import copy
import hashlib
import json
import unittest

from main_competicoes import BotPremiumDiarioCompeticoes
from research_export import construir_payload_research


class PrevisoesFake:
    def __init__(self):
        self.dados = {
            "previsoes": [
                {
                    "chave": "1|Under 3.5 Golos",
                    "event_id": 1,
                    "data_jogo": "2026-10-09",
                    "mercado": "Under 3.5 Golos",
                    "modelo_versao": "V1.2",
                    "ranking_modelo": 1,
                    "probabilidade": 0.66,
                    "probabilidade_bruta": 0.70,
                    "resultado_binario": 1,
                    "diagnostico_modelo": {
                        "versao": 1,
                        "lambda_casa": 1.2,
                        "lambda_fora": 1.0,
                    },
                    "snapshot_hash": "abc",
                    # Nunca pode sair no export:
                    "user_id": 999,
                    "telegram_token": "segredo",
                    "password": "segredo",
                }
            ]
        }


class LabFake:
    configurado = True

    def __init__(self):
        self.recebidas = None

    def exportar(self, previsoes):
        self.recebidas = copy.deepcopy(previsoes)
        return {
            "accepted": True,
            "records": len(previsoes),
            "sha256": "a" * 64,
        }

    def status(self):
        return {
            "dataset": {"records": 1, "sha256": "a" * 64},
            "analysis_running": False,
            "report": {
                "champion": {
                    "total": {"n": 1, "brier": 0.1156, "gap_pp": 34.0},
                    "top5": {"n": 1, "brier": 0.1156, "gap_pp": 34.0},
                },
                "challengers": {
                    "platt_calibration_v1": {
                        "estado": "SHADOW",
                        "oos_n": 31,
                        "challenger": {"brier": 0.11, "gap_pp": 2.0},
                        "delta_brier": -0.0056,
                    }
                },
                "drift": {"estado": "ESTAVEL"},
                "mlflow": {"logged": True, "run_id": "1234567890abcdef"},
            },
        }


class ResearchExportTests(unittest.TestCase):
    def test_payload_e_sanitizado_hashado_e_origem_nao_muda(self):
        previsoes = PrevisoesFake().dados["previsoes"]
        antes = copy.deepcopy(previsoes)

        payload = construir_payload_research(previsoes)

        self.assertEqual(previsoes, antes)
        self.assertEqual(payload["records_count"], 1)
        item = payload["records"][0]
        self.assertEqual(item["snapshot_index"], 1)
        self.assertIn("diagnostico_modelo", item)
        self.assertNotIn("user_id", item)
        self.assertNotIn("telegram_token", item)
        self.assertNotIn("password", item)

        canon = json.dumps(
            payload["records"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(payload["records_sha256"], hashlib.sha256(canon).hexdigest())

    def test_comandos_lab_sao_apenas_leitura(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.previsoes = PrevisoesFake()
        bot.research_lab = LabFake()
        antes = copy.deepcopy(bot.previsoes.dados)

        export = bot._executar_lab_export()
        status = bot._executar_lab_status()

        self.assertIn("ACEITE", export)
        self.assertIn("CHAMPION", status)
        self.assertIn("platt_calibration_v1", status)
        self.assertIn("MLflow", status)
        self.assertEqual(bot.previsoes.dados, antes)


if __name__ == "__main__":
    unittest.main()
