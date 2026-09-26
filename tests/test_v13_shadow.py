import copy
import tempfile
import unittest
from pathlib import Path

from main_competicoes import BotPremiumDiarioCompeticoes
from main_diario import RegistoPrevisoesDiario
from main_sofascore import AJUDA


class V13ShadowTests(unittest.TestCase):
    @staticmethod
    def _previsao(indice, resultado, prob=0.66, data="2026-09-25"):
        return {
            "chave": f"{indice}|Under 3.5 Golos",
            "event_id": indice,
            "data_jogo": data,
            "timestamp_jogo": 1790350000 + indice,
            "casa": f"Casa {indice}",
            "fora": f"Fora {indice}",
            "liga": "English League One",
            "mercado": "Under 3.5 Golos",
            "modelo_versao": "V1.2",
            "ranking_modelo": ((indice - 1) % 20) + 1,
            "confianca_modelo": "MÉDIA-ALTA",
            "probabilidade": prob,
            "probabilidade_bruta": 0.70,
            "qualidade": 81,
            "odd_justa": 1.0 / prob,
            "odd_minima": 1.05 / prob,
            "criada_em": f"2026-09-25T00:{indice % 60:02d}:00Z",
            "estado": "liquidada" if resultado in (0, 1) else "pendente",
            "resultado_binario": resultado,
        }

    def _historico_59(self):
        treino = [
            self._previsao(i + 1, 1 if i < 21 else 0, prob=0.66)
            for i in range(39)
        ]
        holdout = [
            self._previsao(
                40 + i,
                1 if i < 11 else 0,
                prob=0.67,
                data="2026-09-26",
            )
            for i in range(20)
        ]
        return treino + holdout

    def test_shadow_usa_primeiros_39_e_nao_tem_fuga_do_holdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            historico = self._historico_59()
            reg.dados = {"versao": 1, "previsoes": historico}

            estado_antes = reg._estado_v13_shadow()
            beta_antes = estado_antes["beta"]

            for p in historico[39:]:
                p["resultado_binario"] = 1 - int(p["resultado_binario"])

            estado_depois = reg._estado_v13_shadow()
            self.assertEqual(beta_antes, estado_depois["beta"])
            self.assertEqual(len(estado_depois["treino"]), 39)
            self.assertEqual(len(estado_depois["fora_amostra"]), 20)

    def test_shadow_melhora_calibracao_no_holdout_sintetico_sem_mutar(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            reg.dados = {"versao": 1, "previsoes": self._historico_59()}
            antes = copy.deepcopy(reg.dados)

            texto = reg.relatorio_v13_shadow()

            self.assertIn("V1.3-SHADOW-CAL1", texto)
            self.assertIn("Treino fixo: primeiros 39", texto)
            self.assertIn("Registadas após treino: 20", texto)
            self.assertIn("Liquidadas: 20", texto)
            self.assertIn("Dias liquidados representados: 1", texto)
            self.assertIn("Brier melhor que V1.2: ✅", texto)
            self.assertIn("Calibração absoluta melhor: ✅", texto)
            self.assertIn("OOS: 20/40 ⏳", texto)
            self.assertIn("Dias: 1/3 ⏳", texto)
            self.assertEqual(reg.dados, antes)

    def test_shadow_nao_arranca_sem_39_liquidadas(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            previsoes = [
                self._previsao(i + 1, 1 if i < 20 else 0)
                for i in range(38)
            ]
            reg.dados = {"versao": 1, "previsoes": previsoes}

            texto = reg.relatorio_v13_shadow()

            self.assertIn("TREINO AINDA NÃO CONGELADO", texto)
            self.assertIn("Registos de treino: 38/39", texto)

    def test_comando_shadow_so_responde_ao_admin_e_ajuda_documenta(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            reg.dados = {"versao": 1, "previsoes": self._historico_59()}

            bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
            bot.owner_id = 999
            bot.chat_id = -100
            bot.username = "TesteBot"
            bot.previsoes = reg
            mensagens = []
            bot.enviar_mensagem = lambda chat_id, texto: mensagens.append((chat_id, texto))

            bot.processar_comando(-100, "/v13_shadow", user_id=999)
            self.assertEqual(len(mensagens), 1)
            self.assertIn("V1.3-SHADOW-CAL1", mensagens[0][1])

            mensagens.clear()
            bot.processar_comando(-100, "/v13_shadow", user_id=998)
            self.assertEqual(mensagens, [])
            self.assertIn("/v13_shadow", AJUDA)


if __name__ == "__main__":
    unittest.main()
