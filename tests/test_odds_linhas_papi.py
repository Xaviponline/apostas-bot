import unittest

from odds_auditoria import AuditoriaOdds
from odds_betano import OddsBetano


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class PapiLinhasSession:
    def get(self, url, params=None, **kwargs):
        if url.endswith("/markets"):
            return FakeResponse(
                [
                    {
                        "marketId": 106,
                        "marketName": "Over Under Full Time",
                        "playerProp": False,
                        "sportId": 10,
                        "handicap": 3.5,
                        "period": "fulltime",
                        "marketType": "totals",
                        "outcomes": [
                            {"outcomeId": 106, "outcomeName": "Over"},
                            {"outcomeId": 107, "outcomeName": "Under"},
                        ],
                    },
                    {
                        "marketId": 206,
                        "marketName": "Over Under Full Time",
                        "playerProp": False,
                        "sportId": 10,
                        "handicap": 2.5,
                        "period": "fulltime",
                        "marketType": "totals",
                        "outcomes": [
                            {"outcomeId": 206, "outcomeName": "Over"},
                            {"outcomeId": 207, "outcomeName": "Under"},
                        ],
                    },
                ]
            )
        if url.endswith("/odds-by-tournaments"):
            return FakeResponse(
                [
                    {
                        "fixtureId": "id100",
                        "tournamentId": 321,
                        "updatedAt": "2026-09-16T10:03:00Z",
                        "bookmakerOdds": {
                            "betano.pt": {
                                "markets": {
                                    "206": {
                                        "marketActive": True,
                                        "outcomes": {
                                            "206": {
                                                "players": {
                                                    "0": {
                                                        "active": True,
                                                        "price": 1.80,
                                                        "bookmakerOutcomeId": "2.5/over",
                                                        "changedAt": "2026-09-16T10:03:00Z",
                                                        "mainLine": True,
                                                    }
                                                }
                                            },
                                            "207": {
                                                "players": {
                                                    "0": {
                                                        "active": True,
                                                        "price": 2.00,
                                                        "bookmakerOutcomeId": "2.5/under",
                                                        "changedAt": "2026-09-16T10:03:00Z",
                                                        "mainLine": True,
                                                    }
                                                }
                                            },
                                        },
                                    }
                                }
                            }
                        },
                    }
                ]
            )
        if url.endswith("/odds"):
            return FakeResponse(
                {
                    "fixtureId": "id100",
                    "participant1Name": "Casa",
                    "participant2Name": "Fora",
                    "tournamentName": "Liga",
                    "updatedAt": "2026-09-16T10:00:00Z",
                    "bookmakerOdds": {
                        "betano.pt": {
                            "markets": {
                                "106": {
                                    "marketActive": True,
                                    "outcomes": {
                                        "106": {
                                            "players": {
                                                "0": {
                                                    "active": True,
                                                    "price": 2.40,
                                                    "bookmakerOutcomeId": "3.5/over",
                                                    "changedAt": "2026-09-16T10:01:00Z",
                                                    "mainLine": False,
                                                }
                                            }
                                        },
                                        "107": {
                                            "players": {
                                                "0": {
                                                    "active": True,
                                                    "price": 1.55,
                                                    "bookmakerOutcomeId": "3.5/under",
                                                    "bookmakerChangedAt": "2026-09-16T10:02:00Z",
                                                    "changedAt": "2026-09-16T10:02:01Z",
                                                    "mainLine": False,
                                                }
                                            }
                                        },
                                    },
                                },
                                "206": {
                                    "marketActive": True,
                                    "outcomes": {
                                        "206": {
                                            "players": {
                                                "0": {
                                                    "active": True,
                                                    "price": 1.80,
                                                    "bookmakerOutcomeId": "2.5/over",
                                                    "changedAt": "2026-09-16T10:03:00Z",
                                                    "mainLine": True,
                                                }
                                            }
                                        },
                                        "207": {
                                            "players": {
                                                "0": {
                                                    "active": True,
                                                    "price": 2.00,
                                                    "bookmakerOutcomeId": "2.5/under",
                                                    "changedAt": "2026-09-16T10:03:00Z",
                                                    "mainLine": True,
                                                }
                                            }
                                        },
                                    },
                                },
                            }
                        }
                    },
                }
            )
        if url.endswith("/fixtures"):
            return FakeResponse([])
        raise AssertionError(url)


class OddsLinhasPapiTests(unittest.TestCase):
    def setUp(self):
        self.fonte = OddsBetano(
            papi_key="teste", provider="oddspapi", session=PapiLinhasSession()
        )
        self.dados = self.fonte.odds_evento("id100")


    def test_batch_por_torneio_devolve_fixture_normalizado(self):
        fonte = OddsBetano(
            papi_key="teste", provider="oddspapi", session=PapiLinhasSession()
        )
        dados = fonte.odds_eventos_em_lote(
            [{"id": "id100", "tournament_id": 321}]
        )

        self.assertIn("id100", dados)
        self.assertEqual(dados["id100"]["id"], "id100")
        self.assertEqual(
            AuditoriaOdds._extrair_odd(dados["id100"], "Under 2.5 Golos"),
            (2.00, "2026-09-16T10:03:00Z"),
        )

    def test_parser_preserva_linha_periodo_tipo_principal_e_timestamp(self):
        mercado = next(m for m in self.dados["mercados"] if m["handicap"] == 3.5)
        under = next(o for o in mercado["odds"] if o["seleção"] == "Under")
        self.assertEqual(mercado["period"], "fulltime")
        self.assertEqual(mercado["marketType"], "totals")
        self.assertFalse(under["mainLine"])
        self.assertEqual(under["bookmakerChangedAt"], "2026-09-16T10:02:00Z")
        self.assertIn("linha 3.5", self.fonte.formatar_odds(self.dados))

    def test_auditoria_casa_por_mercado_linha_e_selecao(self):
        self.assertEqual(
            AuditoriaOdds._extrair_odd(self.dados, "Under 3.5 Golos"),
            (1.55, "2026-09-16T10:02:00Z"),
        )
        self.assertEqual(
            AuditoriaOdds._extrair_odd(self.dados, "Under 2.5 Golos"),
            (2.00, "2026-09-16T10:03:00Z"),
        )
        self.assertIsNone(AuditoriaOdds._extrair_odd(self.dados, "Under 1.5 Golos"))

    def test_periodo_incorreto_nao_e_aceite(self):
        dados = {
            "casa": "Casa",
            "fora": "Fora",
            "mercados": [
                {
                    "name": "Over Under Full Time",
                    "handicap": 3.5,
                    "period": "firsthalf",
                    "odds": [{"seleção": "Under", "odd": 1.30}],
                }
            ],
        }
        self.assertIsNone(AuditoriaOdds._extrair_odd(dados, "Under 3.5 Golos"))

    def test_totais_do_jogo_ignoram_cantos_e_totais_por_equipa(self):
        dados = {
            "casa": "Atlético Madrid",
            "fora": "CA Osasuna",
            "mercados": [
                {
                    "name": "Corners - Over Under Full Time",
                    "handicap": 3.5,
                    "period": "fulltime",
                    "marketType": "totals",
                    "odds": [{"seleção": "Under", "odd": 6.90}],
                },
                {
                    "name": "Over Under Team 1",
                    "handicap": 3.5,
                    "period": "fulltime",
                    "marketType": "totals",
                    "odds": [{"seleção": "Under", "odd": 1.15}],
                },
                {
                    "name": "Over Under Full Time",
                    "handicap": 3.5,
                    "period": "fulltime",
                    "marketType": "totals",
                    "updatedAt": "2026-09-16T10:03:32.526Z",
                    "odds": [{"seleção": "Under", "odd": 1.37}],
                },
            ],
        }
        self.assertEqual(
            AuditoriaOdds._extrair_odd(dados, "Under 3.5 Golos"),
            (1.37, "2026-09-16T10:03:32.526Z"),
        )

    def test_resultado_1x2_ignora_cantos(self):
        dados = {
            "casa": "Casa",
            "fora": "Fora",
            "mercados": [
                {
                    "name": "Corners - 1X2",
                    "period": "fulltime",
                    "odds": [{"seleção": "1", "odd": 1.16}],
                },
                {
                    "name": "Full Time Result",
                    "period": "fulltime",
                    "updatedAt": "2026-09-16T11:59:53.778Z",
                    "odds": [{"seleção": "1", "odd": 1.38}],
                },
            ],
        }
        self.assertEqual(
            AuditoriaOdds._extrair_odd(dados, "Vitória Casa"),
            (1.38, "2026-09-16T11:59:53.778Z"),
        )


if __name__ == "__main__":
    unittest.main()
