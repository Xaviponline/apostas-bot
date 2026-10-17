"""Testes da apresentação /analisa, independente de odds e snapshots."""
import copy
import unittest
from datetime import datetime, timedelta, timezone

from analisador_inteligente import AnalisadorInteligente


def selecao(rank, hora, odd=None, minima=1.52, prob=0.69, alertas=None):
    return {
        "jogo": {
            "id": rank + 10000, "horario": hora,
            "casa": f"Casa {rank}", "fora": f"Fora {rank}",
            "liga": "English League One",
        },
        "ranking_modelo": rank,
        "mercado": "Under 2.5 Golos",
        "probabilidade": prob,
        "odd_justa": 1.0 / prob,
        "odd_minima": minima,
        "odd_real": odd,
        "confianca": "ALTA",
        "qualidade": 90,
        "_odds_alertas": alertas or [],
    }


class AnalisaVitrinePremiumTests(unittest.TestCase):
    def _relatorio(self, selecoes):
        analisador = AnalisadorInteligente()
        analisador.ultimo_resumo = {
            "jogos": 140, "com_dados": 27, "selecoes": len(selecoes)
        }
        antes = copy.deepcopy(selecoes)
        texto = analisador.gerar_relatorio([], selecoes=selecoes)
        self.assertEqual(selecoes, antes)
        return texto

    def test_destaca_value_sem_ocultar_sem_valor_e_sem_odd(self):
        selecoes = [
            selecao(15, "15:00", 1.60, 1.53, 0.685),
            selecao(2, "15:00", None, 1.51),
            selecao(3, "12:30", 2.02, 1.51, 0.696),
            selecao(12, "12:30", 1.50, 1.53, 0.687),
        ]
        texto = self._relatorio(selecoes)
        self.assertIn("4 SUGESTÕES DO MODELO", texto)
        self.assertIn("💎 2 odds ≥ mínimo", texto)
        self.assertIn("🟡 1 sem odd", texto)
        self.assertIn("🔴 1 abaixo do mínimo", texto)
        self.assertIn("Casa 3 vs Fora 3", texto)
        self.assertIn("🏅 RANKING #3", texto)
        self.assertIn("Odd registada 2,02", texto)
        self.assertIn("Mínima ≥ 1,51", texto)
        self.assertIn("⚠️ PREÇO/EV INVULGAR", texto)
        self.assertIn("PREÇO ABAIXO DO MÍNIMO", texto)
        self.assertIn("⚖️ Odd justa", texto)
        self.assertIn("não cotações em direto", texto)
        # O topo tem sempre o critério de preço, independente do horário.
        self.assertLess(texto.index("Casa 3"), texto.index("Casa 2"))
        self.assertLess(texto.index("Casa 2"), texto.index("Casa 12"))
        self.assertLess(texto.index("Casa 3"), texto.index("Casa 15"))

    def test_preco_maior_que_minimo_nao_e_aposta_garantida(self):
        texto = self._relatorio([selecao(1, "17:00", 1.62, 1.50, 0.66)])
        self.assertIn("1 SUGESTÃO DO MODELO", texto)
        self.assertIn("🟢 VALOR CONFIRMADO", texto)
        self.assertNotIn("⚠️ PREÇO/EV INVULGAR", texto)
        self.assertIn("não comprova vantagem estatística", texto)

    def test_alerta_contexto_dispara_cautela_visivel(self):
        texto = self._relatorio([
            selecao(5, "19:00", 1.70, 1.55, 0.66, ["competicao_divergente"])
        ])
        self.assertIn("⚠️ PREÇO/EV INVULGAR", texto)
        self.assertNotIn("🟢 VALOR CONFIRMADO", texto)

    def test_odd_nao_finita_nao_confirma_preco(self):
        texto = self._relatorio([selecao(4, "15:00", float("nan"))])
        self.assertIn("🟡 1 sem odd", texto)
        self.assertNotIn("Odd registada nan", texto)

    def test_jogos_ja_iniciados_nao_sao_apresentados_como_oportunidades(self):
        passado = selecao(3, "12:30", 2.02, 1.51, 0.696)
        passado["jogo"]["timestamp"] = (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()
        futuro = selecao(8, "15:15", 1.72, 1.52, 0.691)
        futuro["jogo"]["timestamp"] = (datetime.now(timezone.utc) + timedelta(hours=3)).timestamp()
        texto = self._relatorio([passado, futuro])
        self.assertIn("2 SUGESTÕES DO MODELO", texto)
        self.assertIn("🕒 1 por começar  ·  ⛔ 1 já iniciados", texto)
        self.assertIn("💎 1 odds ≥ mínimo", texto)
        self.assertIn("JOGOS JÁ INICIADOS — HISTÓRICO (1)", texto)
        self.assertIn("⛔ JÁ INICIADO", texto)
        self.assertLess(texto.index("Casa 8"), texto.index("Casa 3"))
        # A odd histórica não entra no contador VALUE para os jogos futuros.
        self.assertIn("Odds observadas em jogos futuros: 1/1", texto)

    def test_maximo_por_execucao_nao_se_confunde_com_total_diario(self):
        entradas = [selecao(i, "15:00", None) for i in range(1, 21)]
        extras = [selecao(19, "19:30", None), selecao(20, "21:30", 1.39, 1.54)]
        extras[0]["jogo"]["id"] = 100999
        extras[0]["jogo"]["casa"] = "Ronda posterior A"
        extras[1]["jogo"]["id"] = 101000
        extras[1]["jogo"]["casa"] = "Ronda posterior B"
        texto = self._relatorio(entradas + extras)
        self.assertIn("22 SUGESTÕES DO MODELO", texto)
        self.assertIn("máximo de 20 por execução", texto)
        self.assertIn("Rankings repetidos entre execuções: #19 (2x), #20 (2x)", texto)
        self.assertIn("RANKING #19 ⚠️ repetido", texto)
        self.assertIn("Ronda posterior A", texto)
        self.assertIn("Ronda posterior B", texto)
        self.assertIn("20 por execução", texto)

    def test_zero_selecoes_nao_forca_apostas(self):
        texto = self._relatorio([])
        self.assertIn("0 SUGESTÕES DO MODELO", texto)
        self.assertIn("Nenhuma seleção passou os filtros", texto)


if __name__ == "__main__":
    unittest.main()
