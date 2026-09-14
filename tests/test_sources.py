import unittest

from buscador_jogos_reais import BuscadorJogosReais
from odds_betano import OddsBetano


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class SofaSession:
    def get(self, *args, **kwargs):
        return FakeResponse(
            {
                "events": [
                    {
                        "id": 100,
                        "homeTeam": {"id": 1, "name": "Casa"},
                        "awayTeam": {"id": 2, "name": "Fora"},
                        "tournament": {
                            "name": "Liga X",
                            "uniqueTournament": {"name": "Liga X"},
                            "category": {"name": "Portugal"},
                            "priority": 10,
                        },
                        "status": {"type": "notstarted"},
                        "startTimestamp": 1789415100,
                    }
                ]
            }
        )


class OddsSession:
    def get(self, url, params=None, **kwargs):
        if url.endswith("/events"):
            return FakeResponse(
                [
                    {
                        "id": 50,
                        "home": "Casa",
                        "away": "Fora",
                        "date": "2026-09-14T20:00:00Z",
                        "league": {"name": "Liga X"},
                        "status": "pending",
                    }
                ]
            )
        return FakeResponse(
            {
                "id": 50,
                "home": "Casa",
                "away": "Fora",
                "league": {"name": "Liga X"},
                "bookmakers": {
                    "Betano": [
                        {
                            "name": "ML",
                            "updatedAt": "2026-09-14T12:00:00Z",
                            "odds": [{"home": "1.80", "draw": "3.40", "away": "4.20"}],
                        }
                    ]
                },
            }
        )


class SourceTests(unittest.TestCase):
    def test_sofascore_default_is_off_in_tests(self):
        b = BuscadorJogosReais(enabled=False)
        self.assertEqual(b.buscar_todos_jogos_hoje("2026-09-14"), [])
        self.assertEqual(b.estado, "desativado")

    def test_sofascore_normalizes_real_payload(self):
        b = BuscadorJogosReais(session=SofaSession())
        jogos = b.buscar_todos_jogos_hoje("2026-09-14")
        self.assertEqual(len(jogos), 1)
        self.assertEqual(jogos[0]["id"], 100)
        self.assertEqual(jogos[0]["casa_id"], 1)
        self.assertEqual(jogos[0]["fora_id"], 2)
        self.assertIn("Casa vs Fora", b.formatar_jogos(jogos))

    def test_odds_betano_without_key_does_not_call_network(self):
        fonte = OddsBetano(api_key="")
        self.assertFalse(fonte.configurada)
        self.assertEqual(fonte.eventos_hoje(), [])
        self.assertIsNone(fonte.odds_evento(50))

    def test_odds_betano_parses_events_and_odds(self):
        fonte = OddsBetano(api_key="teste", session=OddsSession())
        eventos = fonte.eventos_hoje()
        self.assertEqual(eventos[0]["id"], 50)
        dados = fonte.odds_evento(50)
        self.assertEqual(dados["mercados"][0]["name"], "ML")
        texto = fonte.formatar_odds(dados)
        self.assertIn("home=1.80", texto)
        self.assertIn("draw=3.40", texto)


if __name__ == "__main__":
    unittest.main()
