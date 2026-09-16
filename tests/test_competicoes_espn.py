import unittest

from buscador_jogos_reais import BuscadorJogosReais
from estatisticas_espn import EstatisticasESPN


class CompeticoesESPNTests(unittest.TestCase):
    def test_slug_da_competicao_substitui_nome_generico_da_fase(self):
        evento = {
            "id": "123456",
            "date": "2026-09-16T20:00:00Z",
            "league": {"name": "League Phase"},
            "season": {
                "name": "League Phase",
                "slug": "2026-27-uefa-europa-league",
            },
            "status": {"type": {"state": "pre"}},
            "competitions": [
                {
                    "league": {"name": "League Phase"},
                    "competitors": [
                        {
                            "homeAway": "home",
                            "team": {"id": "1", "displayName": "Casa"},
                        },
                        {
                            "homeAway": "away",
                            "team": {"id": "2", "displayName": "Fora"},
                        },
                    ],
                }
            ],
        }

        jogo = BuscadorJogosReais._normalizar_evento_espn(evento)

        self.assertIsNotNone(jogo)
        self.assertEqual(jogo["liga"], "UEFA Europa League")
        self.assertEqual(jogo["season_slug"], "2026-27-uefa-europa-league")
        self.assertEqual(EstatisticasESPN.resolver_liga(jogo), "uefa.europa")


if __name__ == "__main__":
    unittest.main()
