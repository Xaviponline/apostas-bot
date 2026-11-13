"""Recolha automatica SHADOW isolada, com reserva conservadora de quota.

Uma chamada paga por dia (reserva de 10 creditos), apenas quando explicitamente
ativada. Persistencia SQLite em DATA_DIR; falha fechada sem volume/sem chave.
"""
import os
import re
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from odds_alternativa_shadow import _get, testar_fonte_alternativa
from shadow_coverage_store import _db_path, registar_linhas

_LISBON = ZoneInfo("Europe/Lisbon")
_MAX_DAILY = 10
# Reservar o teto completo antes de qualquer chamada paga: sem assumir que
# um endpoint tem sempre o mesmo custo, evita exceder a autorizacao.
_RESERVATION = 10


def _connect():
    path = _db_path()
    if path is None:
        return None
    db = sqlite3.connect(str(path), timeout=5, isolation_level=None)
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("""CREATE TABLE IF NOT EXISTS shadow_auto_runs (
        day TEXT PRIMARY KEY, started_at TEXT NOT NULL,
        reserved INTEGER NOT NULL, actual INTEGER,
        status TEXT NOT NULL, fixture TEXT)""")
    return db


def estado():
    """Monitorizacao local sem HTTP, sem mostrar credenciais."""
    try:
        db = _connect()
        if db is None:
            return "⚠️ SHADOW AUTO: volume indisponivel. Zero pedidos."
        with db:
            day = datetime.now(_LISBON).date().isoformat()
            row = db.execute(
                "SELECT reserved, actual, status, fixture FROM shadow_auto_runs WHERE day=?",
                (day,)).fetchone()
        db.close()
        if not row:
            return "📊 SHADOW AUTO: nenhuma consulta paga hoje. Limite: 10 creditos/dia."
        reserved, actual, status, fixture = row
        return (f"📊 SHADOW AUTO — {day}\n"
                f"• Estado: {status}\n"
                f"• Reserva maxima: {reserved}/10 creditos\n"
                f"• Consumo reportado: {actual if actual is not None else 'desconhecido'}\n"
                f"• Jogo: {fixture or 'nao selecionado'}\n"
                "🔒 Apenas SHADOW; sem picks, CLV ou apostas.")
    except (sqlite3.Error, OSError):
        return "⚠️ SHADOW AUTO: monitorizacao indisponivel. Zero pedidos."


def executar(now=None, session=None):
    """Uma tentativa/dia; nao repete em erros/reinicios. Retorna (fez, texto)."""
    now = now or datetime.now(_LISBON)
    if os.getenv("FONTE_ALT_AUTO", "0") != "1":
        return False, "SHADOW AUTO desativado."
    # Nao permitir configurar acima do limite autorizado.
    try:
        configured = int(os.getenv("FONTE_ALT_DAILY_LIMIT", "0"))
    except ValueError:
        return False, "Limite diario invalido."
    if configured != _MAX_DAILY:
        return False, "Limite diario nao confirmado (10)."
    key = os.getenv("THE_ODDS_API_KEY", "").strip()
    if not key:
        return False, "THE_ODDS_API_KEY indisponivel."
    try:
        db = _connect()
        if db is None:
            return False, "Volume indisponivel; zero pedidos."
        day = now.astimezone(_LISBON).date().isoformat()
        # Reserva atomica antes de qualquer chamada, segura contra reinicios
        # e duas instancias concorrentes. Nunca reembolsar automaticamente.
        with db:
            inserted = db.execute(
                """INSERT OR IGNORE INTO shadow_auto_runs
                (day, started_at, reserved, actual, status, fixture)
                VALUES (?, ?, ?, NULL, 'reserved', NULL)""",
                (day, now.astimezone(timezone.utc).isoformat(), _RESERVATION)
            ).rowcount
        if not inserted:
            db.close()
            return False, "SHADOW AUTO ja reservado hoje; zero pedidos."
        import requests
        sess = session or requests.Session()
        events, error, _ = _get(sess, "/sports/soccer_epl/events", {"apiKey": key})
        if error or not isinstance(events, list):
            db.execute("UPDATE shadow_auto_runs SET status='events_error' WHERE day=?", (day,))
            db.close()
            return True, "SHADOW AUTO: eventos indisponiveis; sem consulta paga."
        # Apenas um evento futuro com identificacao inequivoca.
        from odds_referencia_shadow import _dt
        future = sorted(
            (e for e in events if isinstance(e, dict)
             and _dt(e.get("commence_time")) is not None
             and _dt(e.get("commence_time")) > now.astimezone(timezone.utc)
             and isinstance(e.get("home_team"), str)
             and isinstance(e.get("away_team"), str)
             and 2 <= len(e["home_team"]) <= 65
             and 2 <= len(e["away_team"]) <= 65
             and "|" not in e["home_team"] and "|" not in e["away_team"]),
            key=lambda e: e["commence_time"])
        if not future:
            db.execute("UPDATE shadow_auto_runs SET status='no_events' WHERE day=?", (day,))
            db.close()
            return True, "SHADOW AUTO: sem jogos futuros; zero consultas pagas."
        game = future[0]
        command = f"linhas soccer_epl | {game['home_team']} | {game['away_team']}"
        db.execute("UPDATE shadow_auto_runs SET fixture=?, status='requested' WHERE day=?",
                   (command[:220], day))
        response = testar_fonte_alternativa(command, chave=key, session=sess)
        match = re.search(r"Creditos consumidos na chamada: (\d+)", response)
        actual = int(match.group(1)) if match else None
        success = "🎯 LINHAS EXATAS" in response
        if success:
            registar_linhas(command, response)
        db.execute("UPDATE shadow_auto_runs SET actual=?, status=? WHERE day=?",
                   (actual, "ok" if success else "no_lines", day))
        db.close()
        return True, ("SHADOW AUTO: linhas guardadas." if success
                      else "SHADOW AUTO: sem linhas validas.")
    except (sqlite3.Error, OSError, ValueError, TypeError, RuntimeError):
        return False, "SHADOW AUTO: erro isolado; sem repeticao automatica."
