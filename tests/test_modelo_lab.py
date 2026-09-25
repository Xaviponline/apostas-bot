import copy
import tempfile
import time
import unittest
from pathlib import Path

from main_competicoes import BotPremiumDiarioCompeticoes
from main_diario import RegistoPrevisoesDiario
from main_sofascore import AJUDA


class ModeloLabTests(unittest.TestCase):
    def _selecao(self, event_id=88001):
        prob = 0.66
        return {
            "jogo": {
                "id": event_id,
                "casa": "Casa Teste",
                "fora": "Fora Teste",
                "liga": "UEFA Nations League",
                "timestamp": time.time() + 7200,
            },
            "mercado": "Under 3.5 Golos",
            "modelo_versao": "V1.2",
            "ranking_modelo": 1,
            "confianca": "MÉDIA-ALTA",
            "score": prob,
            "probabilidade": prob,
            "probabilidade_bruta": 0.70,
            "qualidade": 96,
            "odd_justa": 1.0 / prob,
            "odd_minima": 1.05 / prob,
            "limite_mercado": 0.64,
            "margem_limite": 0.02,
            "liga_codigo": "uefa.nations",
            "lambda_casa": 1.21,
            "lambda_fora": 0.94,
            "amostra_casa": 8,
            "amostra_fora": 8,
            "amostra_casa_local": 5,
            "amostra_fora_local": 5,
            "amostra_liga": 30,
            "ppg_casa": 1.83,
            "ppg_fora": 1.17,
            "media_liga_casa": 1.42,
            "media_liga_fora": 1.11,
            "media_modelo_casa_gf": 1.50,
            "media_modelo_casa_ga": 0.96,
            "media_modelo_fora_gf": 1.02,
            "media_modelo_fora_ga": 1.14,
            "probabilidades": {
                "Vitória Casa": 0.51,
                "Ambas Marcam": 0.61,
                "Over 2.5 Golos": 0.44,
                "Under 2.5 Golos": 0.56,
                "Under 3.5 Golos": 0.70,
            },
        }

    def test_nova_previsao_congela_telemetria_sem_reescrever_depois(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            selecao = self._selecao()
            original = copy.deepcopy(selecao)

            self.assertEqual(reg.registar([selecao]), 1)
            snap = reg.dados["previsoes"][0]
            diag = snap["diagnostico_modelo"]

            self.assertEqual(selecao, original)
            self.assertEqual(diag["versao"], 1)
            self.assertEqual(diag["liga_codigo"], "uefa.nations")
            self.assertAlmostEqual(diag["lambda_casa"], 1.21)
            self.assertEqual(diag["amostra_casa_local"], 5)
            self.assertAlmostEqual(diag["limite_mercado"], 0.64)
            self.assertIn("Under 3.5 Golos", diag["probabilidades_brutas_mercados"])

            alterada = self._selecao()
            alterada["lambda_casa"] = 3.50
            alterada["probabilidades"]["Under 3.5 Golos"] = 0.90
            self.assertEqual(reg.registar([alterada]), 0)

            diag_depois = reg.dados["previsoes"][0]["diagnostico_modelo"]
            self.assertAlmostEqual(diag_depois["lambda_casa"], 1.21)
            self.assertAlmostEqual(
                diag_depois["probabilidades_brutas_mercados"]["Under 3.5 Golos"],
                0.70,
            )

    def test_modelo_lab_e_read_only_e_valida_invariantes(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            reg.registar([self._selecao()])
            antes = copy.deepcopy(reg.dados)

            texto = reg.relatorio_modelo_lab()

            self.assertIn("MODELO LAB — V1.2", texto)
            self.assertIn("Divergências fórmula V1.2: 0", texto)
            self.assertIn("Divergências odd justa/mínima: 0", texto)
            self.assertIn("Divergências de confiança: 0", texto)
            self.assertIn("Snapshots com diagnóstico detalhado: 1/1", texto)
            self.assertIn("Nenhuma anomalia técnica detetada", texto)
            self.assertEqual(reg.dados, antes)

    def test_modelo_lab_deteta_snapshot_adulterado_sem_o_corrigir(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            reg.registar([self._selecao()])
            reg.dados["previsoes"][0]["probabilidade"] = 0.80
            antes = copy.deepcopy(reg.dados)

            texto = reg.relatorio_modelo_lab()

            self.assertIn("Divergências fórmula V1.2: 1", texto)
            self.assertEqual(reg.dados, antes)

    def test_comando_modelo_lab_so_responde_ao_admin(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            reg.registar([self._selecao()])

            bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
            bot.owner_id = 999
            bot.chat_id = -100
            bot.username = "TesteBot"
            bot.previsoes = reg
            mensagens = []
            bot.enviar_mensagem = lambda chat_id, texto: mensagens.append((chat_id, texto))

            bot.processar_comando(-100, "/modelo_lab", user_id=999)
            self.assertEqual(len(mensagens), 1)
            self.assertIn("MODELO LAB", mensagens[0][1])

            mensagens.clear()
            bot.processar_comando(-100, "/modelo_lab", user_id=998)
            self.assertEqual(mensagens, [])

    def test_ajuda_documenta_modelo_lab(self):
        self.assertIn("/modelo_lab", AJUDA)


if __name__ == "__main__":
    unittest.main()
