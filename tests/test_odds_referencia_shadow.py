"""Regressoes offline para comparador multi-casa SHADOW. Sem rede nem quotas."""
import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from main_competicoes import BotPremiumDiarioCompeticoes
from odds_referencia_shadow import comparar_odds_referencia


AGORA = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)
KICKOFF = "2026-10-24T19:30:00Z"
FIXTURE = "aabbccddeeff001122334455"


def evento():
    return {
        "id": FIXTURE,
        "home_team": "Gil Vicente",
        "away_team": "FC Porto",
        "commence_time": KICKOFF,
    }


def book(key, home, total, quando="2026-10-23T17:50:00Z", linha=2.5):
    return {
        "key": key, "title": key,
        "markets": [
            {"key": "h2h", "last_update": quando, "outcomes": [
                {"name": "Gil Vicente", "price": home},
                {"name": "Draw", "price": 3.4},
                {"name": "FC Porto", "price": 2.1},
            ]},
            {"key": "totals", "last_update": quando, "outcomes": [
                {"name": "Over", "point": linha, "price": total},
                {"name": "Under", "point": linha, "price": 1.88},
            ]},
        ]
    }


def odds():
    x = evento()
    x["bookmakers"] = [
        book("casa_a", 1.80, 1.90),
        book("casa_b", 1.90, 1.91),
        book("casa_c", 2.00, 1.93),
        book("casa_d", 8.00, 1.10, quando="2026-10-22T09:00:00Z"),
        book("casa_e", 1.55, 5.5, linha=3.5),
    ]
    return [x]


class FakeResponse:
    def __init__(self, data):
        self.data = data
        self.status_code = 200
        self.headers = {"x-requests-last": "2", "x-requests-remaining": "496"}

    def json(self):
        return copy.deepcopy(self.data)


class FakeSession:
    def __init__(self, eventos=None, odds_data=None):
        self.events = [evento()] if eventos is None else eventos
        self.odds_data = odds() if odds_data is None else odds_data
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, dict(params)))
        if url.endswith("/events"):
            return FakeResponse(self.events)
        if url.endswith("/odds"):
            return FakeResponse(self.odds_data)
        raise AssertionError("Endpoint nao permitido: " + url)


CMD = "soccer_portugal_primeira_liga | Gil Vicente | FC Porto"


class MercadoReferenciaTests(unittest.TestCase):
    def test_medianas_e_mercado_linha_exata(self):
        sess = FakeSession()
        txt = comparar_odds_referencia(CMD, chave="SEGREDO", session=sess, agora=AGORA)
        self.assertIn("Mercado", txt.upper())
        self.assertIn("1 (Casa): mediana 1,90", txt)
        self.assertIn("1,80-2,00 | 3 casas", txt)
        self.assertIn("Mais 2,5: mediana 1,91", txt)
        self.assertIn("Mais 2,5:", txt)
        self.assertIn("Menos 2,5: mediana 1,88", txt)
        self.assertIn("1X2 + golos 2,5", txt)
        self.assertIn("Creditos consumidos na chamada: 2", txt)
        self.assertNotIn("8,00", txt)
        self.assertNotIn("5,50", txt)
        self.assertNotIn("SEGREDO", txt)
        self.assertEqual(len(sess.calls), 2)
        self.assertTrue(sess.calls[0][0].endswith("/events"))
        self.assertTrue(sess.calls[1][0].endswith("/odds"))
        self.assertEqual(sess.calls[1][1]["markets"], "h2h,totals")
        self.assertEqual(sess.calls[1][1]["regions"], "eu")

    def test_invalido_termina_sem_rede(self):
        sess = FakeSession()
        for cmd in ("", "abc", "soccer_epl | Gil Vicente",
                    "soccer_epl;rm -rf | Gil Vicente | FC Porto",
                    "soccer_epl | FC Porto | FC Porto",
                    "soccer_epl | X | Y"):
            txt = comparar_odds_referencia(cmd, chave="SEGREDO", session=sess, agora=AGORA)
            self.assertIn("Formato:", txt)
        self.assertEqual(sess.calls, [])

    def test_chave_em_falta_zero_chamadas(self):
        sess = FakeSession()
        with patch.dict("os.environ", {}, clear=True):
            txt = comparar_odds_referencia(CMD, session=sess, agora=AGORA)
        self.assertIn("por configurar", txt)
        self.assertEqual(sess.calls, [])

    def test_equipa_nao_encontrada_sem_consumo_de_odds(self):
        sess = FakeSession()
        txt = comparar_odds_referencia(
            "soccer_portugal_primeira_liga | Benfica | Sporting",
            chave="SEGREDO", session=sess, agora=AGORA)
        self.assertIn("Zero creditos de odds", txt)
        self.assertEqual(len(sess.calls), 1)

    def test_multiplo_evento_ambiguo_sem_consumo_de_odds(self):
        sess = FakeSession(eventos=[evento(), evento()])
        txt = comparar_odds_referencia(CMD, chave="SEGREDO", session=sess, agora=AGORA)
        self.assertIn("nao encontrado de forma unica", txt)
        self.assertEqual(len(sess.calls), 1)

    def test_fixture_errado_na_resposta_sem_preco(self):
        errado = odds()
        errado[0]["id"] = "ffffffff00000000"
        sess = FakeSession(odds_data=errado)
        txt = comparar_odds_referencia(CMD, chave="SEGREDO", session=sess, agora=AGORA)
        self.assertIn("Fixture nao confirmado", txt)
        self.assertNotIn("mediana", txt)
        self.assertEqual(len(sess.calls), 2)

    def test_sem_probabilidade_do_modelo_nao_inventa_valor(self):
        sess = FakeSession()
        txt = comparar_odds_referencia(CMD, snapshots=[{
            "casa": "Gil Vicente", "fora": "FC Porto",
            "estado": "pendente", "mercado": "Over 2.5 Golos",
            "probabilidade": 0.6, "odd_minima": 1.75,
            "timestamp_jogo": datetime(2026,10,24, 21,0,tzinfo=timezone.utc).timestamp(),
        }], chave="SEGREDO", session=sess, agora=AGORA)
        self.assertIn("Sem selecao do modelo", txt)
        self.assertNotIn("EV hipotetico", txt)
        self.assertNotIn("odd minima congelada", txt)

    def test_mercado_modelo_compativel_e_preco_fresco(self):
        sess = FakeSession()
        txt = comparar_odds_referencia(CMD, snapshots=[{
            "casa": "Gil Vicente", "fora": "Porto",
            "estado": "pendente", "mercado": "Over 2.5 Golos",
            "probabilidade": .60, "odd_minima": 1.75,
            "timestamp_jogo": datetime(2026,10,24,19,30,tzinfo=timezone.utc).timestamp(),
        }], chave="SEGREDO", session=sess, agora=AGORA)
        self.assertIn("prob, modelo 60,0%", txt)
        self.assertIn("odd minima congelada 1,75", txt)
        self.assertIn("EV hipotetico +14,6%", txt)
        self.assertIn("nao e aposta validada", txt)

    def test_preco_futuro_ou_malformado_e_rejeitado(self):
        o = odds()
        o[0]["bookmakers"].append(book("casa_f", 99.9, 1.11, quando="2026-10-23T20:00:00Z"))
        o[0]["bookmakers"].append(book("casa_g", float("nan"), 1.22))
        sess = FakeSession(odds_data=o)
        txt = comparar_odds_referencia(CMD, chave="SEGREDO", session=sess, agora=AGORA)
        self.assertIn("1 (Casa): mediana 1,90", txt)
        self.assertNotIn("nan", txt.casefold())

    def test_comando_apenas_owner_e_cache(self):
        sess = FakeSession()
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = bot.chat_id = 51
        bot.username = None
        bot.previsoes = type("Previsoes", (), {"dados": {"previsoes": []}})()
        enviados = []
        bot.enviar_mensagem = lambda chat, txt: enviados.append(txt)
        with patch("odds_referencia_shadow.requests.Session", return_value=sess):
            with patch("odds_referencia_shadow.datetime") as mock_dt:
                mock_dt.now.return_value = AGORA
                with patch.dict("os.environ", {"THE_ODDS_API_KEY": "SEGREDO"}):
                    cmd = "/mercado_ref " + CMD
                    bot.processar_comando(52, cmd, user_id=52)
                    self.assertEqual(enviados, [])
                    bot.processar_comando(51, cmd, user_id=51)
                    bot.processar_comando(51, cmd, user_id=51)
                    bot.processar_comando(51,
                         "/mercado_ref soccer_epl | Chelsea | Liverpool", user_id=51)
        self.assertEqual(len(sess.calls), 2)
        self.assertEqual(len(enviados), 3)
        self.assertIn("cache", enviados[1])
        self.assertIn("Limite de uma comparacao", enviados[2])


if __name__ == "__main__":
    unittest.main()
