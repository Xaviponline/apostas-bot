import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from main_sofascore import BotPremiumReal




class BuscadorRetryFake:
    def __init__(self, jogo):
        self.jogo = jogo
        self.chamadas = 0

    def buscar_todos_jogos_hoje(self, data_iso):
        self.chamadas += 1
        return [] if self.chamadas == 1 else [self.jogo]


class LocalDateTests(unittest.TestCase):
    @staticmethod
    def ts_local(data_hora):
        dt = datetime.fromisoformat(data_hora).replace(tzinfo=ZoneInfo("Europe/Lisbon"))
        return dt.astimezone(timezone.utc).timestamp()

    def test_filter_keeps_only_requested_portugal_date(self):
        jogos = [
            {"id": 1, "timestamp": self.ts_local("2026-09-14T23:30:00")},
            {"id": 2, "timestamp": self.ts_local("2026-09-15T00:00:00")},
            {"id": 3, "timestamp": self.ts_local("2026-09-15T01:30:00")},
        ]
        filtrados = BotPremiumReal._filtrar_data_portugal(jogos, "2026-09-14")
        self.assertEqual([j["id"] for j in filtrados], [1])

    def test_filter_drops_missing_timestamp(self):
        jogos = [{"id": 1}, {"id": 2, "timestamp": None}]
        self.assertEqual(BotPremiumReal._filtrar_data_portugal(jogos, "2026-09-14"), [])

    def test_recolha_repete_uma_vez_quando_primeira_lista_vem_vazia(self):
        agora = datetime.now(ZoneInfo("Europe/Lisbon"))
        jogo = {"id": 99, "timestamp": agora.timestamp() + 3600}
        buscador = BuscadorRetryFake(jogo)
        bot = object.__new__(BotPremiumReal)
        bot.buscador = buscador
        bot.JOGOS_RETRY_VAZIO_SEG = 0

        jogos = bot._jogos_hoje_portugal()

        self.assertEqual([j["id"] for j in jogos], [99])
        self.assertEqual(buscador.chamadas, 2)


if __name__ == "__main__":
    unittest.main()
