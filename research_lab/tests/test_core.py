import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from research_export import construir_payload_research
from research_lab.config import LabConfig
from research_lab.dataset import dataframe_from_payload, validar_payload
from research_lab.models import _splits_temporais
from research_lab.runner import executar_experimento


def registos_sinteticos(n=90):
    saida = []
    mercados = ["Under 3.5 Golos", "Over 2.5 Golos", "Ambas Marcam", "Vitória Casa"]
    for i in range(n):
        p = 0.56 + (i % 10) * 0.015
        bruto = min(p + 0.03, 0.89)
        y = 0 if i % 3 == 0 else 1
        lc = 0.9 + (i % 5) * 0.18
        lf = 0.8 + (i % 4) * 0.16
        pc = 1.0 + (i % 6) * 0.15
        pf = 0.9 + (i % 5) * 0.13
        saida.append(
            {
                "chave": f"{i}|{mercados[i % len(mercados)]}",
                "event_id": i + 1,
                "data_jogo": f"2026-09-{1 + (i // 5):02d}",
                "timestamp_jogo": 1800000000 + i * 3600,
                "casa": f"Casa {i}",
                "fora": f"Fora {i}",
                "liga": "Liga Teste",
                "mercado": mercados[i % len(mercados)],
                "modelo_versao": "V1.2",
                "ranking_modelo": (i % 20) + 1,
                "score_modelo": p,
                "probabilidade": p,
                "probabilidade_bruta": bruto,
                "qualidade": 70 + (i % 25),
                "odd_justa": 1 / p,
                "odd_minima": (1 / p) * 1.05,
                "estado": "ganhou" if y else "perdeu",
                "resultado_binario": y,
                "diagnostico_modelo": {
                    "versao": 1,
                    "margem_limite": p - 0.56,
                    "lambda_casa": lc,
                    "lambda_fora": lf,
                    "ppg_casa": pc,
                    "ppg_fora": pf,
                    "amostra_casa_local": 4 + (i % 3),
                    "amostra_fora_local": 3 + (i % 4),
                    "media_liga_casa": 1.4,
                    "media_liga_fora": 1.2,
                },
            }
        )
    return saida


class ResearchLabCoreTests(unittest.TestCase):
    def test_dataset_valida_hash_e_features_derivadas(self):
        payload = construir_payload_research(registos_sinteticos(10))
        validar_payload(payload)
        df = dataframe_from_payload(payload)

        self.assertEqual(len(df), 10)
        self.assertAlmostEqual(df.iloc[0]["lambda_total"], 1.7)
        self.assertAlmostEqual(df.iloc[0]["lambda_diff"], 0.1)
        self.assertTrue(bool(df.iloc[0]["top5"]))

        estragado = json.loads(json.dumps(payload))
        estragado["records"][0]["probabilidade"] = 0.99
        with self.assertRaises(ValueError):
            validar_payload(estragado)

    def test_walk_forward_nunca_treina_no_futuro(self):
        splits = list(_splits_temporais(90, 60, 10))
        self.assertEqual(len(splits), 3)
        for treino, teste in splits:
            self.assertLess(max(treino), min(teste))
            self.assertEqual(min(treino), 0)

    def test_runner_champion_challenger_e_governance(self):
        payload = construir_payload_research(registos_sinteticos(90))
        with tempfile.TemporaryDirectory() as tmp:
            cfg = LabConfig(
                ingest_token="teste",
                s3_endpoint="",
                s3_bucket="",
                s3_region="auto",
                s3_access_key_id="",
                s3_secret_access_key="",
                mlflow_tracking_uri="",
                experiment_name="teste",
                local_dir=tmp,
                optuna_trials=4,
            )
            report = executar_experimento(payload, cfg)

        self.assertEqual(report["champion"]["total"]["n"], 90)
        self.assertEqual(report["challengers"]["platt_calibration_v1"]["oos_n"], 30)
        self.assertEqual(report["challengers"]["meta_logit_v1"]["oos_n"], 40)
        self.assertFalse(report["governance"]["auto_promotion"])
        self.assertTrue(report["governance"]["walk_forward_only"])


if __name__ == "__main__":
    unittest.main()
