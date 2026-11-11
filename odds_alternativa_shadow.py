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


def _get(session, path, parametros, aceitar_objeto=False):
    """Nunca devolver excecoes HTTP/URL com chave em query string."""
    try:
        resposta = session.get(BASE + path, params=parametros, timeout=(5, 20))
        code = int(resposta.status_code)
        if code != 200:
            return None, f"HTTP {code} (credenciais/plano/fonte a verificar)", None
        dados = resposta.json()
        if not isinstance(dados, list) and not (aceitar_objeto and isinstance(dados, dict)):
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
            "• /fonte_alt cobertura — resumo da cache local (zero creditos)\n"
            "• /fonte_alt linhas soccer_epl | Manchester City | Fulham — Under/Over 2.5 e 3.5 por casa (consulta paga)\n"
            "• /fonte_alt mercados soccer_epl | Manchester City | Fulham — catalogo por jogo (consulta paga)\n"
            "• /fonte_alt odds soccer_portugal_primeira_liga — h2h+totals, regiao EU (consulta paga)\n"
            "🔒 Nao utiliza Betano PT nem altera picks/odds de producao."
        )
    # Consulta manual de uma unica partida, apenas linhas exatas 2.5/3.5.
    if str(argumentos or "").strip().casefold().startswith("linhas "):
        from odds_referencia_shadow import _dt, _equipa, _numero
        partes = [p.strip() for p in str(argumentos).strip()[len("linhas "):].split("|")]
        if (len(partes) != 3 or not SPORT.fullmatch(partes[0])
                or not all(2 <= len(p) <= 65 and p.isprintable() for p in partes[1:])
                or _equipa(partes[1], partes[2])):
            return "Formato: /fonte_alt linhas soccer_liga | Equipa Casa | Equipa Fora."
        valor = str(chave or os.getenv("THE_ODDS_API_KEY") or "").strip()
        if not valor:
            return "⚪ THE_ODDS_API_KEY nao configurada. Zero chamadas."
        sport, casa, fora = partes
        sessao = session or requests.Session()
        eventos, erro, _ = _get(sessao, f"/sports/{sport}/events", {"apiKey": valor})
        if erro:
            return "⚠️ Eventos: " + erro
        agora = datetime.now(timezone.utc)
        candidatos = [e for e in eventos if isinstance(e, dict)
                      and _equipa(e.get("home_team"), casa)
                      and _equipa(e.get("away_team"), fora)
                      and _dt(e.get("commence_time")) is not None
                      and _dt(e.get("commence_time")) > agora
                      and isinstance(e.get("id"), str)
                      and re.fullmatch(r"[A-Za-z0-9]{8,80}", e["id"])]
        if len(candidatos) != 1:
            return "⚪ Jogo futuro nao encontrado de forma unica. Zero consultas pagas."
        evento = candidatos[0]
        dados, erro, quota = _get(
            sessao, f"/sports/{sport}/events/{evento['id']}/odds",
            {"apiKey": valor, "regions": "eu", "markets": "alternate_totals",
             "oddsFormat": "decimal", "dateFormat": "iso"}, aceitar_objeto=True)
        if erro:
            return "⚠️ Odds de linhas alternativas: " + erro
        if not isinstance(dados, dict):
            return "⚠️ Resposta de odds por evento inesperada." + _quota_txt(quota)
        if (dados.get("id") != evento["id"]
                or not _equipa(dados.get("home_team"), casa)
                or not _equipa(dados.get("away_team"), fora)
                or _dt(dados.get("commence_time")) != _dt(evento.get("commence_time"))):
            return "⚠️ Identidade ou horario do jogo divergente. Sem odds." + _quota_txt(quota)
        cotacoes = {}
        rejeitadas = 0
        for book in dados.get("bookmakers") or []:
            if not isinstance(book, dict) or not book.get("key"):
                continue
            casa_id = _seguro(book["key"], 45)
            for market in book.get("markets") or []:
                if not isinstance(market, dict) or market.get("key") != "alternate_totals":
                    continue
                atualizado = _dt(market.get("last_update") or book.get("last_update"))
                if atualizado is None or not (-300 <= (agora-atualizado).total_seconds() <= 21600):
                    rejeitadas += 1
                    continue
                for outcome in market.get("outcomes") or []:
                    if not isinstance(outcome, dict):
                        continue
                    try:
                        ponto = float(outcome.get("point"))
                    except (TypeError, ValueError, OverflowError):
                        continue
                    sentido = str(outcome.get("name") or "").casefold()
                    preco = _numero(outcome.get("price"))
                    if ponto not in (2.5, 3.5) or sentido not in ("over", "under") or preco is None:
                        continue
                    chave = (casa_id, sentido, ponto)
                    # Duplicados na mesma casa/linha sao ambiguos; nao publicar.
                    if chave in cotacoes:
                        cotacoes[chave] = None
                    else:
                        cotacoes[chave] = preco
        linhas = ["🎯 LINHAS EXATAS — MULTICASA SHADOW",
                  f"⚽ {_seguro(casa)} vs {_seguro(fora)}",
                  f"🕘 {_hora(evento.get('commence_time'))} | EU",
                  f"🏦 Casas com cotacoes: {len(set(k[0] for k,v in cotacoes.items() if v is not None))}",
                  f"⏳ Mercados sem atualizacao valida: {rejeitadas}"]
        for ponto in (2.5, 3.5):
            for sentido in ("under", "over"):
                amostra = [(k[0], v) for k,v in cotacoes.items()
                           if k[1] == sentido and k[2] == ponto and v is not None]
                linhas.append(f"• {sentido.title()} {ponto:.1f}: {len(amostra)} casas")
                for nome, preco in sorted(amostra)[:3]:
                    linhas.append(f"  {_seguro(nome, 30)}: {preco:.2f}")
        linhas.append("🔒 Nao e Betano PT; sem picks, apostas, CLV ou alteracoes de producao.")
        return "\n".join(linhas) + _quota_txt(quota)

    # Descoberta explicita de mercados alternativos: 1 chamada /markets por evento.
    # Sem odds, sem picks e sem alteracoes no pipeline de producao.
    if str(argumentos or "").strip().casefold().startswith("mercados "):
        from odds_referencia_shadow import _dt, _equipa
        partes = [p.strip() for p in str(argumentos).strip()[len("mercados "):].split("|")]
        if (len(partes) != 3 or not SPORT.fullmatch(partes[0])
                or not all(2 <= len(p) <= 65 and p.isprintable() for p in partes[1:])
                or _equipa(partes[1], partes[2])):
            return "Formato: /fonte_alt mercados soccer_liga | Equipa Casa | Equipa Fora. Zero chamadas."
        valor = str(chave or os.getenv("THE_ODDS_API_KEY") or "").strip()
        if not valor:
            return "⚪ THE_ODDS_API_KEY nao configurada. Zero chamadas."
        sessao = session or requests.Session()
        sport, casa, fora = partes
        eventos, erro, _ = _get(sessao, f"/sports/{sport}/events", {"apiKey": valor})
        if erro:
            return "⚠️ Eventos: " + erro
        agora = datetime.now(timezone.utc)
        candidatos = [
            e for e in eventos if isinstance(e, dict)
            and _equipa(e.get("home_team"), casa) and _equipa(e.get("away_team"), fora)
            and _dt(e.get("commence_time")) is not None
            and _dt(e.get("commence_time")) > agora
            and isinstance(e.get("id"), str)
            and re.fullmatch(r"[A-Za-z0-9]{8,80}", e["id"])
        ]
        if len(candidatos) != 1:
            return ("⚪ Jogo futuro nao encontrado de forma unica. "
                    "Confirma nomes em /fonte_alt jogos " + sport
                    + ". Zero creditos de mercados consumidos.")
        evento = candidatos[0]
        dados, erro, quota = _get(
            sessao, f"/sports/{sport}/events/{evento['id']}/markets",
            {"apiKey": valor, "regions": "eu"}, aceitar_objeto=True,
        )
        if erro:
            return "⚠️ Mercados do evento: " + erro
        # O endpoint pode devolver objetos por bookmaker ou mercados diretamente.
        # Nunca declarar disponibilidade se o formato nao for reconhecido.
        mercados = set()
        casas = 0
        # O endpoint de mercados pode devolver {"data": [bookmakers]}.
        if isinstance(dados, dict):
            itens = dados.get("data")
            if not isinstance(itens, list):
                itens = dados.get("bookmakers")
            if not isinstance(itens, list):
                return ("⚠️ Estrutura de mercados desconhecida (objeto sem lista "
                        "data/bookmakers)." + _quota_txt(quota))
        else:
            itens = dados
        for item in itens:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("markets"), list):
                casas += 1
                for m in item["markets"]:
                    if isinstance(m, dict) and isinstance(m.get("key"), str):
                        mercados.add(m["key"])
            elif isinstance(item.get("key"), str):
                mercados.add(item["key"])
        alternativos = sorted(k for k in mercados if k == "alternate_totals")
        linhas = [
            "🔎 MERCADOS DISPONIVEIS — SHADOW",
            f"⚽ {_seguro(evento.get('home_team'))} vs {_seguro(evento.get('away_team'))}",
            f"🕘 {_hora(evento.get('commence_time'))} | regiao EU",
            f"🏦 Blocos de casas: {casas} | mercados distintos: {len(mercados)}",
            "🎯 alternate_totals: " + ("identificado" if alternativos else "nao identificado nesta resposta"),
            "ℹ️ Esta consulta verifica chaves de mercado, nao odds nem linhas 3.5.",
            "🔒 Sem picks, CLV, V1.2/V1.3 ou escrita de dados.",
        ]
        return "\n".join(linhas) + _quota_txt(quota)
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
