import tempfile
import time
import unittest
import requests
from pathlib import Path

from main_sofascore import BotPremiumReal
from odds_betano import OddsBetano
from previsoes_premium import RegistoPrevisoes


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class CapturaParamsSession:
    def __init__(self):
        self.params = None

    def get(self, url, params=None, **kwargs):
        if url.endswith("/odds-by-tournaments"):
            self.params = dict(params or {})
            return FakeResponse([])
        raise AssertionError(url)


class HTTPFalhaResponse:
    def __init__(self, status):
        self.status_code = status
        self.headers = {}

    def raise_for_status(self):
        raise requests.HTTPError("Pedido rejeitado", response=self)


class SessaoLote400:
    def __init__(self, falhas=None):
        self.chamadas = []
        self.falhas = set(falhas or {"11,22"})

    def get(self, url, params=None, **kwargs):
        if not url.endswith("/odds-by-tournaments"):
            raise AssertionError("Endpoint inesperado: " + url)
        torneios = str((params or {}).get("tournamentIds") or "")
        self.chamadas.append(torneios)
        if torneios in self.falhas:
            return HTTPFalhaResponse(400)
        return FakeResponse([
            {
                "fixtureId": "f" + torneio,
                "participant1Name": "Casa",
                "participant2Name": "Fora",
                "bookmakerOdds": {},
            }
            for torneio in torneios.split(",")
        ])


class OddsBatchFalhaFake:
    configurada = True
    nome_fonte = "Fonte Teste"

    def __init__(self):
        self.individuais = []
        self.ultimo_erro_evento = {}

    def eventos_hoje(self):
        return [
            {
                "id": str(i),
                "casa": f"Casa {i}",
                "fora": f"Fora {i}",
                "data": "2030-01-01T12:00:00Z",
                "tournament_id": 100 + i,
            }
            for i in range(1, 8)
        ]

    def odds_eventos_em_lote(self, eventos):
        saida = {}
        for evento in eventos:
            eid = str(evento["id"])
            self.ultimo_erro_evento[eid] = "odds_http_400"
            saida[eid] = None
        return saida

    def diagnostico_evento(self, event_id):
        return self.ultimo_erro_evento.get(str(event_id), "")

    def odds_evento(self, event_id):
        eid = int(event_id)
        self.individuais.append(eid)
        return {
            "id": str(eid),
            "casa": f"Casa {eid}",
            "fora": f"Fora {eid}",
            "fonte": self.nome_fonte,
            "bookmaker_disponivel": True,
            "mercados": [
                {
                    "name": "Full Time Result",
                    "period": "Full Time",
                    "odds": [
                        {"seleção": "1", "ref": "1", "odd": 1.80},
                        {"seleção": "X", "ref": "X", "odd": 3.20},
                        {"seleção": "2", "ref": "2", "odd": 4.50},
                    ],
                }
            ],
        }


class GestorFake:
    dados = {"ultimo_update": 0}


class OddsBatchRobustezTests(unittest.TestCase):
    def test_batch_nao_envia_oddsformat_redundante(self):
        sessao = CapturaParamsSession()
        fonte = OddsBetano(
            papi_key="teste",
            provider="oddspapi",
            session=sessao,
        )

        fonte.odds_eventos_em_lote(
            [{"id": "id100", "tournament_id": 321}]
        )

        self.assertIsNotNone(sessao.params)
        self.assertEqual(sessao.params["tournamentIds"], "321")
        self.assertEqual(sessao.params["bookmakers"], "betano.pt")
        self.assertNotIn("oddsFormat", sessao.params)

    def _fonte_lote(self, sessao):
        fonte = OddsBetano(papi_key="segredo_teste", provider="oddspapi", session=sessao)
        fonte.PAPI_BATCH_INTERVALO = 0
        return fonte

    def test_lote_400_recupera_duas_metades_com_dois_pedidos_extra(self):
        sessao = SessaoLote400()
        fonte = self._fonte_lote(sessao)
        eventos = [
            {"id": "f11", "tournament_id": 11},
            {"id": "f22", "tournament_id": 22},
        ]

        dados = fonte.odds_eventos_em_lote(eventos)

        self.assertEqual(sessao.chamadas, ["11,22", "11", "22"])
        self.assertEqual(dados["f11"]["id"], "f11")
        self.assertEqual(dados["f22"]["id"], "f22")
        self.assertEqual(fonte.diagnostico_evento("f11"), "")

    def test_lote_400_grupo_invalido_mantem_diagnostico_e_salva_restantes(self):
        sessao = SessaoLote400(falhas={"11,22", "22"})
        fonte = self._fonte_lote(sessao)

        dados = fonte.odds_eventos_em_lote([
            {"id": "f11", "tournament_id": 11},
            {"id": "f22", "tournament_id": 22},
        ])

        self.assertEqual(len(sessao.chamadas), 3)
        self.assertEqual(dados["f11"]["id"], "f11")
        self.assertIsNone(dados["f22"])
        self.assertEqual(fonte.diagnostico_evento("f22"), "odds_http_400")
        self.assertNotIn("segredo_teste", str(dados))

    def test_lote_400_sem_recuperacao_limita_tentativas(self):
        sessao = SessaoLote400(falhas={"11,22", "11", "22"})
        fonte = self._fonte_lote(sessao)
        dados = fonte.odds_eventos_em_lote([
            {"id": "f11", "tournament_id": 11},
            {"id": "f22", "tournament_id": 22},
        ])
        self.assertEqual(sessao.chamadas, ["11,22", "11", "22"])
        self.assertIsNone(dados["f11"])
        self.assertIsNone(dados["f22"])
        self.assertEqual(fonte.diagnostico_evento("f11"), "odds_http_400")

    def test_lote_400_torneio_unico_nao_repete(self):
        sessao = SessaoLote400(falhas={"11"})
        fonte = self._fonte_lote(sessao)
        self.assertEqual(
            fonte.odds_eventos_em_lote([{"id": "f11", "tournament_id": 11}]),
            {"f11": None},
        )
        self.assertEqual(sessao.chamadas, ["11"])

    def test_lote_401_nao_repetir_nem_dividir(self):
        class Sessao401(SessaoLote400):
            def get(self, url, params=None, **kwargs):
                self.chamadas.append(str((params or {}).get("tournamentIds") or ""))
                return HTTPFalhaResponse(401)

        sessao = Sessao401()
        fonte = self._fonte_lote(sessao)
        dados = fonte.odds_eventos_em_lote([
            {"id": "f11", "tournament_id": 11},
            {"id": "f22", "tournament_id": 22},
        ])
        self.assertIsNone(dados["f11"])
        self.assertEqual(sessao.chamadas, ["11,22"])

    def test_captura_automatica_faz_fallback_so_nas_cinco_top5(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            inicio = time.time() + 3600

            # Insere deliberadamente por ordem inversa para provar que o
            # fallback é priorizado por ranking, não por ordem física.
            for ranking in range(7, 0, -1):
                reg.registar(
                    [
                        {
                            "jogo": {
                                "id": ranking,
                                "casa": f"Casa {ranking}",
                                "fora": f"Fora {ranking}",
                                "liga": "Liga Teste",
                                "timestamp": inicio,
                            },
                            "mercado": "Vitória Casa",
                            "probabilidade": 0.60,
                            "probabilidade_bruta": 0.62,
                            "qualidade": 80,
                            "odd_justa": 1.67,
                            "odd_minima": 1.75,
                            "ranking_modelo": ranking,
                            "confianca": "MÉDIA",
                            "score": 0.60,
                        }
                    ]
                )

            odds = OddsBatchFalhaFake()
            bot = BotPremiumReal(
                token="teste",
                gestor=GestorFake(),
                owner_id=1,
                chat_id=1,
                buscador=object(),
                odds=odds,
                analisador=object(),
                previsoes=reg,
            )

            capturadas = bot._capturar_odds_pendentes()

            self.assertEqual(capturadas, 5)
            self.assertEqual(odds.individuais, [1, 2, 3, 4, 5])
            por_rank = {
                int(p["ranking_modelo"]): p
                for p in reg.dados["previsoes"]
            }
            for ranking in range(1, 6):
                self.assertEqual(por_rank[ranking]["odd_real"], 1.80)
            for ranking in (6, 7):
                self.assertNotIn("odd_real", por_rank[ranking])


if __name__ == "__main__":
    unittest.main()
