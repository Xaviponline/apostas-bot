import tempfile
import unittest
from pathlib import Path

from previsoes_premium import RegistoPrevisoes


class ROIOddsTests(unittest.TestCase):
    @staticmethod
    def _selecao(event_id, odd_real=None, timestamp=1789415100):
        s = {
            "jogo": {
                "id": event_id,
                "casa": f"Casa {event_id}",
                "fora": f"Fora {event_id}",
                "liga": "Liga",
                "timestamp": timestamp,
            },
            "mercado": "Vitória Casa",
            "probabilidade": 0.60,
            "probabilidade_bruta": 0.62,
            "qualidade": 80,
            "odd_justa": 1 / 0.60,
            "odd_minima": 1.05 / 0.60,
        }
        if odd_real is not None:
            s.update(
                {
                    "odd_real": odd_real,
                    "odds_fonte": "Fonte Teste",
                    "odds_event_id": f"odds-{event_id}",
                    "odds_atualizada_em": "2026-09-16T10:00:00Z",
                }
            )
        return s

    def test_registo_congela_odd_e_roi_ignora_previsao_sem_odd(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            self.assertEqual(reg.registar([self._selecao(1, 2.00), self._selecao(2)]), 2)

            p1, p2 = reg.dados["previsoes"]
            self.assertEqual(p1["odd_real"], 2.0)
            self.assertAlmostEqual(p1["ev_real"], 0.20)
            self.assertNotIn("odd_real", p2)

            p1["resultado_binario"] = 1
            p1["estado"] = "ganhou"
            p2["resultado_binario"] = 0
            p2["estado"] = "perdeu"

            stats = reg.estatisticas()
            self.assertEqual(stats["liquidadas"], 2)
            self.assertEqual(stats["odds_liquidadas"], 1)
            self.assertAlmostEqual(stats["lucro_unidades"], 1.0)
            self.assertAlmostEqual(stats["roi"], 1.0)
            self.assertIn("ROI observado: +100.0%", reg.relatorio())

    def test_nao_anexa_odd_se_o_jogo_ja_comecou(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            self.assertEqual(reg.registar([self._selecao(3)]), 1)
            self.assertEqual(reg.registar([self._selecao(3, 1.90)]), 0)
            self.assertNotIn("odd_real", reg.dados["previsoes"][0])

    def test_anexa_primeira_odd_real_antes_do_jogo_sem_reescrever_modelo(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            futuro = 1893456000  # 2030-01-01 UTC
            inicial = self._selecao(4, timestamp=futuro)
            self.assertEqual(reg.registar([inicial]), 1)

            antes = dict(reg.dados["previsoes"][0])
            enriquecida = self._selecao(4, 1.90, timestamp=futuro)
            enriquecida["probabilidade"] = 0.99
            enriquecida["qualidade"] = 1

            self.assertEqual(reg.registar([enriquecida]), 0)
            p = reg.dados["previsoes"][0]

            self.assertEqual(p["odd_real"], 1.9)
            self.assertAlmostEqual(p["ev_real"], (0.60 * 1.90) - 1.0)
            self.assertEqual(p["probabilidade"], antes["probabilidade"])
            self.assertEqual(p["qualidade"], antes["qualidade"])
            self.assertEqual(p["odd_justa"], antes["odd_justa"])
            self.assertIn("odds_capturada_em", p)


if __name__ == "__main__":
    unittest.main()