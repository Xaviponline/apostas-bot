"""Validação da recolha manual ESPN dos jogos do dia, sem odds nem V1.3."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from lambda_hoje import validar_hoje, validar_pendentes


class Resposta:
    def __init__(self, events):
        self.events = events
    def raise_for_status(self):
        pass
    def json(self):
        return {"events": self.events}


class Sessao:
    def __init__(self, events):
        self.events = events
        self.calls = []
    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return Resposta(self.events)


class TestLambdaHoje(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "lambda_prospectivo_shadow.jsonl"
        self.agora = datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc)
        self.jogo = dict(id=555, casa_id=12, fora_id=34,
                         timestamp=int(datetime(2026, 11, 27, 12, 0,
                                                tzinfo=timezone.utc).timestamp()))
        self.snapshot = dict(versao=1, chave="eng.1|555",
                             jogo=self.jogo, liga_codigo="eng.1",
                             capturado_em_utc="2026-11-27T09:00:00+00:00")
        self.path.write_text(json.dumps(self.snapshot) + "\n")

    def test_final_exato_escreve_apenas_resultado_independente_e_deduplica(self):
        event = {
            "id": "555", "date": "2026-11-27T12:00Z",
            "status": {"type": {"state": "post", "name": "STATUS_FINAL", "completed": True}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"id": "12"}, "score": "2"},
                {"homeAway": "away", "team": {"id": "34"}, "score": "1"},
            ]}],
        }
        sessao = Sessao([event])
        before = self.path.read_bytes()
        texto = validar_hoje(self.path, agora=self.agora, session=sessao)
        self.assertIn("novos gravados nesta verificação: 1", texto)
        self.assertEqual(len(sessao.calls), 1)
        self.assertEqual(self.path.read_bytes(), before)
        res = self.path.with_name("lambda_prospectivo_resultados.jsonl")
        self.assertEqual(len(res.read_text().splitlines()), 1)
        self.assertIn("novos gravados nesta verificação: 0",
                      validar_hoje(self.path, agora=self.agora, session=sessao))
        self.assertEqual(len(sessao.calls), 1)

    def test_sem_final_mantem_pendente_sem_gravar(self):
        sessao = Sessao([])
        texto = validar_hoje(self.path, agora=self.agora, session=sessao)
        self.assertIn("Sem resultado final confirmado: 1", texto)
        self.assertFalse(self.path.with_name("lambda_prospectivo_resultados.jsonl").exists())

    def test_jogo_ainda_nao_iniciado_nao_faz_http(self):
        sessao = Sessao([])
        texto = validar_hoje(self.path, agora=datetime(2026, 11, 27, 11,
                                                        tzinfo=timezone.utc), session=sessao)
        self.assertIn("ainda cedo: 1", texto)
        self.assertEqual(sessao.calls, [])

    def test_sem_data_pre_jogo_nao_faz_http(self):
        self.snapshot["capturado_em_utc"] = "2026-11-27T13:00:00+00:00"
        self.path.write_text(json.dumps(self.snapshot) + "\n")
        sessao = Sessao([])
        texto = validar_hoje(self.path, agora=self.agora, session=sessao)
        self.assertIn("snapshot pré-jogo: 0", texto)
        self.assertEqual(sessao.calls, [])


    def test_pendentes_recupera_jogo_de_ontem_apos_meia_noite(self):
        # A consulta do dia 28 recupera um snapshot de 27/11 já terminado.
        event = {
            "id": "555", "date": "2026-11-27T12:00Z",
            "status": {"type": {"state": "post", "name": "STATUS_FINAL", "completed": True}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"id": "12"}, "score": "2"},
                {"homeAway": "away", "team": {"id": "34"}, "score": "1"},
            ]}],
        }
        sessao = Sessao([event])
        original = self.path.read_bytes()
        agora = datetime(2026, 11, 28, 1, 0, tzinfo=timezone.utc)
        msg = validar_pendentes(self.path, agora=agora, session=sessao)
        self.assertIn("novos gravados: 1", msg)
        self.assertEqual(sessao.calls[0][1]["dates"], "20261127")
        self.assertEqual(original, self.path.read_bytes())
        msg2 = validar_pendentes(self.path, agora=agora, session=sessao)
        self.assertIn("novos gravados: 0", msg2)
        self.assertEqual(len(sessao.calls), 1)

    def test_pendentes_exclui_inicio_futuro_e_captura_tardia(self):
        sessao = Sessao([])
        msg = validar_pendentes(self.path, agora=datetime(2026, 11, 27, 11,
                                                          tzinfo=timezone.utc), session=sessao)
        self.assertIn("demasiado recentes: 1", msg)
        self.assertEqual(sessao.calls, [])
        self.snapshot["capturado_em_utc"] = "2026-11-27T13:00:00+00:00"
        self.path.write_text(json.dumps(self.snapshot) + "\n")
        msg = validar_pendentes(self.path, agora=self.agora, session=sessao)
        self.assertIn("Snapshots elegíveis (últimos 3 dias): 0", msg)
        self.assertEqual(sessao.calls, [])

    def test_pendentes_sem_final_continua_pendente(self):
        sessao = Sessao([])
        msg = validar_pendentes(self.path, agora=self.agora, session=sessao)
        self.assertIn("Ainda sem final confirmado: 1", msg)
        self.assertFalse(self.path.with_name("lambda_prospectivo_resultados.jsonl").exists())

    def test_pendentes_diagnostica_id_ausente_sem_forcar_associacao(self):
        evento = {
            "id": "999", "date": "2026-11-27T12:00Z",
            "status": {"type": {"state": "post", "name": "STATUS_FINAL", "completed": True}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"id": "12"}, "score": "2"},
                {"homeAway": "away", "team": {"id": "34"}, "score": "1"},
            ]}],
        }
        sessao = Sessao([evento])
        original = self.path.read_bytes()
        resposta = validar_pendentes(self.path, agora=self.agora, session=sessao)
        self.assertIn("ESPN 1 eventos, 1 finais", resposta)
        self.assertIn("IDs ausentes 1", resposta)
        self.assertIn("novos gravados: 0", resposta)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.path.with_name("lambda_prospectivo_resultados.jsonl").exists())
        self.assertEqual(len(sessao.calls), 1)

    def test_pendentes_diagnostica_horario_divergente_sem_associar(self):
        evento = {
            "id": "555", "date": "2026-11-27T12:05Z",
            "status": {"type": {"state": "post", "name": "STATUS_FINAL", "completed": True}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"id": "12"}, "score": "2"},
                {"homeAway": "away", "team": {"id": "34"}, "score": "1"},
            ]}],
        }
        resposta = validar_pendentes(self.path, agora=self.agora, session=Sessao([evento]))
        self.assertIn("horários ≠ 1", resposta)
        self.assertIn("desvios de 5–5 min", resposta)
        self.assertIn("exatos 0", resposta)
        self.assertIn("novos gravados: 0", resposta)

    def test_pendentes_diagnostica_resultado_nao_normalizado(self):
        evento = {
            "id": "555", "date": "2026-11-27T12:00Z",
            "status": {"type": {"state": "post", "name": "STATUS_FINAL", "completed": True}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"id": "12"}, "score": {"value": 2}},
                {"homeAway": "away", "team": {"id": "34"}, "score": {"value": 1}},
            ]}],
        }
        resposta = validar_pendentes(self.path, agora=self.agora, session=Sessao([evento]))
        self.assertIn("não normalizados 1", resposta)
        self.assertIn("novos gravados: 0", resposta)

    def test_pendentes_diagnostica_id_completo_e_grava_sem_pedidos_adicionais(self):
        evento = {
            "id": "555", "date": "2026-11-27T12:00Z",
            "status": {"type": {"state": "post", "name": "STATUS_FINAL", "completed": True}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"id": "12"}, "score": "2"},
                {"homeAway": "away", "team": {"id": "34"}, "score": "1"},
            ]}],
        }
        sessao = Sessao([evento])
        resposta = validar_pendentes(self.path, agora=self.agora, session=sessao)
        self.assertIn("exatos 1", resposta)
        self.assertIn("novos gravados: 1", resposta)
        self.assertEqual(len(sessao.calls), 1)


    def test_pendentes_aceita_espn_status_full_time_com_final_explicito(self):
        evento = {
            "id": "555", "date": "2026-11-27T12:00Z",
            "status": {"type": {"state": "post", "name": "STATUS_FULL_TIME",
                                 "completed": True, "detail": "FT"}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"id": "12"}, "score": "2"},
                {"homeAway": "away", "team": {"id": "34"}, "score": "1"},
            ]}],
        }
        original = self.path.read_bytes()
        sessao = Sessao([evento])
        resposta = validar_pendentes(self.path, agora=self.agora, session=sessao)
        self.assertIn("ESPN 1 eventos, 1 finais", resposta)
        self.assertIn("exatos 1", resposta)
        self.assertIn("novos gravados: 1", resposta)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(len(sessao.calls), 1)
        self.assertIn("novos gravados: 0",
                      validar_pendentes(self.path, agora=self.agora, session=sessao))
        self.assertEqual(len(sessao.calls), 1)

    def test_full_time_incompleto_ou_nao_post_nao_liquida(self):
        from estatisticas_espn import EstatisticasESPN
        original = {
            "id": "555", "date": "2026-11-27T12:00Z",
            "status": {"type": {"state": "post", "name": "STATUS_FULL_TIME",
                                 "completed": True, "detail": "FT"}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"id": "12"}, "score": "2"},
                {"homeAway": "away", "team": {"id": "34"}, "score": "1"},
            ]}],
        }
        for state, completed, name, detail in (
            ("post", False, "STATUS_FULL_TIME", "FT"),
            ("in", True, "STATUS_FULL_TIME", "FT"),
            ("post", True, "STATUS_POSTPONED", "Postponed"),
            ("post", True, "STATUS_FULL_TIME", "After Extra Time"),
            ("post", True, "STATUS_FULL_TIME", "AET"),
        ):
            with self.subTest(state=state, completed=completed, name=name, detail=detail):
                evento = dict(original, status={"type": {
                    "state": state, "completed": completed,
                    "name": name, "detail": detail}})
                parsed = EstatisticasESPN._normalizar_resultado(evento, "eng.2")
                self.assertIsNotNone(parsed)
                self.assertIs(parsed["final_regulamentar_shadow"], False)
                sessao = Sessao([evento])
                resposta = validar_pendentes(self.path, agora=self.agora, session=sessao)
                self.assertIn("novos gravados: 0", resposta)
                self.assertFalse(self.path.with_name("lambda_prospectivo_resultados.jsonl").exists())

    def test_pendentes_exibe_estado_bruto_quando_nao_final(self):
        evento = {
            "id": "555", "date": "2026-11-27T12:00Z",
            "status": {"type": {"state": "in", "name": "STATUS_IN_PROGRESS",
                                 "completed": False}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"id": "12"}, "score": "0"},
                {"homeAway": "away", "team": {"id": "34"}, "score": "0"},
            ]}],
        }
        resposta = validar_pendentes(self.path, agora=self.agora, session=Sessao([evento]))
        self.assertIn("estados:", resposta)
        self.assertIn("STATUS_IN_PROGRESS/in/completed=False ×1", resposta)
        self.assertIn("novos gravados: 0", resposta)


if __name__ == "__main__":
    unittest.main()
