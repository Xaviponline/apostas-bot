"""Testes do diagnostico passivo de identidade dos fixtures."""
import copy
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

from auditoria_fixture_shadow import relatorio_auditoria_fixture
from main_competicoes import BotPremiumDiarioCompeticoes

TZ = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2030, 10, 20, 16, 30, tzinfo=TZ)


def previsao(evento=42, rank=1, ts=None, liga="English League Two"):
    return {
        "modelo_versao": "V1.2", "data_jogo": AGORA.date().isoformat(),
        "event_id": evento, "ranking_modelo": rank,
        "timestamp_jogo": ts if ts is not None else (AGORA + timedelta(hours=3)).timestamp(),
        "casa": "Walsall", "fora": "Oldham Athletic",
        "mercado": "Under 2.5 Golos", "liga": liga,
        "probabilidade": 0.696,
    }


def rastreio(p, **modificacoes):
    obs = {
        "event_id_modelo": str(p["event_id"]),
        "mercado_modelo": p["mercado"],
        "jogo": p["casa"] + " vs " + p["fora"],
        "timestamp_jogo": p["timestamp_jogo"],
        "liga_fonte_fixture": p["liga"],
        "inicio_fonte_fixture": datetime.fromtimestamp(
            p["timestamp_jogo"], TZ
        ).isoformat(),
        "alertas_contexto": [],
        "diagnostico": "mercado_nao_disponivel",
    }
    obs.update(modificacoes)
    return obs


class AuditoriaFixtureShadowTest(unittest.TestCase):
    def _ficheiro(self, pasta, obs):
        dest = Path(pasta) / "odds_rastreio.jsonl"
        dest.write_text("".join(json.dumps(o) + "\n" for o in obs), encoding="utf-8")
        return dest

    def test_sinaliza_divergencia_sem_mudar_dados(self):
        p = previsao()
        p_original = copy.deepcopy(p)
        desfasamento = datetime.fromtimestamp(
            p["timestamp_jogo"] + 4 * 3600, TZ
        ).isoformat()
        with tempfile.TemporaryDirectory() as pasta:
            path = self._ficheiro(pasta, [
                rastreio(p, liga_fonte_fixture="FA Cup",
                        inicio_fonte_fixture=desfasamento,
                        alertas_contexto=["competicao_divergente"]),
            ])
            texto = relatorio_auditoria_fixture([p], path, agora=AGORA)
        self.assertIn("Com observacao associada: 1/1", texto)
        self.assertIn("Horario divergente: 1", texto)
        self.assertIn("Competicao divergente: 1", texto)
        self.assertIn("FA Cup", texto)
        self.assertEqual(p, p_original)

    def test_alias_liga_portugal_nao_gera_falso_alerta(self):
        p = previsao(liga="Portuguese Primeira Liga")
        original = copy.deepcopy(p)
        with tempfile.TemporaryDirectory() as pasta:
            path = self._ficheiro(pasta, [rastreio(
                p, liga_fonte_fixture="Liga Portugal",
                alertas_contexto=["competicao_divergente"]
            )])
            texto = relatorio_auditoria_fixture([p], path, agora=AGORA)
        self.assertIn("Competicao divergente: 0", texto)
        self.assertIn("Nomes alternativos conhecidos: 1", texto)
        self.assertIn("Liga Portugal", texto)
        self.assertEqual(p, original)

    def test_alias_primera_lpf_nao_gera_falso_alerta(self):
        p = previsao(liga="Argentine Liga Profesional")
        with tempfile.TemporaryDirectory() as pasta:
            path = self._ficheiro(pasta, [rastreio(
                p, liga_fonte_fixture="Primera LPF",
                alertas_contexto=["competicao_divergente"]
            )])
            texto = relatorio_auditoria_fixture([p], path, agora=AGORA)
        self.assertIn("Competicao divergente: 0", texto)
        self.assertIn("Nomes alternativos conhecidos: 1", texto)

    def test_outra_liga_continua_alerta_sem_aceite_automatico(self):
        p = previsao(liga="Portuguese Primeira Liga")
        with tempfile.TemporaryDirectory() as pasta:
            path = self._ficheiro(pasta, [rastreio(
                p, liga_fonte_fixture="FA Cup",
                alertas_contexto=["competicao_divergente"]
            )])
            texto = relatorio_auditoria_fixture([p], path, agora=AGORA)
        self.assertIn("Competicao divergente: 1", texto)
        self.assertIn("Nomes alternativos conhecidos: 0", texto)

    def test_distingue_registo_sem_contexto_de_sucesso(self):
        p = previsao()
        with tempfile.TemporaryDirectory() as pasta:
            path = self._ficheiro(pasta, [rastreio(
                p, liga_fonte_fixture="", inicio_fonte_fixture=""
            )])
            texto = relatorio_auditoria_fixture([p], path, agora=AGORA)
        self.assertIn("Com observacao associada: 1/1", texto)
        self.assertIn("Com contexto do fixture: 0/1", texto)
        self.assertIn("Sem contexto do fixture: 1", texto)
        self.assertIn("SEM CONTEXTO EXTERNO REGISTADO", texto)
        self.assertNotIn("✅ Sem divergencias", texto)

    def test_nao_associa_evento_proximo_apenas_por_clubes(self):
        p = previsao()
        with tempfile.TemporaryDirectory() as pasta:
            path = self._ficheiro(pasta, [
                rastreio(p, timestamp_jogo=p["timestamp_jogo"] + 80 * 60,
                        alertas_contexto=["competicao_divergente"]),
                rastreio(p, event_id_modelo="outro", alertas_contexto=["competicao_divergente"]),
                rastreio(p, mercado_modelo="Over 2.5 Golos",
                        alertas_contexto=["competicao_divergente"]),
            ])
            texto = relatorio_auditoria_fixture([p], path, agora=AGORA)
        self.assertIn("Com observacao associada: 0/1", texto)
        self.assertIn("Competicao divergente: 0", texto)

    def test_dados_sem_fuso_nao_provam_desfasamento(self):
        p = previsao()
        with tempfile.TemporaryDirectory() as pasta:
            path = self._ficheiro(pasta, [
                rastreio(p, inicio_fonte_fixture="2030-10-20T22:00:00"),
            ])
            texto = relatorio_auditoria_fixture([p], path, agora=AGORA)
        self.assertIn("Horario divergente: 0", texto)

    def test_jsonl_corrompido_falha_fechado(self):
        p = previsao()
        with tempfile.TemporaryDirectory() as pasta:
            path = self._ficheiro(pasta, [rastreio(p)])
            with path.open("a", encoding="utf-8") as file:
                file.write("{registo incompleto\n")
            texto = relatorio_auditoria_fixture([p], path, agora=AGORA)
        self.assertIn("Rastreio ilegivel", texto)
        self.assertNotIn("Com observacao associada: 1/1", texto)

    def test_ausencia_de_rastreio_e_inconclusiva(self):
        p = previsao()
        texto = relatorio_auditoria_fixture([p], None, agora=AGORA)
        self.assertIn("Contexto de fixtures insuficiente", texto)
        self.assertNotIn("✅ Sem divergencias", texto)

    def test_comando_owner_sem_alteracoes(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = bot.chat_id = 41
        bot.username = None
        p = previsao(ts=(datetime.now(TZ) + timedelta(hours=2)).timestamp())
        p["data_jogo"] = datetime.now(TZ).date().isoformat()
        bot.previsoes = SimpleNamespace(dados={"previsoes": [p]}, path=None)
        anterior = copy.deepcopy(bot.previsoes.dados)
        mensagens = []
        bot.enviar_mensagem = lambda chat, msg: mensagens.append((chat, msg))
        bot.processar_comando(41, "/auditoria_fixture", user_id=41)
        self.assertEqual(len(mensagens), 1)
        self.assertIn("AUDITORIA DE FIXTURES", mensagens[0][1])
        self.assertEqual(bot.previsoes.dados, anterior)
        bot.processar_comando(42, "/auditoria_fixture", user_id=42)
        self.assertEqual(len(mensagens), 1)


if __name__ == "__main__":
    unittest.main()
