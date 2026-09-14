import tempfile
import unittest
from pathlib import Path

from previsoes_premium import RegistoPrevisoes
from analisador_inteligente import AnalisadorInteligente


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "events": [
                {
                    "id": "999",
                    "status": {"type": {"state": "post", "completed": True}},
                    "competitions": [
                        {
                            "competitors": [
                                {"homeAway": "home", "score": "2"},
                                {"homeAway": "away", "score": "1"},
                            ]
                        }
                    ],
                }
            ]
        }


class FakeSession:
    def get(self, *args, **kwargs):
        return FakeResponse()


class PredictionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "previsoes.json"
        self.reg = RegistoPrevisoes(self.path, session=FakeSession())
        self.selecao = {
            "jogo": {
                "id": 999,
                "casa": "Casa",
                "fora": "Fora",
                "liga": "Liga",
                "timestamp": 1789415100,
            },
            "mercado": "Vitória Casa",
            "probabilidade": 0.65,
            "probabilidade_bruta": 0.68,
            "qualidade": 80,
            "odd_justa": 1 / 0.65,
            "odd_minima": 1.05 / 0.65,
        }

    def test_prediction_is_append_only_and_settles(self):
        self.assertEqual(self.reg.registar([self.selecao]), 1)
        alterada = dict(self.selecao)
        alterada["probabilidade"] = 0.90
        self.assertEqual(self.reg.registar([alterada]), 0)
        self.assertAlmostEqual(self.reg.dados["previsoes"][0]["probabilidade"], 0.65)

        self.assertEqual(self.reg.atualizar_pendentes(), 1)
        stats = self.reg.estatisticas()
        self.assertEqual(stats["liquidadas"], 1)
        self.assertEqual(stats["ganhos"], 1)
        self.assertAlmostEqual(stats["hit_rate"], 1.0)
        self.assertAlmostEqual(stats["brier"], (0.65 - 1) ** 2)
        self.assertIn("Brier Score", self.reg.relatorio())

    def test_conservative_probability_penalizes_lower_quality(self):
        bruta = 0.70
        baixa = AnalisadorInteligente._probabilidade_conservadora(bruta, 55)
        alta = AnalisadorInteligente._probabilidade_conservadora(bruta, 95)
        self.assertLess(baixa, alta)
        self.assertLess(alta, bruta)
        self.assertGreater(baixa, 0.50)


if __name__ == "__main__":
    unittest.main()
