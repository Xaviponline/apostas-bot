"""Validação da recolha manual ESPN dos jogos do dia, sem odds nem V1.3."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from lambda_hoje import validar_hoje


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


if __name__ == "__main__":
    unittest.main()
