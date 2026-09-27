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





class EspnEnriquecimentoIntermitenteSession:
    EVENTO = {
        "id": "401999777",
        "date": "2026-09-27T20:00:00Z",
        "league": {"name": "Regular Season"},
        "season": {"name": "Regular Season", "slug": "regular-season"},
        "status": {"type": {"state": "pre"}},
        "competitions": [
            {
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": "111", "displayName": "Casa 2"},
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": "222", "displayName": "Fora 2"},
                    },
                ]
            }
        ],
    }

    def __init__(self):
        self.chamadas_especificas = 0

    def get(self, url, *args, **kwargs):
        if "/all/scoreboard" in url:
            return FakeResponse({"events": [self.EVENTO]})
        if "/esp.2/scoreboard" in url:
            self.chamadas_especificas += 1
            if self.chamadas_especificas == 1:
                return FakeResponse({"events": [self.EVENTO]})
            return FakeResponse({"message": "forbidden"}, status_code=403)
        return FakeResponse({"events": []})

class EnriquecimentoCompeticoesTests(unittest.TestCase):
    def test_cache_diario_preserva_league_code_se_endpoint_especifico_falhar_depois(self):
        session = EspnEnriquecimentoIntermitenteSession()
        buscador = BuscadorJogosEnriquecido(session=session, enabled=True)

        primeira = buscador.buscar_todos_jogos_hoje("2026-09-27")
        segunda = buscador.buscar_todos_jogos_hoje("2026-09-27")

        self.assertEqual(primeira[0]["league_code"], "esp.2")
        self.assertEqual(primeira[0]["liga"], "Spanish LaLiga 2")
        self.assertEqual(segunda[0]["league_code"], "esp.2")
        self.assertEqual(segunda[0]["liga"], "Spanish LaLiga 2")
        self.assertEqual(
            EstatisticasESPNEnriquecidas.resolver_liga(segunda[0]),
            "esp.2",
        )

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
