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
                        "top5_oos_n": 12,
                        "top5_champion": {"n": 12, "brier": 0.20, "gap_pp": -1.0},
                        "top5_challenger": {"n": 12, "brier": 0.18, "gap_pp": 0.5},
                        "top5_delta_brier": -0.02,
                        "top5_bootstrap_delta_brier": {
                            "n": 12,
                            "delta": -0.02,
                            "ci95_low": -0.04,
                            "ci95_high": -0.01,
                        },
                    }
                },
                "drift": {
                    "n": 40,
                    "estado": "ALTO",
                    "base": {"n": 24, "snapshot_min": 1, "snapshot_max": 24},
                    "recente": {"n": 16, "snapshot_min": 25, "snapshot_max": 40},
                    "numeric_details": {
                        "lambda_total": {
                            "psi": 0.31,
                            "estado": "ALTO",
                            "base_media": 2.3,
                            "recente_media": 2.8,
                        }
                    },
                    "categorical": {
                        "mercado": {
                            "tv_distance": 0.15,
                            "estado": "MODERADO",
                            "top_mudancas": [
                                {
                                    "categoria": "Under 3.5 Golos",
                                    "base_pct": 25.0,
                                    "recente_pct": 40.0,
                                    "delta_pp": 15.0,
                                }
                            ],
                        }
                    },
                },
                "drift_segmentado": {
                    "estado": "DESCRITIVO", "n": 40,
                    "resumo": {
                        "base": {"n": 24, "snapshot_min": 1, "snapshot_max": 24,
                                 "metricas": {"brier": 0.24, "gap_pp": -3.1}},
                        "recente": {"n": 16, "snapshot_min": 25, "snapshot_max": 40,
                                    "metricas": {"brier": 0.25, "gap_pp": -2.1}},
                        "bootstrap_brier": {"delta_brier": 0.01, "ci95_low": -0.02,
                                            "ci95_high": 0.03, "dias_base": 5, "dias_recente": 4},
                    },
                    "por_mercado": {
                        "n_segmentos_elegiveis": 1,
                        "base_coberta_pct": 50, "recente_coberta_pct": 70,
                        "brier_mix_base": {"base": 0.24, "recente": 0.25, "delta": 0.01},
                        "segmentos": [{"segmento": "Under 3.5 Golos", "base_n": 12, "recente_n": 11,
                                       "brier_base": 0.24, "brier_recente": 0.25,
                                       "features": {"lambda_total": {"delta_media": -0.4}}}],
                    },
                    "por_liga": {"n_segmentos_elegiveis": 0, "base_coberta_pct": 0,
                                 "recente_coberta_pct": 0, "brier_mix_base": None, "segmentos": []},
                    "por_liga_mercado": {"n_segmentos_elegiveis": 0, "base_coberta_pct": 0,
                                        "recente_coberta_pct": 0, "brier_mix_base": None, "segmentos": []},
                },
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
        drift = bot._executar_lab_drift()
        segmentado = bot._executar_lab_drift_segmentado()
        top5 = bot._executar_lab_top5()

        self.assertIn("ACEITE", export)
        self.assertIn("CHAMPION", status)
        self.assertIn("platt_calibration_v1", status)
        self.assertIn("MLflow", status)
        self.assertIn("DRIFT DETALHADO", drift)
        self.assertIn("DRIFT SEGMENTADO", segmentado)
        self.assertIn("Under 3.5 Golos", segmentado)
        self.assertIn("Brier mix-base", segmentado)
        self.assertIn("Lambda total", drift)
        self.assertIn("Under 3.5 Golos", drift)
        self.assertIn("TOP5 OOS", top5)
        self.assertIn("melhoria consistente", top5)
        self.assertEqual(bot.previsoes.dados, antes)


    def test_drift_segmentado_so_owner_admin(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = 999
        bot.chat_id = -100
        bot.username = "TesteBot"
        bot.previsoes = PrevisoesFake()
        bot.research_lab = LabFake()
        mensagens = []
        bot.enviar_mensagem = lambda chat_id, texto: mensagens.append((chat_id, texto))

        bot.processar_comando(-100, "/lab_drift_segmentado", user_id=998)
        self.assertEqual(mensagens, [])
        bot.processar_comando(-100, "/lab_drift_segmentado", user_id=999)
        self.assertEqual(len(mensagens), 1)
        self.assertIn("DRIFT SEGMENTADO", mensagens[0][1])


if __name__ == "__main__":
    unittest.main()
