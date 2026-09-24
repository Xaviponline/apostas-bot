import unittest

from odds_auditoria import AuditoriaOdds
from odds_betano import OddsBetano


class RespostaFake:
    def __init__(self, dados):
        self._dados = dados
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._dados


class SessaoPapiSemBetano:
    def __init__(self):
        self.chamadas = []

    def get(self, url, params=None, **kwargs):
        self.chamadas.append((url, dict(params or {})))
        if url.endswith("/fixtures"):
            return RespostaFake([
                {
                    "fixtureId": "id-cup-1",
                    "participant1Id": 11,
                    "participant2Id": 22,
                    "participant1Name": "Fleetwood Town",
                    "participant2Name": "Sheffield United",
                    "startTime": "2026-09-16T18:45:00.000Z",
                    "tournamentName": "EFL Cup",
                    "tournamentId": 321,
                    "statusName": "Pre-Game",
                    "hasOdds": False,
                }
            ])
        if url.endswith("/odds"):
            return RespostaFake({
                "fixtureId": "id-cup-1",
                "participant1Name": "Fleetwood Town",
                "participant2Name": "Sheffield United",
                "tournamentName": "EFL Cup",
                "bookmakerOdds": {},
            })
        raise AssertionError(url)


class SessaoPapiFallbackEstado:
    def __init__(self):
        self.chamadas = []

    def get(self, url, params=None, **kwargs):
        params = dict(params or {})
        self.chamadas.append((url, params))
        if not url.endswith("/fixtures"):
            raise AssertionError(url)
        if "statusId" in params:
            return RespostaFake([])
        return RespostaFake([
            {
                "fixtureId": "id-futuro-1",
                "participant1Id": 101,
                "participant2Id": 202,
                "participant1Name": "Portugal",
                "participant2Name": "Wales",
                "startTime": "2099-09-24T18:45:00.000Z",
                "tournamentName": "UEFA Nations League",
                "tournamentId": 999,
                "statusName": "Scheduled",
                "statusId": 1,
                "hasOdds": True,
            },
            {
                "fixtureId": "id-passado-1",
                "participant1Id": 303,
                "participant2Id": 404,
                "participant1Name": "Old Home",
                "participant2Name": "Old Away",
                "startTime": "2000-01-01T18:45:00.000Z",
                "tournamentName": "Old League",
                "tournamentId": 998,
                "statusName": "Ended",
                "statusId": 3,
                "hasOdds": True,
            },
        ])


class FontePayloadErrado:
    configurada = True
    nome_fonte = "Teste"

    def eventos_hoje(self):
        return [{"id": "evt1", "casa": "Independiente Rivadavia", "fora": "Atlético Tucumán"}]

    def odds_evento(self, event_id):
        return {
            "id": "evt1",
            "casa": "Independiente",
            "fora": "River Plate",
            "fonte": "Teste",
            "mercados": [
                {
                    "name": "Full Time Result",
                    "odds": [
                        {"seleção": "1", "ref": "home", "odd": 2.25},
                    ],
                }
            ],
        }


class OddsDescobertaTests(unittest.TestCase):
    def test_fixtures_papi_nao_dependem_de_hasodds_ou_bookmaker(self):
        sessao = SessaoPapiSemBetano()
        fonte = OddsBetano(papi_key="teste", provider="oddspapi", session=sessao)
        eventos = fonte.eventos_hoje()
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["id"], "id-cup-1")
        _, params = sessao.chamadas[0]
        self.assertNotIn("hasOdds", params)
        self.assertNotIn("bookmakers", params)
        self.assertFalse(eventos[0]["has_odds"])


    def test_fallback_sem_status_quando_status_zero_vem_vazio(self):
        sessao = SessaoPapiFallbackEstado()
        fonte = OddsBetano(papi_key="teste", provider="oddspapi", session=sessao)
        eventos = fonte.eventos_hoje()
        self.assertEqual([e["id"] for e in eventos], ["id-futuro-1"])
        self.assertEqual(len(sessao.chamadas), 2)
        self.assertEqual(sessao.chamadas[0][1].get("statusId"), 0)
        self.assertNotIn("statusId", sessao.chamadas[1][1])
        self.assertIn("fallback=1", fonte.ultimo_diagnostico_eventos)
        self.assertIn("futuros=1", fonte.ultimo_diagnostico_eventos)

    def test_jogo_existe_mas_betano_sem_odds_tem_diagnostico_proprio(self):
        fonte = OddsBetano(
            papi_key="teste", provider="oddspapi", session=SessaoPapiSemBetano()
        )
        selecoes = [{
            "jogo": {"id": 1, "casa": "Fleetwood Town", "fora": "Sheffield United"},
            "mercado": "Under 2.5 Golos",
            "probabilidade": 0.69,
        }]
        saida = AuditoriaOdds(fonte).enriquecer(selecoes)
        self.assertEqual(saida[0]["_odds_diag"], "betano_sem_odds_no_evento")
        self.assertNotIn("odd_real", saida[0])

    def test_payload_de_outro_jogo_nunca_e_aceite(self):
        selecoes = [{
            "jogo": {
                "id": 9,
                "casa": "Independiente Rivadavia",
                "fora": "Atlético Tucumán",
            },
            "mercado": "Vitória Casa",
            "probabilidade": 0.698,
        }]
        saida = AuditoriaOdds(FontePayloadErrado()).enriquecer(selecoes)
        self.assertEqual(saida[0]["_odds_diag"], "odds_payload_evento_divergente")
        self.assertNotIn("odd_real", saida[0])


if __name__ == "__main__":
    unittest.main()
