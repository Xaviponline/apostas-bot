import copy
import tempfile
import unittest
from pathlib import Path

from main_competicoes import BotPremiumDiarioCompeticoes
from previsoes_premium import RegistoPrevisoes


class CarteiraDetalheTests(unittest.TestCase):
    @staticmethod
    def selecao(evento, odd, minima=1.75):
        return {
            "jogo": {
                "id": evento,
                "casa": f"Casa {evento}",
                "fora": f"Fora {evento}",
                "liga": "Liga Teste",
                "timestamp": 1893528000 + 3600 * evento,
            },
            "mercado": "Ambas Marcam",
            "probabilidade": 0.60,
            "probabilidade_bruta": 0.625,
            "qualidade": 80,
            "odd_justa": 1.6667,
            "odd_minima": minima,
            "odd_real": odd,
            "ranking_modelo": 2,
            "confianca": "MÉDIA",
            "score": 0.60,
        }

    @staticmethod
    def bot(registo):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.previsoes = registo
        bot.owner_id = 999
        bot.chat_id = -100
        bot.username = "TesteBot"
        bot.enviar_mensagem = lambda chat_id, texto: None
        return bot

    def test_ledger_apenas_value_calcula_resultados_e_clv_sem_modificar_historico(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            reg.registar([
                self.selecao(1, 1.80),
                self.selecao(2, 2.10),
                self.selecao(3, 1.60),
                self.selecao(4, 1.85),
            ])
            p1, p2, p3, p4 = reg.dados["previsoes"]
            p1["resultado_binario"] = 1
            p2["resultado_binario"] = 0
            p4["estado"] = "pendente"
            p1["odd_fecho"] = 1.70
            p1["odd_fecho_capturada_em"] = "2030-01-01T19:35:00Z"
            p2["odd_fecho"] = 2.20
            anterior = copy.deepcopy(reg.dados)

            linhas = reg.entradas_carteira_valor()
            self.assertEqual(len(linhas), 3)
            self.assertEqual(len(linhas), reg.metricas_carteira_valor()["elegiveis"])
            por_chave = {r["chave"]: r for r in linhas}
            ganhos = next(x for x in linhas if x["casa"] == "Casa 1")
            perdas = next(x for x in linhas if x["casa"] == "Casa 2")
            pendente = next(x for x in linhas if x["casa"] == "Casa 4")
            self.assertAlmostEqual(ganhos["lucro_unidades"], 0.80)
            self.assertAlmostEqual(ganhos["clv"], 1.80 / 1.70 - 1)
            self.assertAlmostEqual(perdas["lucro_unidades"], -1.0)
            self.assertLess(perdas["clv"], 0)
            self.assertIsNone(pendente["resultado_binario"])
            self.assertIsNone(pendente["clv"])
            self.assertEqual(reg.metricas_clv()["total"], 2)
            self.assertEqual(reg.dados, anterior)
            self.assertEqual(reg.verificar_integridade()["divergentes"], 0)

    def test_detalhe_e_clv_mostram_odds_resultados_e_ausencia_de_fecho(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            reg.registar([self.selecao(1, 1.80), self.selecao(2, 1.90)])
            primeiro, segundo = reg.dados["previsoes"]
            primeiro["resultado_binario"] = 1
            primeiro["odd_fecho"] = 1.70
            segundo["resultado_binario"] = 0

            bot = self.bot(reg)
            antes = copy.deepcopy(reg.dados)
            detalhe = bot._executar_carteira_detalhe()
            clv = bot._executar_clv()

            self.assertIn("CARTEIRA VALUE — DETALHE", detalhe)
            self.assertIn("Entrada 1,80 | Mín. 1,75 | Fecho 1,70", detalhe)
            self.assertIn("GANHOU | P/L +0,80u | CLV +5,9%", detalhe)
            self.assertIn("PERDEU | P/L -1,00u | CLV sem fecho", detalhe)
            self.assertIn("FECHOS INDIVIDUAIS", clv)
            self.assertIn("1,80 → 1,70 | CLV +5,9%", clv)
            self.assertEqual(reg.dados, antes)

    def test_paginacao_e_acesso_somente_admin(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            reg.registar([self.selecao(i, 1.80) for i in range(1, 11)])
            bot = self.bot(reg)
            self.assertIn("Página 1/2", bot._executar_carteira_detalhe())
            self.assertIn("Página 2/2", bot._executar_carteira_detalhe("2"))
            self.assertNotIn("Casa 10", bot._executar_carteira_detalhe("2"))
            self.assertIn("Página seguinte", bot._executar_carteira_detalhe())
            self.assertIn("Formato", bot._executar_carteira_detalhe("abc"))
            self.assertIn("Só existem 2", bot._executar_carteira_detalhe("3"))

            mensagens = []
            bot.enviar_mensagem = lambda chat_id, texto: mensagens.append((chat_id, texto))
            bot.processar_comando(-100, "/carteira_detalhe 2", user_id=999)
            self.assertEqual(len(mensagens), 1)
            self.assertIn("Página 2/2", mensagens[0][1])
            mensagens.clear()
            bot.processar_comando(-100, "/carteira_detalhe", user_id=998)
            self.assertEqual(mensagens, [])


if __name__ == "__main__":
    unittest.main()
