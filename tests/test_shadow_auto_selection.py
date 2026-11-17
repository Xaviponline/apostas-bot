"""Selecao SHADOW AUTO sem rede nem consumo de creditos."""
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from shadow_auto_collector import _historico_fixture, _scout_prioridade


class PrioridadeShadowTests(unittest.TestCase):
    def test_scout_prioriza_ranking_e_ignora_passados(self):
        now = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"DATA_DIR": folder}):
            payload = {"versao": 1, "dias": {"2026-11-17": {"selecoes": [
                {"ranking": 3, "timestamp_jogo": now.timestamp() + 86400,
                 "sport": "soccer_epl", "casa": "Arsenal", "fora": "Chelsea"},
                {"ranking": 1, "timestamp_jogo": now.timestamp() - 10,
                 "sport": "soccer_epl", "casa": "Fulham", "fora": "Liverpool"},
            ]}}}
            (Path(folder) / "scout_shadow.json").write_text(json.dumps(payload))
            self.assertEqual(_scout_prioridade(now)[3], "Arsenal")

    def test_scout_sem_ficheiro_falha_fechado(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"DATA_DIR": folder}):
            self.assertIsNone(_scout_prioridade(datetime.now(timezone.utc)))

    def test_historico_exclui_dia_atual(self):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE shadow_auto_runs (day TEXT, fixture TEXT)")
        db.executemany("INSERT INTO shadow_auto_runs VALUES (?,?)", [
            ("2026-11-16", "linhas soccer_epl | City | Fulham"),
            ("2026-11-17", "linhas soccer_epl | Arsenal | Chelsea")])
        self.assertEqual(_historico_fixture(db, "2026-11-17"),
                         {"linhas soccer_epl | City | Fulham"})
        db.close()


if __name__ == "__main__":
    unittest.main()
