import copy
import tempfile
import unittest
from pathlib import Path

from main_competicoes import BotPremiumDiarioCompeticoes
from main_diario import RegistoPrevisoesDiario
from main_sofascore import AJUDA


class V13Top5ShadowTests(unittest.TestCase):
    @staticmethod
    def _p(indice, resultado, ranking, data="2026-09-27", prob=0.66):
        return {
            "chave": f"{indice}|Under 3.5 Golos",
            "event_id": indice,
            "data_jogo": data,
            "timestamp_jogo": 1790500000 + indice,
            "casa": f"Casa {indice}",
            "fora": f"Fora {indice}",
            "liga": "English League One",
            "mercado": "Under 3.5 Golos",
            "modelo_versao": "V1.2",
            "ranking_modelo": ranking,
            "confianca_modelo": "MÉDIA-ALTA",
            "probabilidade": prob,
            "probabilidade_bruta": 0.70,
            "qualidade": 81,
            "odd_justa": 1.0 / prob,
            "odd_minima": 1.05 / prob,
            "criada_em": "2026-09-27T00:05:00Z",
            "estado": "liquidada" if resultado in (0, 1) else "pendente",
            "resultado_binario": resultado,
        }

    def _desenvolvimento(self):
        previsoes = []
        for i in range(59):
            ranking = (i % 20) + 1
            if ranking <= 5:
                resultado = 1 if i % 4 != 0 else 0
            else:
                resultado = 1 if i % 2 == 0 else 0
            previsoes.append(
                self._p(i + 1, resultado, ranking, data="2026-09-26")
            )
        return previsoes

    def test_top5_so_avalia_a_partir_do_snapshot_60_e_e_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            previsoes = self._desenvolvimento()
            previsoes.extend(
                [
                    self._p(60, 1, 1),
                    self._p(61, 1, 2),
                    self._p(62, 0, 3),
                    self._p(63, 0, 8),
                    self._p(64, 0, 12),
                    self._p(65, 1, 18),
                ]
            )
            reg.dados = {"versao": 1, "previsoes": previsoes}
            antes = copy.deepcopy(reg.dados)

            texto = reg.relatorio_v13_shadow_top5()

            self.assertIn("V1.3-SHADOW-SEL1-TOP5", texto)
            self.assertIn("A partir do snapshot #60", texto)
            self.assertIn("Registadas: 6", texto)
            self.assertIn("Top 5 liquidadas: 3", texto)
            self.assertIn("Top 5 OOS: 3/25", texto)
            self.assertEqual(reg.dados, antes)

    def test_top5_sem_dados_prospetivos_nao_reusa_historico_no_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            reg.dados = {"versao": 1, "previsoes": self._desenvolvimento()}

            texto = reg.relatorio_v13_shadow_top5()

            self.assertIn("RACIONAL HISTÓRICO — NÃO É TESTE", texto)
            self.assertIn("Registadas: 0", texto)
            self.assertIn("Top 5 OOS: 0/25", texto)
            self.assertIn("não contam no gate prospetivo", texto.lower())

    def test_gate_top5_sem_comparador_fica_pendente_e_nao_falhado(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            previsoes = self._desenvolvimento()
            previsoes.extend(
                [
                    self._p(60, 1, 1),
                    self._p(61, 1, 2),
                    self._p(62, 0, 3),
                ]
            )
            reg.dados = {"versao": 1, "previsoes": previsoes}

            texto = reg.relatorio_v13_shadow_top5()

            self.assertIn("Hit rate ≥5pp acima de #6–20: ⏳", texto)
            self.assertIn("Brier melhor que #6–20: ⏳", texto)
            self.assertIn(
                "Comparador #6–20: ainda sem previsões prospetivas liquidadas.",
                texto,
            )

    def test_gate_top5_exige_amostra_dias_e_superioridade(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            previsoes = self._desenvolvimento()

            idx = 60
            for dia in range(5):
                data = f"2026-10-{dia + 1:02d}"
                for rank in range(1, 6):
                    previsoes.append(self._p(idx, 1 if rank <= 4 else 0, rank, data))
                    idx += 1
                for rank in range(6, 11):
                    previsoes.append(self._p(idx, 1 if rank == 6 else 0, rank, data))
                    idx += 1

            reg.dados = {"versao": 1, "previsoes": previsoes}
            texto = reg.relatorio_v13_shadow_top5()

            self.assertIn("Top 5 OOS: 25/25 ✅", texto)
            self.assertIn("Dias: 5/5 ✅", texto)
            self.assertIn("Hit rate ≥5pp acima de #6–20: ✅", texto)
            self.assertIn("Brier melhor que #6–20: ✅", texto)

    def test_comando_top5_so_admin_e_ajuda(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            reg.dados = {"versao": 1, "previsoes": self._desenvolvimento()}

            bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
            bot.owner_id = 999
            bot.chat_id = -100
            bot.username = "TesteBot"
            bot.previsoes = reg
            mensagens = []
            bot.enviar_mensagem = lambda chat_id, texto: mensagens.append((chat_id, texto))

            bot.processar_comando(-100, "/v13_top5", user_id=999)
            self.assertEqual(len(mensagens), 1)
            self.assertIn("V1.3-SHADOW-SEL1-TOP5", mensagens[0][1])

            mensagens.clear()
            bot.processar_comando(-100, "/v13_top5", user_id=998)
            self.assertEqual(mensagens, [])
            self.assertIn("/v13_top5", AJUDA)


if __name__ == "__main__":
    unittest.main()
