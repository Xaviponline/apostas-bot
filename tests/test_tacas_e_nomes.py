import unittest

from main_enriquecido import (
    AnalisadorInteligenteEnriquecido,
    BuscadorJogosEnriquecido,
    EstatisticasESPNEnriquecidas,
)
from nomes_ligas import nome_liga_pt


class TacasENomesTests(unittest.TestCase):
    def test_premier_league_de_outro_pais_nao_e_inglesa(self):
        self.assertEqual(nome_liga_pt("Russian Premier League"), "Russian Premier League")
        self.assertEqual(
            AnalisadorInteligenteEnriquecido._bandeira_liga("Russian Premier League"),
            "🌍",
        )

    def test_tacas_principais_estao_na_descoberta_de_producao(self):
        esperadas = {
            "eng.fa",
            "eng.league_cup",
            "esp.copa_del_rey",
            "ger.dfb_pokal",
            "ita.coppa_italia",
            "fra.coupe_de_france",
            "por.taca.portugal",
            "ned.cup",
            "sco.tennents",
            "sco.cis",
            "bra.copa_do_brazil",
            "arg.copa",
        }
        self.assertTrue(esperadas.issubset(set(BuscadorJogosEnriquecido.ESPN_LEAGUES)))

    def test_resolver_aceita_codigo_e_nome_de_taca(self):
        self.assertEqual(
            EstatisticasESPNEnriquecidas.resolver_liga(
                {"league_code": "eng.league_cup", "liga": "Third Round"}
            ),
            "eng.league_cup",
        )
        self.assertEqual(
            EstatisticasESPNEnriquecidas.resolver_liga({"liga": "Spanish Copa del Rey"}),
            "esp.copa_del_rey",
        )
        self.assertEqual(
            EstatisticasESPNEnriquecidas.resolver_liga({"liga": "Portuguese Taca de Portugal"}),
            "por.taca.portugal",
        )

    def test_apresentacao_das_tacas(self):
        casos = {
            "English Carabao Cup": "EFL Cup",
            "Spanish Copa del Rey": "Taça do Rei",
            "German DFB-Pokal": "Taça da Alemanha",
            "Italian Coppa Italia": "Taça de Itália",
            "French Coupe de France": "Taça de França",
            "Portuguese Taca de Portugal": "Taça de Portugal",
            "Dutch KNVB Beker": "Taça dos Países Baixos",
            "Scottish Cup": "Taça da Escócia",
            "Brazilian Copa do Brasil": "Copa do Brasil",
            "Argentine Copa Argentina": "Copa Argentina",
        }
        for origem, esperado in casos.items():
            with self.subTest(origem=origem):
                self.assertEqual(nome_liga_pt(origem), esperado)


if __name__ == "__main__":
    unittest.main()
