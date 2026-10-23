"""Testes offline para The Odds API shadow. Zero rede, zero dados persistidos."""
import unittest
from unittest.mock import patch

from main_competicoes import BotPremiumDiarioCompeticoes
from odds_alternativa_shadow import testar_fonte_alternativa


class FakeResponse:
    status_code = 200

    def __init__(self, data, code=200):
        self.data = data
        self.status_code = code
        self.headers = {
            "x-requests-last": "2",
            "x-requests-remaining": "498",
        }

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, dict(params), timeout))
        return self.response


class FonteAltTests(unittest.TestCase):
    def test_status_sem_key_sem_rede(self):
        with patch.dict("os.environ", {}, clear=True):
            texto = testar_fonte_alternativa()
        self.assertIn("por configurar", texto)
        self.assertIn("zero creditos", texto)
        self.assertIn("Nao utiliza Betano PT", texto)

    def test_invalido_zero_pedidos(self):
        s = FakeSession(FakeResponse([]))
        for argumento in ("odds", "odds outro", "jogos ../abc",
                          "odds soccer_epl?apiKey=segredo", "nao"):
            txt = testar_fonte_alternativa(argumento, chave="SEGREDO", session=s)
            self.assertTrue("Formato" in txt or "desconhecida" in txt)
        self.assertEqual(s.calls, [])

    def test_catalogo_gratis_e_filtro(self):
        s = FakeSession(FakeResponse([
            {"key": "soccer_portugal_primeira_liga", "title": "Portugal Primeira Liga"},
            {"key": "soccer_epl", "title": "Premier League"},
            {"key": "basketball_nba", "title": "NBA"},
        ]))
        txt = testar_fonte_alternativa("ligas portugal", chave="SEGREDO", session=s)
        self.assertIn("Portugal Primeira Liga", txt)
        self.assertNotIn("Premier League", txt)
        self.assertNotIn("SEGREDO", txt)
        self.assertEqual(len(s.calls), 1)
        self.assertTrue(s.calls[0][0].endswith("/sports/"))
        self.assertEqual(set(s.calls[0][1]), {"apiKey"})

    def test_eventos_somente_metadados(self):
        s = FakeSession(FakeResponse([
            {"home_team": "A", "away_team": "B",
             "commence_time": "2026-10-24T20:00:00Z"}
        ]))
        txt = testar_fonte_alternativa("jogos soccer_epl", chave="SEGREDO", session=s)
        self.assertIn("A vs B", txt)
        self.assertNotIn("SEGREDO", txt)
        self.assertTrue(s.calls[0][0].endswith("/soccer_epl/events"))
        self.assertEqual(set(s.calls[0][1]), {"apiKey"})

    def test_um_pedido_odds_so_h2h_totals_eu(self):
        s = FakeSession(FakeResponse([
            {"home_team": "A", "away_team": "B",
             "commence_time": "2026-10-24T20:00:00Z",
             "bookmakers": [{"key": "betsson", "title": "Betsson",
                             "markets": [
                                 {"key": "h2h", "outcomes": [{"name": "A", "price": 1.55}]},
                                 {"key": "totals", "outcomes": [{"name": "Over", "price": 1.9}]},
                             ]}]}
        ]))
        txt = testar_fonte_alternativa("odds soccer_epl", chave="SEGREDO", session=s)
        self.assertIn("1X2=1 | Totais=1", txt)
        self.assertIn("Creditos consumidos na chamada: 2", txt)
        self.assertIn("498", txt)
        self.assertNotIn("1.55", txt)
        self.assertNotIn("1.9", txt)
        self.assertNotIn("SEGREDO", txt)
        self.assertEqual(len(s.calls), 1)
        self.assertEqual(s.calls[0][1]["regions"], "eu")
        self.assertEqual(s.calls[0][1]["markets"], "h2h,totals")

    def test_erro_http_sem_expor_key(self):
        s = FakeSession(FakeResponse({"message": "secret SEGREDO"}, code=401))
        txt = testar_fonte_alternativa("ligas", chave="SEGREDO", session=s)
        self.assertIn("HTTP 401", txt)
        self.assertNotIn("SEGREDO", txt)

    def test_owner_e_cache_nao_repetem_consultas(self):
        s = FakeSession(FakeResponse([]))
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = bot.chat_id = 51
        bot.username = None
        enviados = []
        bot.enviar_mensagem = lambda cid, txt: enviados.append(txt)
        with patch("odds_alternativa_shadow.requests.Session", return_value=s):
            with patch.dict("os.environ", {"THE_ODDS_API_KEY": "SEGREDO"}):
                bot.processar_comando(52, "/fonte_alt odds soccer_epl", user_id=52)
                self.assertEqual(enviados, [])
                bot.processar_comando(51, "/fonte_alt odds soccer_epl", user_id=51)
                bot.processar_comando(51, "/fonte_alt odds soccer_epl", user_id=51)
                bot.processar_comando(51, "/fonte_alt odds soccer_spain_la_liga", user_id=51)
        self.assertEqual(len(s.calls), 1)
        self.assertIn("cache", enviados[1])
        self.assertIn("Limite de um teste pago", enviados[2])


if __name__ == "__main__":
    unittest.main()
