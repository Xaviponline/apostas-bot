import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from main_competicoes import BotPremiumDiarioCompeticoes
from previsoes_premium import RegistoPrevisoes


class V13ComercialTests(unittest.TestCase):
    @staticmethod
    def selecao(event_id, ranking, odd, inicio, dias=0, minima=1.75):
        ts = (inicio + timedelta(days=dias)).timestamp()
        return {
            "jogo": {
                "id": event_id,
                "casa": f"Casa {event_id}",
                "fora": f"Fora {event_id}",
                "liga": "Liga Teste",
                "timestamp": ts,
            },
            "mercado": "Vitória Casa",
            "probabilidade": 0.60,
            "probabilidade_bruta": 0.62,
            "qualidade": 80,
            "odd_justa": 1.6667,
            "odd_minima": minima,
            "odd_real": odd,
            "ranking_modelo": ranking,
            "confianca": "MÉDIA",
            "score": 0.60,
        }

    @staticmethod
    def liquidar(p, ganhou, fecho=None):
        p["resultado_binario"] = 1 if ganhou else 0
        p["estado"] = "ganhou" if ganhou else "perdeu"
        if fecho is not None:
            p["odd_fecho"] = fecho

    def test_gate_usa_apenas_top5_value_pos_inicio_e_coorte_fixa(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            reg.V13_COMERCIAL_START_SNAPSHOT = 3
            reg.V13_COMERCIAL_TARGET = 4
            reg.V13_COMERCIAL_MIN_DIAS = 2
            reg.V13_COMERCIAL_MIN_CLV_AMOSTRAS = 3
            inicio = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)

            reg.registar([
                self.selecao(1, 1, 2.00, inicio, 0),  # pré-teste
                self.selecao(2, 2, 2.00, inicio, 0),  # pré-teste
                self.selecao(3, 1, 2.00, inicio, 0),
                self.selecao(4, 2, 1.80, inicio, 0),
                self.selecao(5, 5, 1.90, inicio, 1),
                self.selecao(6, 4, 2.20, inicio, 1),
                self.selecao(7, 3, 2.30, inicio, 2),  # elegível mas fora das primeiras 4
                self.selecao(8, 6, 2.50, inicio, 2),  # fora Top5
                self.selecao(9, 1, 1.50, inicio, 2),  # Top5, mas sem VALUE
            ])

            ps = reg.dados["previsoes"]
            self.liquidar(ps[2], True, 1.90)
            self.liquidar(ps[3], True, 1.70)
            self.liquidar(ps[4], False, 1.80)
            self.liquidar(ps[5], True, None)
            self.liquidar(ps[6], False, 2.00)
            self.liquidar(ps[7], True, 2.00)
            self.liquidar(ps[8], True, 1.40)

            antes = copy.deepcopy(reg.dados)
            m = reg.metricas_v13_comercial()

            self.assertEqual(m["top5_monitorizadas"], 6)
            self.assertEqual(m["elegiveis_total"], 5)
            self.assertEqual(m["coorte_tamanho"], 4)
            self.assertEqual([x["snapshot"] for x in m["coorte"]], [3, 4, 5, 6])
            self.assertEqual(m["liquidadas"], 4)
            self.assertEqual(m["dias"], 2)
            self.assertEqual(m["clv_amostras"], 3)
            self.assertGreater(m["roi"], 0)
            self.assertGreater(m["clv_media"], 0)
            self.assertEqual(m["estado"], "PASSOU")
            self.assertTrue(all(m["regras"].values()))
            self.assertEqual(reg.dados, antes)

    def test_primeira_coorte_nao_e_estendida_para_cumprir_dias(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            reg.V13_COMERCIAL_START_SNAPSHOT = 1
            reg.V13_COMERCIAL_TARGET = 3
            reg.V13_COMERCIAL_MIN_DIAS = 2
            reg.V13_COMERCIAL_MIN_CLV_AMOSTRAS = 2
            inicio = datetime(2030, 2, 1, 12, tzinfo=timezone.utc)

            reg.registar([
                self.selecao(10, 1, 2.00, inicio, 0),
                self.selecao(11, 2, 2.00, inicio, 0),
                self.selecao(12, 3, 2.00, inicio, 0),
                self.selecao(13, 4, 2.00, inicio, 1),
            ])
            for p in reg.dados["previsoes"]:
                self.liquidar(p, True, 1.90)

            m = reg.metricas_v13_comercial()
            self.assertEqual([x["snapshot"] for x in m["coorte"]], [1, 2, 3])
            self.assertEqual(m["dias"], 1)
            self.assertEqual(m["estado"], "NAO_PASSOU")
            self.assertFalse(m["regras"]["dias_20"])

    def test_relatorio_e_apenas_leitura(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            reg.V13_COMERCIAL_START_SNAPSHOT = 1
            reg.V13_COMERCIAL_TARGET = 2
            reg.V13_COMERCIAL_MIN_DIAS = 2
            reg.V13_COMERCIAL_MIN_CLV_AMOSTRAS = 2
            inicio = datetime(2030, 3, 1, 12, tzinfo=timezone.utc)
            reg.registar([
                self.selecao(20, 1, 2.00, inicio, 0),
                self.selecao(21, 2, 1.50, inicio, 1),
            ])
            bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
            bot.previsoes = reg
            antes = copy.deepcopy(reg.dados)

            texto = bot._executar_v13_comercial()

            self.assertIn("V1.3 COMERCIAL", texto)
            self.assertIn("Entradas VALUE confirmadas: 1/2", texto)
            self.assertIn("EM RECOLHA", texto)
            self.assertEqual(reg.dados, antes)


if __name__ == "__main__":
    unittest.main()
