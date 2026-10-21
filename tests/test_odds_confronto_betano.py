"""Testes offline da comparacao manual de Betano PT vs OddsPapi."""
import copy
import unittest
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from odds_confronto_betano import confrontar_betano
from main_competicoes import BotPremiumDiarioCompeticoes

PT = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2026, 10, 21, 13, 40, tzinfo=PT)
DIA = datetime(2026, 10, 23, 22, 0, tzinfo=PT)
COMANDO = "2026-10-23 22:00 | Gimnasia y Esgrima de La Plata | CA Sarmiento"


class FakeOdds:
    provider = "oddspapi"
    configurada = True
    papi_bookmaker = "betano.pt"
    _catalogo_mercados = None

    def __init__(self, fixtures=None, odds=None):
        self.fixtures = fixtures if fixtures is not None else [{
            "fixtureId": "id123",
            "participant1Name": "Gimnasia La Plata",
            "participant2Name": "CA Sarmiento Junin",
            "startTime": DIA.isoformat(),
            "tournamentName": "Primera LPF",
        }]
        self.odds = odds if odds is not None else {
            "id": "id123", "casa": "Gimnasia La Plata",
            "fora": "CA Sarmiento Junin", "bookmaker_disponivel": True,
            "updatedAt": "2026-10-21T11:10:00Z",
            "mercados": [
                {
                    "id": "101", "name": "Full Time Result", "period": "fulltime",
                    "odds": [
                        {"seleção": "1", "odd": 1.62},
                        {"seleção": "X", "odd": 3.35},
                        {"seleção": "2", "odd": 4.85},
                    ],
                },
                {
                    "id": "1010", "name": "Over Under Full Time", "period": "fulltime",
                    "handicap": 2.5,
                    "odds": [
                        {"seleção": "Over", "odd": 1.91},
                        {"seleção": "Under", "odd": 1.62},
                    ],
                },
                {
                    "id": "200", "name": "Both Teams to Score", "period": "fulltime",
                    "odds": [
                        {"seleção": "Yes", "odd": 1.88},
                        {"seleção": "No", "odd": 1.65},
                    ],
                },
            ],
        }
        self.calls = []

    def _get_papi(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        if endpoint != "/fixtures":
            raise AssertionError("Nao permitido outra chamada direta")
        return copy.deepcopy(self.fixtures)

    def contexto_operacao(self, nome):
        return nullcontext()

    def odds_evento(self, id):
        self.calls.append(("/odds", id))
        return copy.deepcopy(self.odds)

    def diagnostico_evento(self, id):
        return "odds_http_404"


class ConfrontoOddsTests(unittest.TestCase):
    def test_fixture_unico_sem_statusid_e_sete_mercados(self):
        f = FakeOdds()
        chamadas = []
        def permitir(tipo, minimo):
            chamadas.append((tipo, minimo))
            return True
        resposta = confrontar_betano(f, COMANDO, permitir, agora=AGORA)
        self.assertIn("ambas equipas + hora: 1", resposta)
        self.assertIn("1 - Casa: 1.62", resposta)
        self.assertIn("X - Empate: 3.35", resposta)
        self.assertIn("2 - Fora: 4.85", resposta)
        self.assertIn("Mais 2,5: 1.91", resposta)
        self.assertIn("Menos 2,5: 1.62", resposta)
        self.assertIn("Ambas SIM: 1.88", resposta)
        self.assertIn("Ambas NAO: 1.65", resposta)
        self.assertEqual([c[0] for c in f.calls], ["/fixtures", "/odds"])
        self.assertNotIn("statusId", f.calls[0][1])
        self.assertEqual(chamadas, [("ODDS_AUTO", 25), ("ODDS_AUTO", 25)])

    def test_sem_correspondencia_nao_gasta_odds(self):
        f = FakeOdds(fixtures=[])
        t = confrontar_betano(f, COMANDO, lambda *x: True, agora=AGORA)
        self.assertIn("nao identificado", t)
        self.assertIn("nao comprova que falte na Betano", t)
        self.assertEqual([x[0] for x in f.calls], ["/fixtures"])

    def test_duplicado_nao_aceite(self):
        f = FakeOdds()
        f.fixtures.append(dict(f.fixtures[0], fixtureId="outro"))
        t = confrontar_betano(f, COMANDO, lambda *x: True, agora=AGORA)
        self.assertIn("ambas equipas + hora: 2", t)
        self.assertEqual([x[0] for x in f.calls], ["/fixtures"])

    def test_hora_desfasada_nao_aceite(self):
        f = FakeOdds()
        f.fixtures[0]["startTime"] = (DIA + timedelta(hours=4)).isoformat()
        t = confrontar_betano(f, COMANDO, lambda *x: True, agora=AGORA)
        self.assertIn("ambas equipas + hora: 0", t)
        self.assertEqual([x[0] for x in f.calls], ["/fixtures"])

    def test_bookmaker_ausente_nao_prova_mercado_ausente_na_betano(self):
        f = FakeOdds(odds={
            "id": "id123", "casa": "Gimnasia La Plata", "fora": "CA Sarmiento Junin",
            "bookmaker_disponivel": False, "mercados": [],
        })
        t = confrontar_betano(f, COMANDO, lambda *x: True, agora=AGORA)
        self.assertIn("Betano no payload OddsPapi: NAO", t)
        self.assertIn("nao prova mercado inexistente", t)

    def test_payload_id_divergente_bloqueia_preco(self):
        f = FakeOdds()
        f.odds["id"] = "outro"
        t = confrontar_betano(f, COMANDO, lambda *x: True, agora=AGORA)
        self.assertIn("incompativel", t)
        self.assertNotIn("1 - Casa: 1.62", t)

    def test_reserva_quota_antes_de_qualquer_consulta(self):
        f = FakeOdds()
        t = confrontar_betano(f, COMANDO, lambda *x: False, agora=AGORA)
        self.assertIn("Reserva de quota", t)
        self.assertEqual(f.calls, [])

    def test_reserva_quota_impede_segundo_endpoint(self):
        f = FakeOdds()
        calls = 0
        def permitir(*args):
            nonlocal calls
            calls += 1
            return calls == 1
        t = confrontar_betano(f, COMANDO, permitir, agora=AGORA)
        self.assertIn("/odds suspenso", t)
        self.assertEqual([x[0] for x in f.calls], ["/fixtures"])

    def test_argumento_invalido_ou_jogo_antigo_nunca_consulta(self):
        f = FakeOdds()
        for a in ("", "2026-10-20 22:00 | Casa | Fora",
                  "2026-10-23 22:00 | Casa", "2027-02-20 22:00 | Casa | Fora",
                  "2026-10-23 22:00 | Casa | Fora | Injetar"):
            self.assertIn("Formato", confrontar_betano(f, a, lambda *x: True, agora=AGORA))
        self.assertEqual(f.calls, [])

    def test_owner_e_cache_repeticao(self):
        f = FakeOdds()
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = bot.chat_id = 51
        bot.username = None
        bot.odds = f
        bot._quota_permite_captura = lambda *args: True
        mensagens = []
        bot.enviar_mensagem = lambda chat, texto: mensagens.append(texto)
        comando = "/odds_confronto " + COMANDO
        bot.processar_comando(52, comando, user_id=52)
        self.assertEqual(mensagens, [])
        bot.processar_comando(51, comando, user_id=51)
        bot.processar_comando(51, comando, user_id=51)
        self.assertEqual(len(mensagens), 2)
        self.assertIn("CONFRONTO BETANO PT", mensagens[0])
        self.assertIn("cache", mensagens[1])
        self.assertEqual([x[0] for x in f.calls], ["/fixtures", "/odds"])


if __name__ == "__main__":
    unittest.main()
