import unittest

import requests

from odds_auditoria import AuditoriaOdds
from odds_betano import OddsBetano


class Session429:
    def get(self, url, params=None, **kwargs):
        response = requests.Response()
        response.status_code = 429
        response.url = url
        raise requests.HTTPError("rate limit", response=response)


class SessionQuotaFixtures:
    def get(self, url, params=None, **kwargs):
        response = requests.Response()
        response.status_code = 429
        response.url = url
        response._content = b'{"code":"REQUEST_LIMIT_EXCEEDED"}'
        response.headers["Content-Type"] = "application/json"
        return response


class FonteComFalha:
    configurada = True
    nome_fonte = "Fonte teste"

    def eventos_hoje(self):
        return [{"id": "evt-1", "casa": "Casa", "fora": "Fora"}]

    def odds_evento(self, event_id):
        self._erro = {str(event_id): "odds_http_429"}
        return None

    def diagnostico_evento(self, event_id):
        return self._erro.get(str(event_id), "")


class FonteDescobertaFalha:
    configurada = True
    nome_fonte = "Fonte teste"
    ultimo_diagnostico_eventos = "odds_http_429"

    def eventos_hoje(self):
        return []


class OddsDiagnosticoFonteTests(unittest.TestCase):

    def test_eventos_hoje_converte_quota_em_diagnostico(self):
        fonte = OddsBetano(
            papi_key="teste",
            provider="oddspapi",
            session=SessionQuotaFixtures(),
        )
        fonte.PAPI_FIXTURES_INTERVALO = 0
        self.assertEqual(fonte.eventos_hoje(), [])
        self.assertEqual(fonte.ultimo_diagnostico_eventos, "odds_quota_esgotada")

    def test_odds_betano_guarda_http_sem_expor_payload(self):
        fonte = OddsBetano(
            papi_key="teste",
            provider="oddspapi",
            session=Session429(),
        )
        self.assertIsNone(fonte.odds_evento("abc"))
        self.assertEqual(fonte.diagnostico_evento("abc"), "odds_http_429")


    def test_auditoria_propaga_falha_da_descoberta(self):
        selecoes = [
            {
                "jogo": {"id": 2, "casa": "Portugal", "fora": "Wales"},
                "mercado": "Vitória Casa",
                "probabilidade": 0.66,
            }
        ]
        saida = AuditoriaOdds(FonteDescobertaFalha()).enriquecer(selecoes)
        self.assertEqual(saida[0]["_odds_diag"], "odds_http_429")
        self.assertNotIn("odd_real", saida[0])

    def test_auditoria_propaga_diagnostico_da_fonte(self):
        selecoes = [
            {
                "jogo": {"id": 1, "casa": "Casa", "fora": "Fora"},
                "mercado": "Vitória Casa",
                "probabilidade": 0.60,
            }
        ]
        saida = AuditoriaOdds(FonteComFalha()).enriquecer(selecoes)
        self.assertEqual(saida[0]["_odds_diag"], "odds_http_429")
        self.assertNotIn("odd_real", saida[0])


if __name__ == "__main__":
    unittest.main()
