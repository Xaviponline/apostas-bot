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
            self.assertIn("Top 5 do checkpoint: 3/40", texto)
            self.assertEqual(reg.dados, antes)

    def test_top5_sem_dados_prospetivos_nao_reusa_historico_no_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            reg.dados = {"versao": 1, "previsoes": self._desenvolvimento()}

            texto = reg.relatorio_v13_shadow_top5()

            self.assertIn("RACIONAL HISTÓRICO — NÃO É TESTE", texto)
            self.assertIn("Registadas: 0", texto)
            self.assertIn("Top 5 do checkpoint: 0/40", texto)
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

    def test_checkpoint25_fica_encerrado_e_nao_promove_antes_de_40(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            previsoes = self._desenvolvimento()

            idx = 60
            # Reproduz o checkpoint real: 25 Top5, 19 acertos, e 26 comparadores.
            for n in range(25):
                previsoes.append(
                    self._p(
                        idx,
                        1 if n < 19 else 0,
                        (n % 5) + 1,
                        data=f"2026-10-{(n // 5) + 1:02d}",
                        prob=0.671,
                    )
                )
                idx += 1
            for n in range(26):
                previsoes.append(
                    self._p(
                        idx,
                        1 if n < 13 else 0,
                        6 + (n % 15),
                        data=f"2026-10-{(n // 5) + 1:02d}",
                        prob=0.625,
                    )
                )
                idx += 1

            reg.dados = {"versao": 1, "previsoes": previsoes}
            texto = reg.relatorio_v13_shadow_top5()

            self.assertIn("🔐 CHECKPOINT 25 — ENCERRADO", texto)
            self.assertIn("Top 5: 19/25 (76.0%)", texto)
            self.assertIn("Calibração ≤8pp: ❌", texto)
            self.assertIn("Estado: ❌ NÃO PROMOVIDA no checkpoint 25.", texto)
            self.assertIn("Top 5 do checkpoint: 25/40 ⏳", texto)
            self.assertIn("Sem decisão antes das 40 Top 5", texto)

    def test_gate_checkpoint40_exige_calibracao_dias_e_superioridade(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            previsoes = self._desenvolvimento()

            idx = 60
            top5_criadas = 0
            restantes_criadas = 0
            for dia in range(8):
                data = f"2026-11-{dia + 1:02d}"
                for rank in range(1, 6):
                    resultado = 1 if top5_criadas < 27 else 0
                    previsoes.append(self._p(idx, resultado, rank, data, prob=0.66))
                    idx += 1
                    top5_criadas += 1
                for rank in range(6, 11):
                    resultado = 1 if restantes_criadas < 10 else 0
                    previsoes.append(self._p(idx, resultado, rank, data, prob=0.62))
                    idx += 1
                    restantes_criadas += 1

            reg.dados = {"versao": 1, "previsoes": previsoes}
            texto = reg.relatorio_v13_shadow_top5()

            self.assertIn("Top 5 do checkpoint: 40/40 ✅", texto)
            self.assertIn("Top 5 checkpoint: 27/40 (67.5%)", texto)
            self.assertIn("|Gap calibração| ≤8pp: ✅", texto)
            self.assertIn("Hit rate ≥5pp acima de #6–20: ✅", texto)
            self.assertIn("Brier melhor que #6–20: ✅", texto)
            self.assertIn("CHECKPOINT 40 PASSOU", texto)

    def test_checkpoint40_nao_e_reaberto_por_resultados_posteriores(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoesDiario(Path(tmp) / "previsoes.json")
            previsoes = self._desenvolvimento()

            idx = 60
            # Primeiros 40 Top5: 20/40, insuficiente para passar.
            for n in range(40):
                previsoes.append(
                    self._p(idx, 1 if n < 20 else 0, (n % 5) + 1, data="2026-12-01", prob=0.66)
                )
                idx += 1
                previsoes.append(
                    self._p(idx, 1 if n < 10 else 0, 6 + (n % 15), data="2026-12-01", prob=0.62)
                )
                idx += 1

            # Cinco Top5 posteriores ganham todos, mas não podem alterar o checkpoint fixo.
            for n in range(5):
                previsoes.append(
                    self._p(idx, 1, (n % 5) + 1, data="2026-12-02", prob=0.66)
                )
                idx += 1

            reg.dados = {"versao": 1, "previsoes": previsoes}
            texto = reg.relatorio_v13_shadow_top5()

            self.assertIn("Top 5 live: 25/45", texto)
            self.assertIn("Top 5 checkpoint: 20/40 (50.0%)", texto)
            self.assertIn("CHECKPOINT 40 FALHOU", texto)
            self.assertIn("Resultados posteriores não reabrem este gate", texto)

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
