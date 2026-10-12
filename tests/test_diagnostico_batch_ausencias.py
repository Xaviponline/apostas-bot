"""Diagnostico sem rede real para odds ausentes e HTTP 404 em lote."""
import unittest
import requests
from unittest.mock import patch

from odds_betano import OddsBetano
from odds_auditoria import AuditoriaOdds


class Resposta:
    headers = {}

    def __init__(self, payload=None, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("Falha simulada", response=self)

    def json(self):
        return self.payload


class Sessao:
    def __init__(self, resposta):
        self.resposta = resposta
        self.chamadas = []

    def get(self, url, params=None, **kwargs):
        self.chamadas.append((url, dict(params or {})))
        if url.endswith("/odds-by-tournaments"):
            return self.resposta
        if url.endswith("/markets"):
            return Resposta([])
        raise AssertionError("Endpoint inesperado: " + url)


class DiagnosticoBatchTests(unittest.TestCase):
    @staticmethod
    def _eventos():
        return [
            {"id": "f11", "tournament_id": 11},
            {"id": "f12", "tournament_id": 11},
        ]

    def _fonte(self, resposta):
        sessao = Sessao(resposta)
        fonte = OddsBetano(papi_key="chave-falsa", provider="oddspapi", session=sessao)
        fonte.PAPI_BATCH_INTERVALO = 0
        fonte.PAPI_ACCOUNT_INTERVALO = 0
        return fonte, sessao

    def test_distingue_fixture_omitido_de_betano_sem_odds(self):
        fonte, sessao = self._fonte(Resposta([{
            "fixtureId": "f11", "participant1Name": "Casa", "participant2Name": "Fora",
            "bookmakerOdds": {},
        }]))
        with self.assertLogs(level="INFO") as logs:
            dados = fonte.odds_eventos_em_lote(self._eventos())

        self.assertFalse(dados["f11"]["bookmaker_disponivel"])
        self.assertIsNone(dados["f12"])
        self.assertEqual(fonte.diagnostico_evento("f12"), "fixture_omitido_no_lote")
        self.assertEqual(len(sessao.chamadas), 1)
        self.assertIn("omitidos=1", " ".join(logs.output))
        self.assertIn("betano_presente=0", " ".join(logs.output))
        self.assertNotIn("chave-falsa", " ".join(logs.output))
        extraida, motivo = AuditoriaOdds._extrair_odd_diagnostico(
            dados["f11"], "Under 2.5 Golos"
        )
        self.assertIsNone(extraida)
        self.assertEqual(motivo, "betano_sem_odds_no_evento")

    def test_lote_vazio_nao_atribui_ausencia_de_odds_a_betano(self):
        fonte, _ = self._fonte(Resposta([]))
        dados = fonte.odds_eventos_em_lote(self._eventos())
        self.assertTrue(all(x is None for x in dados.values()))
        self.assertEqual(fonte.diagnostico_evento("f11"), "fixture_omitido_no_lote")
        self.assertEqual(fonte.diagnostico_evento("f12"), "fixture_omitido_no_lote")

    def test_http_404_lote_mantem_erro_e_nao_faz_pedidos_extra(self):
        fonte, sessao = self._fonte(Resposta(status=404))
        with self.assertLogs(level="INFO") as logs:
            dados = fonte.odds_eventos_em_lote(self._eventos())
        self.assertEqual(dados, {"f11": None, "f12": None})
        self.assertEqual(fonte.diagnostico_evento("f11"), "odds_http_404")
        self.assertEqual(fonte.diagnostico_evento("f12"), "odds_http_404")
        self.assertEqual(len(sessao.chamadas), 1)
        self.assertIn("torneios=1", " ".join(logs.output))
        self.assertNotIn("chave-falsa", " ".join(logs.output))


if __name__ == "__main__":
    unittest.main()
