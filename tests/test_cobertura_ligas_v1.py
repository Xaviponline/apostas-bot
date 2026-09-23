import unittest

from analisador_inteligente import AnalisadorInteligente
from buscador_jogos_reais import BuscadorJogosReais
from estatisticas_espn import EstatisticasESPN
from nomes_ligas import nome_liga_pt


class CoberturaLigasV1Tests(unittest.TestCase):
    def test_novas_ligas_por_nome(self):
        casos = {
            "English League Championship": "eng.2",
            "English League One": "eng.3",
            "English League Two": "eng.4",
            "Spanish LALIGA 2": "esp.2",
            "Italian Serie B": "ita.2",
            "German 2. Bundesliga": "ger.2",
            "Scottish Premiership": "sco.1",
            "Scottish Championship": "sco.2",
            "Austrian Bundesliga": "aut.1",
            "Danish Superliga": "den.1",
            "Greek Super League": "gre.1",
            "Swiss Super League": "sui.1",
            "Major League Soccer": "usa.1",
            "UEFA Nations League": "uefa.nations",
        }
        for nome, codigo in casos.items():
            with self.subTest(nome=nome):
                self.assertEqual(EstatisticasESPN.resolver_liga({"liga": nome}), codigo)

    def test_laliga_2_slug_nao_cai_na_laliga_1(self):
        jogo = {
            "liga": "League Stage",
            "season_slug": "2026-27-spanish-laliga-2",
        }
        self.assertEqual(EstatisticasESPN.resolver_liga(jogo), "esp.2")
        self.assertEqual(
            BuscadorJogosReais._nome_liga_por_slug(jogo["season_slug"]),
            "Spanish LALIGA 2",
        )

    def test_fallback_espn_contem_novas_ligas(self):
        esperadas = {
            "eng.2", "eng.3", "eng.4", "esp.2", "ita.2", "ger.2",
            "sco.1", "sco.2", "aut.1", "den.1", "gre.1", "sui.1", "usa.1",
            "uefa.nations",
        }
        self.assertTrue(esperadas.issubset(set(BuscadorJogosReais.ESPN_LEAGUES)))

    def test_apresentacao_pt_e_bandeiras(self):
        self.assertEqual(nome_liga_pt("Spanish LALIGA 2"), "LaLiga 2")
        self.assertEqual(nome_liga_pt("English League Two"), "League Two")
        self.assertEqual(nome_liga_pt("Scottish Premiership"), "Premiership Escocesa")
        self.assertEqual(nome_liga_pt("UEFA Nations League"), "Liga das Nações")
        self.assertEqual(AnalisadorInteligente._bandeira_liga("Greek Super League"), "🇬🇷")
        self.assertEqual(AnalisadorInteligente._bandeira_liga("Swiss Super League"), "🇨🇭")


if __name__ == "__main__":
    unittest.main()
