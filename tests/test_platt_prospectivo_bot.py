"""Integração administrativa e export SHADOW sem impacto na V1.2."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from main_competicoes import BotPremiumDiarioCompeticoes
from main_enriquecido import BotPremiumDiarioDiagnostico


class PlattBotShadowTests(unittest.TestCase):
    def setUp(self):
        self.bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        self.bot.owner_id = self.bot.chat_id = 77
        self.bot.username = None
        self.bot.previsoes = SimpleNamespace(dados={"previsoes": [{"event_id": 5}]})
        self.bot.research_lab = Mock()
        self.bot.research_lab.configurado = True

    def test_auto_export_quando_analise_normal_sucesso(self):
        antes = copy.deepcopy(self.bot.previsoes.dados)
        with patch.object(BotPremiumDiarioDiagnostico, "_executar_analise",
                          return_value="RELATORIO"):
            saida = self.bot._executar_analise()
            self.assertEqual(saida, "RELATORIO")
            self.bot.research_lab.exportar.assert_called_once()
            self.bot._executar_analise()
            self.bot.research_lab.exportar.assert_called_once()
        self.assertEqual(antes, self.bot.previsoes.dados)

    def test_auto_export_se_aumenta_historico(self):
        with patch.object(BotPremiumDiarioDiagnostico, "_executar_analise",
                          return_value="RELATORIO"):
            self.bot._executar_analise()
            self.bot.previsoes.dados["previsoes"].append({"event_id": 6})
            self.bot._executar_analise()
        self.assertEqual(self.bot.research_lab.exportar.call_count, 2)

    def test_falha_lab_nao_bloqueia_analise(self):
        self.bot.research_lab.exportar.side_effect = RuntimeError("falha simulada")
        with patch.object(BotPremiumDiarioDiagnostico, "_executar_analise",
                          return_value="RELATORIO"):
            self.assertEqual(self.bot._executar_analise(), "RELATORIO")
        self.assertEqual(len(self.bot.previsoes.dados["previsoes"]), 1)

    def test_analise_tecnica_nao_exporta(self):
        with patch.object(BotPremiumDiarioDiagnostico, "_executar_analise",
                          return_value="TECNICO"):
            self.assertEqual(self.bot._executar_analise(tecnica=True), "TECNICO")
            self.bot.research_lab.exportar.assert_not_called()

    def test_comando_owner_apenas_leitura(self):
        payload = {
            "platt_prospectivo": {
                "estado": "AVALIAÇÃO_DESCRITIVA",
                "treino_n": 120, "treino_dias": 20,
                "treino_digest": "abc123", "congelado_em": "2026-10-17T13:00:00Z",
                "previsoes": 2, "alvo": 100,
                "inscritas_total": 2, "liquidadas": 1,
                "dias": 1, "avisos": 0, "delta_brier": -0.01,
                "brier_champion": 0.26, "brier_platt": 0.25,
                "gap_champion_pp": -10.0, "gap_platt_pp": -2.0,
            }
        }
        self.bot.research_lab.status.return_value = payload
        mensagens = []
        self.bot.enviar_mensagem = lambda chat, texto: mensagens.append(texto)
        original = copy.deepcopy(self.bot.previsoes.dados)
        self.bot.processar_comando(77, "/lab_platt_prospectivo", user_id=77)
        self.assertEqual(len(mensagens), 1)
        self.assertIn("PLATT TOP5", mensagens[0])
        self.assertIn("2/100", mensagens[0])
        self.assertIn("Sem decisão", mensagens[0])
        self.bot.processar_comando(88, "/lab_platt_prospectivo", user_id=88)
        self.assertEqual(len(mensagens), 1)
        self.assertEqual(original, self.bot.previsoes.dados)


if __name__ == "__main__":
    unittest.main()
