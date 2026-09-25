import copy
import tempfile
import unittest
from pathlib import Path

from main_diario import BotPremiumDiario, RegistoPrevisoesDiario
from main_sofascore import AJUDA


class V12StatusTests(unittest.TestCase):
    @staticmethod
    def _previsao(indice, resultado=None):
        liquidada = resultado in (0, 1)
        return {
            "data_jogo": "2026-09-25",
            "liga": "UEFA Nations League",
            "mercado": "Under 3.5 Golos" if indice % 2 else "Ambas Marcam",
            "modelo_versao": "V1.2",
            "ranking_modelo": (indice % 20) + 1,
            "confianca_modelo": "ALTA" if indice % 3 == 0 else "MÉDIA-ALTA",
            "probabilidade": 0.66,
            "qualidade": 96,
            "resultado_binario": resultado,
            "estado": ("ganhou" if resultado == 1 else "perdeu") if liquidada else "pendente",
        }

    def _registo_atual(self):
        reg = RegistoPrevisoesDiario.__new__(RegistoPrevisoesDiario)
        liquidadas = [
            self._previsao(i, 1 if i < 14 else 0)
            for i in range(27)
        ]
        pendentes = [self._previsao(100 + i, None) for i in range(12)]
        reg.dados = {
            "versao": 1,
            "previsoes": liquidadas
            + pendentes
            + [
                {
                    "modelo_versao": "V1.1",
                    "probabilidade": 0.65,
                    "qualidade": 80,
                    "resultado_binario": 1,
                    "estado": "ganhou",
                }
            ],
        }
        return reg

    def test_resumo_v12_conta_apenas_v12(self):
        reg = self._registo_atual()
        antes = copy.deepcopy(reg.dados)

        resumo = reg.resumo_v12()

        self.assertEqual(resumo["registadas"], 39)
        self.assertEqual(resumo["liquidadas"], 27)
        self.assertEqual(resumo["pendentes"], 12)
        self.assertEqual(resumo["faltam"], 13)
        self.assertEqual(resumo["potencial"], 39)
        self.assertEqual(resumo["faltam_apos_pendentes"], 1)
        self.assertAlmostEqual(resumo["progresso"], 0.675)
        self.assertEqual(reg.dados, antes)

    def test_v12_status_e_read_only(self):
        bot = BotPremiumDiario.__new__(BotPremiumDiario)
        bot.previsoes = self._registo_atual()
        antes = copy.deepcopy(bot.previsoes.dados)

        texto = bot._executar_v12_status()

        self.assertIn("V1.2 — CENTRO DE CONTROLO", texto)
        self.assertIn("MODELO CONGELADO", texto)
        self.assertIn("Liquidadas: 27/40", texto)
        self.assertIn("Pendentes: 12", texto)
        self.assertIn("67.5%", texto)
        self.assertIn("39/40", texto)
        self.assertIn("apenas leitura", texto)
        self.assertEqual(bot.previsoes.dados, antes)

    def test_ciclo_v12_assinala_meta_atingida(self):
        reg = RegistoPrevisoesDiario.__new__(RegistoPrevisoesDiario)
        reg.dados = {
            "versao": 1,
            "previsoes": [
                self._previsao(i, 1 if i % 2 == 0 else 0)
                for i in range(40)
            ],
        }

        texto = reg._relatorio_ciclo_v12()

        self.assertIn("Liquidadas: 40/40", texto)
        self.assertIn("AMOSTRA-ALVO ATINGIDA", texto)
        self.assertIn("auditoria da V1.2", texto)

    def test_ajuda_expoe_v12_status(self):
        self.assertIn("/v12_status", AJUDA)
        self.assertIn("apenas leitura", AJUDA)


if __name__ == "__main__":
    unittest.main()
