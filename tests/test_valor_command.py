import copy
import unittest
from datetime import datetime, timedelta

from main_competicoes import BotPremiumDiarioCompeticoes
from main_diario import TZ_PORTUGAL


class OddsFake:
    configurada = True
    nome_fonte = "Betano teste"

    def eventos_hoje(self):
        return [
            {
                "id": "evt-1",
                "casa": "Independiente Rivadavia",
                "fora": "Atlético Tucumán",
            }
        ]

    def odds_evento(self, event_id):
        self.assert_id = event_id
        return {
            "casa": "Independiente Rivadavia",
            "fora": "Atlético Tucumán",
            "fonte": self.nome_fonte,
            "mercados": [
                {
                    "name": "Full Time Result",
                    "period": "Full Time",
                    "odds": [
                        {"seleção": "Home", "ref": "1", "odd": 2.25},
                        {"seleção": "Draw", "ref": "X", "odd": 3.10},
                        {"seleção": "Away", "ref": "2", "odd": 3.20},
                    ],
                }
            ],
        }


class PrevisoesFake:
    def __init__(self):
        agora = datetime.now(TZ_PORTUGAL)
        self.dados = {
            "previsoes": [
                {
                    "event_id": 123,
                    "data_jogo": agora.strftime("%Y-%m-%d"),
                    "timestamp_jogo": (agora + timedelta(hours=2)).timestamp(),
                    "casa": "Independiente Rivadavia",
                    "fora": "Atlético Tucumán",
                    "liga": "Argentine Copa Argentina",
                    "mercado": "Vitória Casa",
                    "probabilidade": 0.698,
                    "qualidade": 94,
                    "odd_justa": 1.43,
                    "odd_minima": 1.50,
                    "estado": "pendente",
                    "odd_real": 1.80,
                }
            ]
        }


class ValorCommandTests(unittest.TestCase):
    def test_valor_consulta_odd_atual_sem_alterar_snapshot(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.odds = OddsFake()
        bot.previsoes = PrevisoesFake()
        antes = copy.deepcopy(bot.previsoes.dados)

        texto = bot._executar_valor()

        self.assertIn("VALOR AGORA", texto)
        self.assertIn("atual 2,25", texto)
        self.assertIn("Diferença elevada", texto)
        self.assertEqual(bot.previsoes.dados, antes)

    def test_valor_ignora_previsao_que_ja_comecou(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.odds = OddsFake()
        bot.previsoes = PrevisoesFake()
        bot.previsoes.dados["previsoes"][0]["timestamp_jogo"] = (
            datetime.now(TZ_PORTUGAL) - timedelta(minutes=1)
        ).timestamp()

        texto = bot._executar_valor()

        self.assertIn("Não existem previsões congeladas ainda por começar", texto)


if __name__ == "__main__":
    unittest.main()
