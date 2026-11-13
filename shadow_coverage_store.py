"""Historico SHADOW isolado: apenas respostas manuais de linhas, sem API externa."""
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_MARKETS = ("Under 2.5", "Over 2.5", "Under 3.5", "Over 3.5")


def _db_path():
    # Persistencia apenas em volume configurado; nunca no filesystem efemero.
    base = os.getenv("DATA_DIR", "").strip()
    if not base:
        return None
    path = Path(base).resolve()
    if not path.is_dir():
        return None
    return path / "fonte_alt_shadow.sqlite3"


def registar_linhas(comando, resposta):
    """Guarda apenas contagens agregadas; nao grava odds nem chaves."""
    if not str(comando).startswith("linhas ") or "🎯 LINHAS EXATAS" not in str(resposta):
        return False
    path = _db_path()
    if path is None:
        return False
    counts = {}
    for market in _MARKETS:
        match = re.search(r"(?m)^• " + re.escape(market) + r": (\d+) casas$", resposta)
        if match is None:
            return False
        counts[market] = int(match.group(1))
    # Nao guardar nomes de equipas sem limite; comando normalizado/truncado.
    fixture = " ".join(str(comando).split())[:220]
    with sqlite3.connect(str(path), timeout=3) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS shadow_coverage (
            fixture TEXT PRIMARY KEY, checked_at TEXT NOT NULL,
            under25 INTEGER NOT NULL, over25 INTEGER NOT NULL,
            under35 INTEGER NOT NULL, over35 INTEGER NOT NULL)""")
        db.execute("""INSERT OR REPLACE INTO shadow_coverage
            (fixture, checked_at, under25, over25, under35, over35)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (fixture, datetime.now(timezone.utc).isoformat(),
             counts["Under 2.5"], counts["Over 2.5"],
             counts["Under 3.5"], counts["Over 3.5"]))
    return True


def historico_cobertura():
    """Resumo local read-only, sem qualquer chamada de rede."""
    path = _db_path()
    if path is None or not path.exists():
        return "📊 HISTORICO SHADOW: sem volume DATA_DIR ou sem registos. Zero pedidos."
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3) as db:
            total, u25, o25, u35, o35 = db.execute(
                """SELECT COUNT(*), SUM(under25 > 0), SUM(over25 > 0),
                   SUM(under35 > 0), SUM(over35 > 0) FROM shadow_coverage"""
            ).fetchone()
        total = int(total or 0)
        return ("📊 HISTORICO THE ODDS API — SHADOW (VOLUME)\n"
                f"• Jogos distintos analisados: {total}\n"
                f"• Under 2.5: {int(u25 or 0)}/{total}\n"
                f"• Over 2.5: {int(o25 or 0)}/{total}\n"
                f"• Under 3.5: {int(u35 or 0)}/{total}\n"
                f"• Over 3.5: {int(o35 or 0)}/{total}\n"
                "🔒 Sem HTTP, sem picks ou CLV.")
    except (sqlite3.Error, OSError):
        return "⚠️ Historico SHADOW indisponivel. Zero pedidos."
