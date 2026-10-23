"""Diagnostico manual, isolado, para fonte alternativa The Odds API v4.

OWNER/ADMIN no handler. Nao participa no pipeline produtivo (V1.2, SEL1,
V1.3, VALUE, CLV) e nao guarda precos ou altera o motor de odds.
GET /sports e /events: custo zero segundo a documentacao do fornecedor.
GET /odds: explicitamente uma unica liga, EU, h2h+totals (ate 2 creditos).
"""
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests


BASE = "https://api.the-odds-api.com/v4"
SPORT = re.compile(r"soccer_[a-z0-9_]{2,60}\Z", re.ASCII)
TZ = ZoneInfo("Europe/Lisbon")


def _seguro(valor, tamanho=80):
    return "".join(c for c in " ".join(str(valor or "").split())
                   if c.isprintable())[:tamanho]


def _hora(valor):
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return "sem fuso"
        return dt.astimezone(TZ).strftime("%d/%m %H:%M")
    except (ValueError, TypeError):
        return "hora indisponivel"


def _get(session, path, parametros):
    """Nunca devolver excecoes HTTP/URL com chave em query string."""
    try:
        resposta = session.get(BASE + path, params=parametros, timeout=(5, 20))
        code = int(resposta.status_code)
        if code != 200:
            return None, f"HTTP {code} (credenciais/plano/fonte a verificar)", None
        dados = resposta.json()
        if not isinstance(dados, list):
            return None, "formato de resposta inesperado", None
        headers = resposta.headers or {}
        quota = {
            k: _seguro(headers.get(k) or "?", 14)
            for k in ("x-requests-last", "x-requests-remaining")
        }
        return dados, None, quota
    except (requests.RequestException, ValueError, TypeError, OverflowError):
        return None, "consulta indisponivel (sem detalhes sensiveis)", None


def _quota_txt(quota):
    if not quota:
        return ""
    return (
        f"\n📊 Creditos consumidos na chamada: {quota['x-requests-last']}"
        f" | restantes: {quota['x-requests-remaining']}"
    )


def testar_fonte_alternativa(argumentos="", chave=None, session=None):
    """Uma operacao solicitada pelo OWNER; nunca executada automaticamente."""
    args = str(argumentos or "").strip().split(maxsplit=2)
    if not args:
        estado = "configurada" if (chave or os.getenv("THE_ODDS_API_KEY")) else "por configurar"
        return (
            "🧪 FONTE ALTERNATIVA — THE ODDS API (SHADOW)\n"
            f"🔑 Estado: {estado}\n"
            "• /fonte_alt ligas — listar ligas de futebol (zero creditos)\n"
            "• /fonte_alt ligas portugal — procurar uma liga (zero creditos)\n"
            "• /fonte_alt jogos soccer_portugal_primeira_liga — eventos (zero creditos)\n"
            "• /fonte_alt odds soccer_portugal_primeira_liga — UMA consulta h2h+totals, regiao eu (ate 2 creditos)\n"
            "🔒 Nao utiliza Betano PT nem altera picks/odds de producao."
        )
    operacao = args[0].casefold()
    if operacao not in {"ligas", "jogos", "odds"}:
        return "⚠️ Operacao desconhecida. Usa /fonte_alt."
    if operacao in {"jogos", "odds"} and (
        len(args) != 2 or not SPORT.fullmatch(args[1])
    ):
        return "⛔ Formato: /fonte_alt jogos|odds soccer_nome_da_liga. Zero chamadas."
    if operacao == "ligas":
        if len(args) > 2 or (len(args) == 2 and len(args[1]) > 45):
            return "⛔ Pesquisa demasiado longa. Usa /fonte_alt ligas portugal."
    valor = str(chave or os.getenv("THE_ODDS_API_KEY") or "").strip()
    if not valor:
        return "⚪ THE_ODDS_API_KEY nao configurada. Zero chamadas."
    sessao = session or requests.Session()
    if operacao == "ligas":
        dados, erro, quota = _get(sessao, "/sports/", {"apiKey": valor})
        if erro:
            return "⚠️ Fonte alternativa: " + erro
        filtro = args[1].casefold() if len(args) == 2 else ""
        ligas = [
            x for x in dados if isinstance(x, dict)
            and str(x.get("key") or "").startswith("soccer_")
            and (not filtro or filtro in str(x.get("key") or "").casefold()
                 or filtro in str(x.get("title") or "").casefold())
        ]
        saida = [
            "⚽ LIGAS NA THE ODDS API — SHADOW",
            f"📚 Ligas de futebol correspondentes: {len(ligas)}"
        ]
        for x in ligas[:16]:
            saida.append(f"• {_seguro(x.get('title'), 45)} — {_seguro(x.get('key'), 70)}")
        if len(ligas) > 16:
            saida.append(f"↳ +{len(ligas)-16} (filtra com /fonte_alt ligas portugal)")
        saida.append("🔒 Endpoint gratuito; sem alterar modelo, picks ou odds.")
        return "\n".join(saida) + _quota_txt(quota)

    sport = args[1]
    if operacao == "jogos":
        dados, erro, quota = _get(sessao, f"/sports/{sport}/events",
                                  {"apiKey": valor})
        if erro:
            return "⚠️ Eventos: " + erro
        linhas = [
            f"📅 EVENTOS THE ODDS API — {sport}",
            f"📚 Jogos devolvidos: {len(dados)}",
        ]
        for e in dados[:8]:
            if not isinstance(e, dict):
                continue
            linhas.append(f"• {_hora(e.get('commence_time'))} | "
                         f"{_seguro(e.get('home_team'), 38)} vs "
                         f"{_seguro(e.get('away_team'), 38)}")
        linhas.append("🔒 Sem cotacoes; esta listagem nao valida Betano PT.")
        return "\n".join(linhas) + _quota_txt(quota)

    dados, erro, quota = _get(sessao, f"/sports/{sport}/odds", {
        "apiKey": valor, "regions": "eu", "markets": "h2h,totals",
        "oddsFormat": "decimal", "dateFormat": "iso"
    })
    if erro:
        return "⚠️ Odds alternativas: " + erro
    bookmakers = {}
    por_mercado = {"h2h": 0, "totals": 0}
    for e in dados:
        if not isinstance(e, dict):
            continue
        for b in e.get("bookmakers") or []:
            if not isinstance(b, dict):
                continue
            key = _seguro(b.get("key"), 50)
            if key:
                bookmakers[key] = _seguro(b.get("title"), 45)
            for m in b.get("markets") or []:
                if isinstance(m, dict) and m.get("key") in por_mercado:
                    if isinstance(m.get("outcomes"), list) and m["outcomes"]:
                        por_mercado[m["key"]] += 1
    linhas = [
        "🧪 ODDS ALTERNATIVAS — SHADOW",
        f"🏆 Liga: {sport} | regiao: eu",
        f"📚 Jogos devolvidos: {len(dados)}",
        f"🏦 Bookmakers distintos: {len(bookmakers)}",
        f"📊 Presencas de mercado: 1X2={por_mercado['h2h']} | Totais={por_mercado['totals']}",
    ]
    if bookmakers:
        linhas.append("🏷️ Exemplos: " + ", ".join(list(bookmakers.values())[:6]))
    for e in dados[:3]:
        if isinstance(e, dict):
            linhas.append(f"• {_hora(e.get('commence_time'))}: "
                          f"{_seguro(e.get('home_team'), 30)} vs "
                          f"{_seguro(e.get('away_team'), 30)}")
    linhas.extend([
        "⚠️ Nao representa cotacoes da Betano Portugal nem valida VALUE/CLV.",
        "🔒 Consulta manual sem guardar odds ou alterar previsoes.",
    ])
    return "\n".join(linhas) + _quota_txt(quota)
