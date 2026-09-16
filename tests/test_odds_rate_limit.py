import unittest
from unittest.mock import patch

import requests

from odds_betano import OddsBetano


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}", response=self
            )

    def json(self):
        return self.payload


class RateLimitSession:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = 0

    def get(self, *args, **kwargs):
        self.chamadas += 1
        return self.respostas.pop(0)


class OddsRateLimitTests(unittest.TestCase):
    def test_429_temporario_espera_e_repete(self):
        session = RateLimitSession(
            [
                FakeResponse(
                    {
                        "error": {
                            "code": "RATE_LIMITED",
                            "retryMs": 5,
                        }
                    },
                    status_code=429,
                ),
                FakeResponse({"fixtureId": "evt1"}, status_code=200),
            ]
        )
        fonte = OddsBetano(
            papi_key="teste", provider="oddspapi", session=session
        )
        fonte.PAPI_ODDS_INTERVALO = 0

        with patch("odds_betano.sleep") as dormir:
            dados = fonte._get_papi("/odds", {"fixtureId": "evt1"})

        self.assertEqual(dados["fixtureId"], "evt1")
        self.assertEqual(session.chamadas, 2)
        self.assertTrue(dormir.called)

    def test_cota_esgotada_nao_faz_retry(self):
        session = RateLimitSession(
            [
                FakeResponse(
                    {
                        "message": "Request limit exceeded",
                        "code": "REQUEST_LIMIT_EXCEEDED",
                    },
                    status_code=429,
                )
            ]
        )
        fonte = OddsBetano(
            papi_key="teste", provider="oddspapi", session=session
        )
        fonte.PAPI_ODDS_INTERVALO = 0

        with patch("odds_betano.sleep"):
            with self.assertRaises(requests.HTTPError):
                fonte._get_papi("/odds", {"fixtureId": "evt1"})

        self.assertEqual(session.chamadas, 1)


if __name__ == "__main__":
    unittest.main()
