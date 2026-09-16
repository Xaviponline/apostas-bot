import unittest

from main_enriquecido import BuscadorJogosEnriquecido, EstatisticasESPNEnriquecidas


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class EspnEnriquecidaSession:
    EVENTO = {
        "id": "401999001",
        "date": "2026-09-16T20:00:00Z",
        "league": {"name": "League Phase"},
        "season": {"name": "League Phase", "slug": "league-phase"},
        "status": {"type": {"state": "pre"}},
        "competitions": [
            {
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": "11", "displayName": "Casa Europa"},
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "22", "displayName": "Fora Europa"},
                    },
                ]
            }
        ],
    }

    def get(self, url, *args, **kwargs):
        if "/all/scoreboard" in url:
            return FakeResponse({"events": [self.EVENTO]})
        if "/uefa.europa/scoreboard" in url:
            return FakeResponse({"events": [self.EVENTO]})
        return FakeResponse({"events": []})


class EnriquecimentoCompeticoesTests(unittest.TestCase):
    def test_endpoint_especifico_enriquece_evento_global_generico(self):
        buscador = BuscadorJogosEnriquecido(
            session=EspnEnriquecidaSession(),
            enabled=True,
        )
        jogos = buscador.buscar_todos_jogos_hoje("2026-09-16")

        self.assertEqual(len(jogos), 1)
        jogo = jogos[0]
        self.assertEqual(jogo["liga"], "UEFA Europa League")
        self.assertEqual(jogo["league_code"], "uefa.europa")
        self.assertEqual(EstatisticasESPNEnriquecidas.resolver_liga(jogo), "uefa.europa")


if __name__ == "__main__":
    unittest.main()
