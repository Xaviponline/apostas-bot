"""Segurança do estado da bookmaker OddsPapi sem chamadas reais."""
import copy
import unittest

from odds_betano import OddsBetano
from odds_auditoria import AuditoriaOdds


def payload(book):
    return {
        "fixtureId": "123",
        "participant1Name": "Casa",
        "participant2Name": "Fora",
        "tournamentName": "English Premier League",
        "bookmakerOdds": {"betano.pt": book},
    }


def bookmaker(**kwargs):
    value = {
        "bookmakerIsActive": True,
        "suspended": False,
        "markets": {
            "1": {
                "marketActive": True,
                "outcomes": {
                    "home": {"players": {"0": {
                        "active": True, "price": 2.0,
                        "changedAt": "2030-10-24T12:00:00Z",
                    }}},
                },
            }
        },
    }
    value.update(kwargs)
    return value


class BookmakerSuspensaTests(unittest.TestCase):
    def setUp(self):
        self.fonte = OddsBetano(papi_key="fake",provider="oddspapi")
        self.fonte._catalogo_mercados = {
            "1": {"name": "Full Time Result", "period": "fulltime",
                  "outcomes": {"home": "Home"}}
        }

    def test_bookmaker_suspensa_ou_inativa_bloqueia_odds(self):
        for flags in ({"suspended": True},
                      {"bookmakerIsActive": False},
                      {"suspended": True, "bookmakerIsActive": False}):
            with self.subTest(flags=flags):
                raw = payload(bookmaker(**flags))
                before = copy.deepcopy(raw)
                out = self.fonte._normalizar_odds_papi(raw)
                self.assertEqual(raw, before)
                self.assertFalse(out["bookmaker_disponivel"])
                self.assertEqual(out["mercados"], [])
                odd, diag = AuditoriaOdds._extrair_odd_diagnostico(
                    out, "Vitória Casa")
                self.assertIsNone(odd)
                self.assertEqual(diag, "betano_sem_odds_no_evento")

    def test_bookmaker_ativa_retorna_odd(self):
        out=self.fonte._normalizar_odds_papi(payload(bookmaker()))
        self.assertTrue(out["bookmaker_disponivel"])
        self.assertEqual(len(out["mercados"]), 1)
        self.assertEqual(out["mercados"][0]["odds"][0]["odd"], 2.0)

    def test_campos_ausentes_compatibilidade_historica(self):
        b=bookmaker()
        b.pop("bookmakerIsActive")
        b.pop("suspended")
        out=self.fonte._normalizar_odds_papi(payload(b))
        self.assertTrue(out["bookmaker_disponivel"])
        self.assertTrue(out["mercados"])

    def test_mercado_suspenso_e_player_inativo_continuam_bloqueados(self):
        b=bookmaker()
        b["markets"]["1"]["marketActive"]=False
        out=self.fonte._normalizar_odds_papi(payload(b))
        self.assertEqual(out["mercados"],[])
        b=bookmaker()
        b["markets"]["1"]["outcomes"]["home"]["players"]["0"]["active"]=False
        out=self.fonte._normalizar_odds_papi(payload(b))
        self.assertEqual(out["mercados"],[])


if __name__ == "__main__":
    unittest.main()
