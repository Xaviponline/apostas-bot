"""Testes offline de auditoria do /odds bruto — sem chamadas de rede."""
import copy
import unittest
from contextlib import nullcontext

from odds_payload_audit import auditar_payload_bruto
from main_competicoes import BotPremiumDiarioCompeticoes

ID = "id1000015573265458"


def payload():
    return {
        "fixtureId": ID,
        "participant1Name": "Gimnasia La Plata",
        "participant2Name": "CA Sarmiento",
        "tournamentName": "Primera LPF",
        "updatedAt": "2026-10-21T09:45:48Z",
        "apiKey": "SEGREDO_NAO_APRESENTAR",
        "bookmakerOdds": {
            "betano.pt": {
                "markets": {
                    "101": {
                        "marketActive": True,
                        "outcomes": {"a": {"players": {
                            "1": {"active": False, "price": 1.55}
                        }}},
                    },
                    "104": {
                        "marketActive": False,
                        "outcomes": {"yes": {"players": {
                            "1": {"active": True, "price": 1.75}
                        }}},
                    },
                    "1010": {
                        "marketActive": True,
                        "outcomes": {"over": {"players": {
                            "1": {"active": True, "price": None}
                        }}},
                    },
                    "1018": {
                        "marketActive": True,
                        "outcomes": {"under": {"players": {
                            "1": {"active": True, "price": 9.99}
                        }}},
                    },
                }
            }
        }
    }


class FakeOdds:
    provider = "oddspapi"
    configurada = True
    papi_bookmaker = "betano.pt"

    def __init__(self, raw=None, catalogo=True):
        self.raw = payload() if raw is None else raw
        self.calls = []
        self._catalogo_mercados = ({
            "101": {"name": "Full Time Result", "period": "fulltime"},
            "104": {"name": "Both Teams to Score", "period": "fulltime"},
            "1010": {"name": "Over Under Full Time",
                     "handicap": 2.5, "period": "fulltime"},
            "1018": {"name": "Over Under Full Time",
                     "handicap": 6.5, "period": "fulltime"},
        } if catalogo else None)

    def _get_papi(self, endpoint, params):
        self.calls.append((endpoint, copy.deepcopy(params)))
        if endpoint != "/odds":
            raise AssertionError("Nao pode consultar outra rota")
        return copy.deepcopy(self.raw)

    def contexto_operacao(self, operacao):
        self.calls.append(("contexto", operacao))
        return nullcontext()


class PayloadBrutoTests(unittest.TestCase):
    def test_inativos_sao_contados_sem_mudar_preco(self):
        odds = FakeOdds()
        chamadas = []
        texto = auditar_payload_bruto(
            odds, ID, lambda *a: chamadas.append(a) or True
        )
        self.assertIn("Mercados brutos: 4 | ativos: 3 | inativos: 1", texto)
        self.assertIn("Mercados ativos com preco: 1 | sem preco: 2", texto)
        self.assertIn("Resultado Final (1X2): 1 → 0", texto)
        self.assertIn("Ambas Marcam: 1 → 0", texto)
        self.assertIn("Mais/Menos 2.5: 1 → 0", texto)
        self.assertIn("1018", texto)
        self.assertEqual(chamadas, [("ODDS_AUTO", 25)])
        self.assertEqual([c[0] for c in odds.calls], ["contexto", "/odds"])
        self.assertEqual(odds.calls[-1][1]["fixtureId"], ID)
        self.assertEqual(odds.calls[-1][1]["bookmakers"], "betano.pt")
        for segredo in ("1.55", "1.75", "9.99", "SEGREDO_NAO_APRESENTAR"):
            self.assertNotIn(segredo, texto)

    def test_formato_invalido_zero_api_e_quota(self):
        odds = FakeOdds()
        def nao_chamar(*args):
            raise AssertionError("Quota nao deve ser consultada")
        for arg in ("", "abc", ID + " | Betano", "https://" + ID,
                    "id1", "../" + ID):
            self.assertIn("Formato", auditar_payload_bruto(odds, arg, nao_chamar))
        self.assertEqual(odds.calls, [])

    def test_reserva_clv_bloqueia_antes_do_endpoint(self):
        odds = FakeOdds()
        texto = auditar_payload_bruto(odds, ID, lambda *args: False)
        self.assertIn("Reserva de quota", texto)
        self.assertEqual(odds.calls, [])

    def test_resposta_com_fixture_id_diferente_falha_fechada(self):
        odds = FakeOdds()
        odds.raw["fixtureId"] = "id99999999"
        texto = auditar_payload_bruto(odds, ID, lambda *args: True)
        self.assertIn("nao corresponde", texto)
        self.assertNotIn("Markets", texto)

    def test_catalogo_ausente_nao_dispara_markets(self):
        odds = FakeOdds(catalogo=False)
        texto = auditar_payload_bruto(odds, ID, lambda *args: True)
        self.assertIn("Sem catalogo", texto)
        self.assertIn("sem chamada /markets", texto)
        self.assertEqual([c[0] for c in odds.calls], ["contexto", "/odds"])

    def test_bookmaker_ausente_nao_prova_betano_sem_mercado(self):
        odds = FakeOdds()
        odds.raw["bookmakerOdds"] = {}
        texto = auditar_payload_bruto(odds, ID, lambda *args: True)
        self.assertIn("sem bloco reconhecido", texto)
        self.assertIn("Nao prova", texto)

    def test_owner_e_repeticao_usa_cache(self):
        odds = FakeOdds()
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = bot.chat_id = 51
        bot.username = None
        bot.odds = odds
        bot._quota_permite_captura = lambda *args: True
        mensagens = []
        bot.enviar_mensagem = lambda chat, txt: mensagens.append(txt)
        cmd = "/odds_payload_audit " + ID
        bot.processar_comando(52, cmd, user_id=52)
        self.assertEqual(mensagens, [])
        bot.processar_comando(51, cmd, user_id=51)
        bot.processar_comando(51, cmd, user_id=51)
        self.assertEqual(len(mensagens), 2)
        self.assertIn("PAYLOAD BRUTO", mensagens[0])
        self.assertIn("cache", mensagens[1])
        self.assertEqual([c[0] for c in odds.calls], ["contexto", "/odds"])

    def test_limitado_a_dois_ids_por_processo(self):
        odds = FakeOdds()
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.odds = odds
        bot._quota_permite_captura = lambda *args: True
        bot._executar_odds_payload_audit(ID)
        bot._executar_odds_payload_audit("id1000015573265459")
        resposta = bot._executar_odds_payload_audit("id1000015573265460")
        self.assertIn("Limite local", resposta)
        self.assertEqual(sum(c[0] == "/odds" for c in odds.calls), 2)


if __name__ == "__main__":
    unittest.main()
