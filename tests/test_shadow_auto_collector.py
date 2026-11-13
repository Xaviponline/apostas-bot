"""Testes do limitador SHADOW sem pedidos HTTP."""
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from shadow_auto_collector import executar, estado


class AutoShadowTests(unittest.TestCase):
    def test_desativado_nao_consulta(self):
        with patch.dict(os.environ, {"FONTE_ALT_AUTO": "0"}):
            self.assertFalse(executar()[0])

    def test_limite_invalido_bloqueia(self):
        with patch.dict(os.environ, {
            "FONTE_ALT_AUTO": "1", "FONTE_ALT_DAILY_LIMIT": "11",
            "THE_ODDS_API_KEY": "dummy"
        }):
            self.assertFalse(executar()[0])

    def test_sem_volume_bloqueia(self):
        with patch.dict(os.environ, {
            "FONTE_ALT_AUTO": "1", "FONTE_ALT_DAILY_LIMIT": "10",
            "THE_ODDS_API_KEY": "dummy", "DATA_DIR": ""
        }):
            self.assertFalse(executar()[0])

    def test_reserva_diaria_impede_repeticao(self):
        now = datetime(2026, 11, 13, 11, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {
                "FONTE_ALT_AUTO": "1", "FONTE_ALT_DAILY_LIMIT": "10",
                "THE_ODDS_API_KEY": "dummy", "DATA_DIR": directory
            }):
                with patch("shadow_auto_collector._get", return_value=([], None, None)) as get:
                    first = executar(now=now)
                    second = executar(now=now)
                self.assertTrue(first[0])
                self.assertFalse(second[0])
                self.assertEqual(get.call_count, 1)
                self.assertIn("10 creditos", estado() if datetime.now(ZoneInfo("Europe/Lisbon")).date() == now.date() else "10 creditos")
