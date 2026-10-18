"""VALUE historico vs consulta posterior sem cotacao: somente leitura."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from odds_rastreio import RastreioOdds
from main_competicoes import BotPremiumDiarioCompeticoes


PT = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2026, 10, 18, 12, 18, tzinfo=PT)
KICKOFF = datetime(2026, 10, 18, 11, 15, tzinfo=PT).timestamp()


class TestValidadeHistorica(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "rastreio.jsonl"
        self.rastreio = RastreioOdds(self.path)
        self.snapshot = {
            "event_id": 108,
            "mercado": "Vitória Casa",
            "data_jogo": "2026-10-18",
            "timestamp_jogo": KICKOFF,
            "casa": "RKC Waalwijk",
            "fora": "FC Volendam",
            "odd_real": 2.05,
            "odd_valor_confirmado": 2.05,
            "odd_minima": 1.51,
            "valor_estado": "confirmado",
            "estado": "pendente",
        }
        self.previsoes = SimpleNamespace(dados={"previsoes": [self.snapshot]})

    def obs(self, hora, odd=None, diagnostico="", event_id="108", mercado="Vitória Casa"):
        return {
            "event_id_modelo": event_id,
            "mercado_modelo": mercado,
            "timestamp_jogo": KICKOFF,
            "observado_em": datetime(2026, 10, 18, hora // 60, hora % 60,
                                     tzinfo=PT).astimezone(timezone.utc).isoformat(),
            "odd_observada": odd,
            "diagnostico": diagnostico,
        }

    def escrever(self, *observacoes):
        with self.path.open("w", encoding="utf-8") as f:
            for p in observacoes:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")

    def test_rkc_preco_9h_falhas_1045_e_1105(self):
        self.escrever(
            self.obs(9*60, odd=2.05),
            self.obs(10*60+45, diagnostico="mercado_nao_disponivel"),
            self.obs(11*60+5, diagnostico="mercado_nao_disponivel"),
        )
        original = copy.deepcopy(self.previsoes.dados)
        bytes_antes = self.path.read_bytes()
        result = self.rastreio.relatorio_disponibilidade(self.previsoes, agora=AGORA)
        self.assertIn("VALUE histórico nos últimos 7 dias: 1", result)
        self.assertIn("Última observação sem cotação válida: 1", result)
        self.assertIn("RKC Waalwijk", result)
        self.assertIn("18/10/2026 11:05", result)
        self.assertIn("preço NÃO reconfirmado", result)
        self.assertIn("2.05", result)
        self.assertEqual(self.previsoes.dados, original)
        self.assertEqual(self.path.read_bytes(), bytes_antes)

    def test_cotacao_recuperada_na_ronda_seguinte_limpa_sinal(self):
        self.escrever(
            self.obs(9*60, odd=2.05),
            self.obs(10*60+45, diagnostico="mercado_nao_disponivel"),
            self.obs(11*60, odd=1.80),
        )
        report = self.rastreio.relatorio_disponibilidade(self.previsoes, agora=AGORA)
        self.assertIn("Última observação com preço: 1", report)
        self.assertIn("Última observação sem cotação válida: 0", report)
        self.assertNotIn("preço NÃO reconfirmado", report)

    def test_evento_mercado_diferente_ou_pos_jogo_nao_contamina(self):
        self.escrever(
            self.obs(9*60, odd=2.05),
            self.obs(11*60, diagnostico="mercado_nao_disponivel", event_id="999"),
            self.obs(11*60, diagnostico="mercado_nao_disponivel", mercado="Ambas Marcam"),
            self.obs(11*60+25, diagnostico="mercado_nao_disponivel"),
        )
        report = self.rastreio.relatorio_disponibilidade(self.previsoes, agora=AGORA)
        self.assertIn("Última observação com preço: 1", report)
        self.assertIn("Última observação sem cotação válida: 0", report)

    def test_sem_rastreio_nao_inventa_validade(self):
        report = self.rastreio.relatorio_disponibilidade(self.previsoes, agora=AGORA)
        self.assertIn("não é possível reconfirmar", report)
        self.assertFalse(self.path.exists())

    def test_readonly_apenas_owner_e_sem_oddspapi(self):
        self.escrever(
            self.obs(9*60, odd=2.05),
            self.obs(11*60+5, diagnostico="mercado_nao_disponivel"),
        )
        b = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        b.username = None
        b.owner_id = b.chat_id = 43
        b._rastreio_odds = self.rastreio
        b.previsoes = self.previsoes
        msgs = []
        b.enviar_mensagem = lambda chat, resp: msgs.append((chat, resp))
        b.processar_comando(44, "/odds_validade", user_id=44)
        self.assertEqual(msgs, [])
        b.processar_comando(43, "/odds_validade", user_id=43)
        self.assertEqual(len(msgs), 1)
        self.assertIn("VALIDADE DAS ODDS", msgs[0][1])


if __name__ == "__main__":
    unittest.main()
