import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from main_sofascore import BotPremiumReal


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


if __name__ == "__main__":
    unittest.main()
