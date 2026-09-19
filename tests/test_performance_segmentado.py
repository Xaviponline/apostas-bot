import tempfile
import unittest
from pathlib import Path

from main_diario import RegistoPrevisoesDiario


class PerformanceSegmentadoTests(unittest.TestCase):
    def test_relatorio_mostra_segmentos_sem_alterar_dados(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            reg.dados = {
                "versao": 1,
                "previsoes": [
                    {
                        "data_jogo": "2026-09-14",
                        "liga": "English Premier League",
                        "mercado": "Vitória Casa",
                        "probabilidade": 0.65,
                        "qualidade": 90,
                        "resultado_binario": 1,
                        "estado": "ganhou",
                    },
                    {
                        "data_jogo": "2026-09-14",
                        "liga": "English Premier League",
                        "mercado": "Over 2.5 Golos",
                        "probabilidade": 0.60,
                        "qualidade": 60,
                        "resultado_binario": 0,
                        "estado": "perdeu",
                    },
                    {
                        "data_jogo": "2026-09-15",
                        "liga": "Spanish LaLiga",
                        "mercado": "Vitória Casa",
                        "modelo_versao": "V1.1",
                        "probabilidade": 0.70,
                        "qualidade": 75,
                        "resultado_binario": 1,
                        "estado": "ganhou",
                    },
                ],
            }
            antes = [dict(p) for p in reg.dados["previsoes"]]
            texto = reg.relatorio()

        self.assertIn("📅 DESEMPENHO POR DIA", texto)
        self.assertIn("• 14/09: 1/2 (50.0%)", texto)
        self.assertIn("• 15/09: 1/1 (100.0%)", texto)
        self.assertIn("🎯 DESEMPENHO POR MERCADO", texto)
        self.assertIn("• Vitória Casa: 2/2 (100.0%)", texto)
        self.assertIn("• Over 2.5 Golos: 0/1 (0.0%)", texto)
        self.assertIn("🏆 DESEMPENHO POR COMPETIÇÃO", texto)
        self.assertIn("Premier League: 1/2 (50.0%)", texto)
        self.assertIn("LaLiga: 1/1 (100.0%)", texto)
        self.assertIn("📈 DESEMPENHO POR PROBABILIDADE", texto)
        self.assertIn("60–64%: 0/1 (0.0%)", texto)
        self.assertIn("65–69%: 1/1 (100.0%)", texto)
        self.assertIn("70%+: 1/1 (100.0%)", texto)
        self.assertIn("🧩 DESEMPENHO POR VERSÃO", texto)
        self.assertIn("V1.0 (histórico): 1/2 (50.0%)", texto)
        self.assertIn("V1.1: 1/1 (100.0%)", texto)
        self.assertIn("⭐ DESEMPENHO POR CONFIANÇA", texto)
        self.assertIn("⭐⭐⭐⭐⭐ ALTA: 1/1 (100.0%)", texto)
        self.assertIn("⭐⭐⭐⭐ MÉDIA-ALTA: 1/1 (100.0%)", texto)
        self.assertIn("⭐⭐⭐ MÉDIA: 0/1 (0.0%)", texto)
        self.assertIn("🧪 DESEMPENHO POR QUALIDADE DOS DADOS", texto)
        self.assertIn("Dados 85–100: 1/1 (100.0%)", texto)
        self.assertIn("Dados 70–84: 1/1 (100.0%)", texto)
        self.assertIn("Dados 55–69: 0/1 (0.0%)", texto)
        self.assertEqual(reg.dados["previsoes"], antes)


if __name__ == "__main__":
    unittest.main()
