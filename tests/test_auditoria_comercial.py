import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from previsoes_premium import RegistoPrevisoes


class AuditoriaComercialTests(unittest.TestCase):
    @staticmethod
    def _selecao(event_id, odd_real=None, timestamp=1893528000):
        selecao = {
            "jogo": {
                "id": event_id,
                "casa": f"Casa {event_id}",
                "fora": f"Fora {event_id}",
                "liga": "Liga Teste",
                "timestamp": timestamp,
            },
            "mercado": "Vitória Casa",
            "probabilidade": 0.60,
            "probabilidade_bruta": 0.62,
            "qualidade": 80,
            "odd_justa": 1.6667,
            "odd_minima": 1.75,
            "ranking_modelo": 2,
            "confianca": "MÉDIA",
            "score": 0.60,
        }
        if odd_real is not None:
            selecao.update(
                {
                    "odd_real": odd_real,
                    "odds_fonte": "Fonte Teste",
                    "odds_event_id": str(event_id),
                    "odds_atualizada_em": "2030-01-01T18:00:00Z",
                }
            )
        return selecao

    def test_snapshot_novo_fica_selado_e_adulteracao_e_detetada(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            reg.registar([self._selecao(1, 1.80)])

            p = reg.dados["previsoes"][0]
            self.assertIn("snapshot_hash", p)
            self.assertEqual(reg.verificar_integridade()["validos"], 1)
            self.assertEqual(reg.verificar_integridade()["divergentes"], 0)

            p["probabilidade"] = 0.99
            integridade = reg.verificar_integridade()
            self.assertEqual(integridade["divergentes"], 1)

    def test_historico_legado_nao_e_retro_selado(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            reg.dados["previsoes"].append(
                {
                    "event_id": 99,
                    "mercado": "Under 2.5 Golos",
                    "modelo_versao": "V1.2",
                }
            )

            integridade = reg.verificar_integridade()
            self.assertEqual(integridade["legados_sem_hash"], 1)
            self.assertEqual(integridade["protegidos"], 0)

    def test_valor_pode_expirar_sem_reescrever_odd_inicial_ou_modelo(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            kickoff = datetime(2030, 1, 1, 20, 0, tzinfo=timezone.utc).timestamp()
            reg.registar([self._selecao(2, 1.80, timestamp=kickoff)])
            p = reg.dados["previsoes"][0]
            prob_inicial = p["probabilidade"]
            hash_inicial = p["snapshot_hash"]

            self.assertEqual(p["valor_estado"], "confirmado")
            self.assertEqual(p["odd_valor_confirmado"], 1.8)

            atual = self._selecao(2, 1.60, timestamp=kickoff)
            resumo = reg.atualizar_estado_mercado(
                [atual],
                agora=datetime(2030, 1, 1, 19, 40, tzinfo=timezone.utc),
            )

            p = reg.dados["previsoes"][0]
            self.assertEqual(resumo["expirados_novos"], 1)
            self.assertEqual(resumo["fechos_capturados"], 1)
            self.assertEqual(p["valor_estado"], "expirado")
            self.assertEqual(p["odd_real"], 1.8)
            self.assertEqual(p["odd_mercado_atual"], 1.6)
            self.assertEqual(p["odd_fecho"], 1.6)
            self.assertAlmostEqual(p["clv_odds"], (1.8 / 1.6) - 1.0, places=6)
            self.assertEqual(p["probabilidade"], prob_inicial)
            self.assertEqual(p["snapshot_hash"], hash_inicial)
            self.assertEqual(reg.verificar_integridade()["divergentes"], 0)

    def test_carteira_shadow_so_usa_odds_que_atingiram_minima(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            reg.registar(
                [
                    self._selecao(10, 2.00),
                    self._selecao(11, 1.80),
                    self._selecao(12, 1.50),
                ]
            )
            p1, p2, p3 = reg.dados["previsoes"]
            p1["resultado_binario"] = 1
            p1["estado"] = "ganhou"
            p2["resultado_binario"] = 0
            p2["estado"] = "perdeu"
            p3["resultado_binario"] = 1
            p3["estado"] = "ganhou"

            m = reg.metricas_carteira_valor()
            self.assertEqual(m["elegiveis"], 2)
            self.assertEqual(m["liquidadas"], 2)
            self.assertEqual(m["ganhos"], 1)
            self.assertEqual(m["perdas"], 1)
            self.assertAlmostEqual(m["lucro_unidades"], 0.0)
            self.assertAlmostEqual(m["roi"], 0.0)
            self.assertAlmostEqual(m["max_drawdown"], 1.0)
            self.assertEqual(m["max_streak_perdas"], 1)


if __name__ == "__main__":
    unittest.main()
