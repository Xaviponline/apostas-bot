"""Comparador SHADOW de odds de referencia (nao vinculado a uma casa).

Uma consulta gratuita /events para confirmar o fixture exato e uma consulta
manual /odds da liga, regions=eu, markets=h2h,totals (ate 2 creditos).
Sem gravar odds, sem alterar modelos, coortes, VALUE/CLV ou premium.
"""
import math
import os
import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone

from odds_auditoria import AuditoriaOdds
from odds_alternativa_shadow import SPORT, _get, _hora, _quota_txt, _seguro
import requests


IDADE_MAX_SEG = 6 * 3600
AJUSTE_KICKOFF_SEG = 15 * 60


def _dt(valor):
    try:
        dt = datetime.fromisoformat(str(valor or "").replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def _numero(valor, minimo=1.0, maximo=1000.0):
    if isinstance(valor, bool):
        return None
    try:
        v = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return v if math.isfinite(v) and minimo < v < maximo else None


def _equipa(a, b):
    # A equivalencia e exata APOS normalizacao de tokens/acentos. Sem fuzzy.
    return bool(a and b and AuditoriaOdds._canon_equipa(a)
                == AuditoriaOdds._canon_equipa(b))


def _selecao(mercado, outcome, casa, fora):
    chave = mercado.get("key")
    nome = str(outcome.get("name") or "")
    if chave == "h2h":
        if _equipa(nome, casa):
            return "Vitória Casa"
        if _equipa(nome, fora):
            return "Vitória Fora"
        if nome.casefold() in {"draw", "tie", "empate"}:
            return "Empate"
        return None
    if chave == "totals":
        try:
            linha = float(outcome.get("point"))
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(linha) or abs(linha - 2.5) > 0.00001:
            return None
        if nome.casefold() == "over":
            return "Over 2.5 Golos"
        if nome.casefold() == "under":
            return "Under 2.5 Golos"
    return None


def _recolher(evento, agora):
    """Uma observacao por bookmaker e selecao; nunca misturar linhas 1.5/3.5."""
    cotacoes = defaultdict(dict)
    desconhecidas = antigas = duplicadas = 0
    home, away = evento.get("home_team"), evento.get("away_team")
    vistos = set()
    for book in evento.get("bookmakers") or []:
        if not isinstance(book, dict) or not book.get("key"):
            continue
        bookmaker = str(book["key"]).casefold()
        for market in book.get("markets") or []:
            if not isinstance(market, dict) or market.get("key") not in {"h2h", "totals"}:
                continue
            atualizado = _dt(market.get("last_update") or book.get("last_update"))
            if atualizado is None:
                desconhecidas += 1
                continue
            delta = (agora - atualizado).total_seconds()
            if delta > IDADE_MAX_SEG or delta < -300:
                antigas += 1
                continue
            for outcome in market.get("outcomes") or []:
                if not isinstance(outcome, dict):
                    continue
                selecao = _selecao(market, outcome, home, away)
                price = _numero(outcome.get("price"))
                if not selecao or price is None:
                    continue
                ident = (bookmaker, selecao)
                if ident in vistos:
                    duplicadas += 1
                    # Um bookmaker ambiguo nao pode distorcer a mediana.
                    cotacoes[selecao].pop(bookmaker, None)
                else:
                    vistos.add(ident)
                    cotacoes[selecao][bookmaker] = price
    return cotacoes, antigas, desconhecidas, duplicadas


def _mercado_modelo(snapshot):
    nome = str(snapshot.get("mercado") or "")
    if nome in {"Vitória Casa", "Vitória Fora"}:
        return nome
    if re.fullmatch(r"(Over|Under) 2[.,]5 Golos", nome):
        return nome.replace(",", ".")
    if nome == "Empate":
        return nome
    return None


def _resumo_modelo(snapshots, evento, cotacoes, agora):
    """So vincular se nomes e hora do fixture coincidirem e selecao existir."""
    linhas = []
    if not isinstance(snapshots, list):
        return linhas
    ts_fonte = _dt(evento.get("commence_time"))
    if ts_fonte is None:
        return linhas
    for p in snapshots:
        if not isinstance(p, dict) or p.get("estado") != "pendente":
            continue
        if not _equipa(p.get("casa"), evento.get("home_team")):
            continue
        if not _equipa(p.get("fora"), evento.get("away_team")):
            continue
        try:
            ts_modelo = float(p["timestamp_jogo"])
        except (ValueError, TypeError, OverflowError, KeyError):
            continue
        if not math.isfinite(ts_modelo) or abs(ts_modelo - ts_fonte.timestamp()) > AJUSTE_KICKOFF_SEG:
            continue
        mercado = _mercado_modelo(p)
        if mercado is None:
            continue
        prob = _numero(p.get("probabilidade"), minimo=0, maximo=1.000001)
        minima = _numero(p.get("odd_minima"), minimo=1)
        if prob is None or prob > 1 or minima is None:
            continue
        preços = list(cotacoes.get(mercado, {}).values())
        linhas.append(
            f"• {mercado}: prob. modelo {prob*100:.1f}% | "
            f"odd minima congelada {minima:.2f}"
        )
        if len(preços) >= 3:
            mediana = statistics.median(preços)
            ev = (prob * mediana - 1) * 100
            linhas.append(
                f"  Mediana mercado {mediana:.2f} | EV hipotetico {ev:+.1f}% "
                "(nao e aposta validada)"
            )
        else:
            linhas.append("  Cotacao de referencia insuficiente; sem EV.")
        if len(linhas) >= 8:
            break
    return linhas


def comparar_odds_referencia(argumentos="", snapshots=None, chave=None,
                             session=None, agora=None):
    """Formato SPORT | CASA | FORA; no maximo uma consulta paga."""
    exemplo = (
        "Formato: /mercado_ref soccer_portugal_primeira_liga | Gil Vicente | FC Porto\n"
        "📊 1X2 e golos 2.5 | regiao EU | ate 2 creditos por execucao.\n"
        "🔒 Apenas SHADOW, nao publica picks nem muda coortes."
    )
    bruto = str(argumentos or "").strip()
    partes = [x.strip() for x in bruto.split("|")]
    if len(partes) != 3:
        return exemplo
    sport, casa, fora = partes
    if not SPORT.fullmatch(sport) or len(casa) < 2 or len(fora) < 2:
        return exemplo
    if len(casa) > 65 or len(fora) > 65 or _equipa(casa, fora):
        return exemplo
    if any(not all(c.isprintable() for c in p) for p in partes):
        return exemplo
    key = str(chave or os.getenv("THE_ODDS_API_KEY") or "").strip()
    if not key:
        return "⚪ THE_ODDS_API_KEY por configurar. Zero consultas."
    agora = agora or datetime.now(timezone.utc)
    sessao = session or requests.Session()

    # Descoberta sem custo antes da unica chamada que consome creditos.
    events, err, _ = _get(sessao, f"/sports/{sport}/events", {"apiKey": key})
    if err:
        return "⚠️ Eventos indisponiveis: " + err
    matches = [
        e for e in events if isinstance(e, dict)
        and _equipa(e.get("home_team"), casa)
        and _equipa(e.get("away_team"), fora)
        and _dt(e.get("commence_time")) is not None
        and _dt(e.get("commence_time")) > agora
        and isinstance(e.get("id"), str)
        and bool(re.fullmatch(r"[a-zA-Z0-9]{8,80}", e["id"]))
    ]
    if len(matches) != 1:
        return (
            "⚪ Jogo futuro nao encontrado de forma unica na lista gratuita.\n"
            "Verifica os nomes com /fonte_alt jogos " + sport + ".\n"
            "🔒 Zero creditos de odds consumidos; nao associamos equipas por aproximacao."
        )
    evento = matches[0]

    odds, erro, quota = _get(sessao, f"/sports/{sport}/odds", {
        "apiKey": key, "regions": "eu", "markets": "h2h,totals",
        "oddsFormat": "decimal", "dateFormat": "iso",
    })
    if erro:
        return "⚠️ Odds alternativas indisponiveis: " + erro
    candidatos = [
        e for e in odds if isinstance(e, dict) and e.get("id") == evento["id"]
        and _equipa(e.get("home_team"), evento.get("home_team"))
        and _equipa(e.get("away_team"), evento.get("away_team"))
        and _dt(e.get("commence_time")) == _dt(evento.get("commence_time"))
    ]
    if len(candidatos) != 1:
        return (
            "⚠️ Fixture nao confirmado de forma unica no payload de odds. "
            "Nenhuma odd associada; nao calcular EV."
        ) + _quota_txt(quota)
    jogo = candidatos[0]
    cotacoes, antigas, desconhecidas, duplicadas = _recolher(jogo, agora)
    linhas = [
        "📈 MERCADO DE REFERENCIA — SHADOW",
        f"⚽ {_seguro(jogo.get('home_team'))} vs {_seguro(jogo.get('away_team'))}",
        f"🕘 {_hora(jogo.get('commence_time'))} (Portugal)",
        f"🏆 {sport} | 1X2 + golos 2.5 | EU",
        "📌 Cada casa conta uma vez por selecao; mercados/linhas nao se misturam.",
        "",
    ]
    for rotulo, mercado in (
        ("1 (Casa)", "Vitória Casa"), ("X (Empate)", "Empate"),
        ("2 (Fora)", "Vitória Fora"), ("Mais 2.5", "Over 2.5 Golos"),
        ("Menos 2.5", "Under 2.5 Golos"),
    ):
        valores = list(cotacoes.get(mercado, {}).values())
        if len(valores) < 3:
            linhas.append(f"• {rotulo}: {len(valores)} casas | referencia insuficiente")
        else:
            minimo, mediana, maximo = min(valores), statistics.median(valores), max(valores)
            linhas.append(
                f"• {rotulo}: mediana {mediana:.2f} | "
                f"intervalo {minimo:.2f}-{maximo:.2f} | {len(valores)} casas"
            )
    linhas.extend([
        "",
        "📉 Cotacoes excluidas: "
        f"mercados antigos {antigas}, sem data {desconhecidas}, duplicados {duplicadas}.",
        "⌛ Apenas mercados atualizados nas ultimas 6 horas; jogos ainda por comecar.",
    ])
    do_modelo = _resumo_modelo(snapshots, jogo, cotacoes, agora)
    if do_modelo:
        linhas += ["", "🧠 MODELO JA REGISTADO — somente leitura:", *do_modelo]
    else:
        linhas.append(
            "🧠 Sem selecao do modelo associada com hora/equipas exatas; "
            "nao estimar VALUE nem inventar odd minima."
        )
    linhas.extend([
        "",
        "⚠️ Mediana e preco de referencia, NAO odd justa nem promessa de lucro.",
        "🔒 Nao escolhe casa nem publica picks; sem alterar V1.2/V1.3/CLV/historico.",
    ])
    return "\n".join(linhas).replace(".", ",") + _quota_txt(quota)
