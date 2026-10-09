import unittest
import pandas as pd
from research_lab.segment_drift import relatorio_drift_segmentado


def exemplo(n=100, desvio_condicional=False):
    data = []
    for i in range(n):
        recente = i >= int(n * .6)
        mercado = "Under 2.5 Golos" if (i % 10 < (8 if recente else 2)) else "Over 2.5 Golos"
        liga = "Liga A" if i % 3 else "Liga B"
        p = 0.62 if mercado.startswith("Under") else 0.72
        data.append({
            "snapshot_index": i + 1,
            "resultado": 1,
            "probabilidade": p,
            "data_jogo": f"2026-09-{1 + i // 5:02d}",
            "mercado": mercado,
            "liga": liga,
            "lambda_total": (2.1 if mercado.startswith("Under") else 3.2) + (0.4 if recente and desvio_condicional else 0),
            "media_liga_total": 2.3 if mercado.startswith("Under") else 3.0,
            "margem_limite": 0.06,
        })
    return pd.DataFrame(data)


class SegmentedDriftTests(unittest.TestCase):
    def test_usa_split_fixo_e_nunca_faz_promocao(self):
        original = exemplo()
        anterior = original.copy(deep=True)
        rel = relatorio_drift_segmentado(original)
        pd.testing.assert_frame_equal(original, anterior)
        self.assertEqual(rel["resumo"]["base"]["n"], 60)
        self.assertEqual(rel["resumo"]["recente"]["n"], 40)
        self.assertEqual(rel["resumo"]["base"]["snapshot_max"], 60)
        self.assertEqual(rel["resumo"]["recente"]["snapshot_min"], 61)
        self.assertNotIn("promotion", str(rel).lower())

    def test_composicao_nao_e_confundida_com_drift_condicional(self):
        rel = relatorio_drift_segmentado(exemplo())
        seg = rel["por_mercado"]
        self.assertEqual(seg["n_segmentos_elegiveis"], 2)
        self.assertAlmostEqual(seg["brier_mix_base"]["delta"], 0.0, places=12)
        for item in seg["segmentos"]:
            self.assertAlmostEqual(item["features"]["lambda_total"]["delta_media"], 0, places=12)

    def test_drift_condicional_e_identificado_sem_ajustar_thresholds(self):
        rel = relatorio_drift_segmentado(exemplo(desvio_condicional=True))
        seg = rel["por_mercado"]
        for item in seg["segmentos"]:
            self.assertAlmostEqual(item["features"]["lambda_total"]["delta_media"], 0.4, places=12)

    def test_grupos_pequenos_nao_sao_comparados(self):
        rel = relatorio_drift_segmentado(exemplo(40), minimo=20)
        self.assertEqual(rel["por_liga_mercado"]["n_segmentos_elegiveis"], 0)
        self.assertIsNone(rel["por_liga_mercado"]["brier_mix_base"])

    def test_amostra_insuficiente(self):
        self.assertEqual(relatorio_drift_segmentado(exemplo(12))["estado"], "AMOSTRA_INSUFICIENTE")

    def test_bootstrap_tem_semente_deterministica_e_mais_de_tres_dias(self):
        a, b = relatorio_drift_segmentado(exemplo()), relatorio_drift_segmentado(exemplo())
        self.assertEqual(a["resumo"]["bootstrap_brier"], b["resumo"]["bootstrap_brier"])
        self.assertIsNotNone(a["resumo"]["bootstrap_brier"]["ci95_low"])


if __name__ == "__main__":
    unittest.main()
