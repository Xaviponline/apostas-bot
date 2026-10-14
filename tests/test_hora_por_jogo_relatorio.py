"""Regressoes do horario por jogo no relatorio /analisa (apresentacao apenas)."""
import copy
import unittest

from analisador_inteligente import AnalisadorInteligente


def selecao(identificador, hora):
    return {
        "jogo": {
            "id": identificador,
            "casa": f"Equipa Casa {identificador}",
            "fora": f"Equipa Fora {identificador}",
            "liga": "UEFA Champions League",
            "horario": hora,
        },
        "mercado": "Ambas Marcam",
        "probabilidade": 0.65,
        "odd_justa": 1.0 / 0.65,
        "odd_minima": 1.05 / 0.65,
        "qualidade": 80,
        "ranking_modelo": identificador,
        "confianca": "MÉDIA-ALTA",
    }


class HorarioPorJogoRelatorioTests(unittest.TestCase):
    def setUp(self):
        self.analisador = AnalisadorInteligente()

    def relatorio(self, selecoes):
        self.analisador.ultimo_resumo = {
            "jogos": len(selecoes),
            "com_dados": len(selecoes),
            "selecoes": len(selecoes),
        }
        return self.analisador.gerar_relatorio([], selecoes=selecoes)

    def test_horario_em_cada_selecao_mesmo_na_mesma_hora(self):
        itens = [selecao(1, "20:00"), selecao(2, "20:00")]
        original = copy.deepcopy(itens)
        texto = self.relatorio(itens)

        self.assertEqual(texto.count("⏰ 20:00 — JOGOS"), 1)
        self.assertEqual(texto.count("🕒 Início: 20:00 (Portugal)"), 2)
        self.assertIn("Ranking modelo: #1", texto)
        self.assertIn("Ranking modelo: #2", texto)
        self.assertEqual(itens, original)  # Formatar nao altera selecoes/snapshots.

    def test_horarios_distintos_continuam_agrupados(self):
        texto = self.relatorio([selecao(1, "19:45"), selecao(2, "20:00")])

        self.assertIn("🕒 Início: 19:45 (Portugal)", texto)
        self.assertIn("🕒 Início: 20:00 (Portugal)", texto)
        self.assertLess(texto.index("🕒 Início: 19:45"), texto.index("🕒 Início: 20:00"))

    def test_hora_indisponivel_nao_e_inventada(self):
        texto = self.relatorio([selecao(1, "")])

        self.assertIn("🕒 Início: hora indisponível", texto)
        self.assertNotIn("🕒 Início: --:--", texto)


if __name__ == "__main__":
    unittest.main()
