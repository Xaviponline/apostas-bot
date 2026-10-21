"""Confronto manual entre um jogo visivel na Betano PT e o payload OddsPapi.

OWNER-only no handler, uma execucao por argumentos/processo. Nao cria
snapshots nem muda ranking, VALUE, CLV, V1.2, SEL1, V1.3 ou Platt.
A ausencia de resposta API nao prova ausencia na Betano portuguesa.
"""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from math import isfinite
from zoneinfo import ZoneInfo

from odds_auditoria import AuditoriaOdds

TZ_PT = ZoneInfo("Europe/Lisbon")
FORMATO = (
    "Formato: /odds_confronto AAAA-MM-DD HH:MM | Equipa Casa | Equipa Fora\n"
    "Exemplo: /odds_confronto 2026-10-23 22:00 | "
    "Gimnasia y Esgrima de La Plata | CA Sarmiento"
)


def _curto(txt, maximo=80):
    return "".join(c for c in " ".join(str(txt or "").split())
                   if c.isprintable())[:maximo]


def _alvo(argumento, agora):
    partes = [p.strip() for p in str(argumento or "").split("|")]
    if len(partes) != 3 or any(not p for p in partes) or len(str(argumento)) > 230:
        return None
    try:
        data = datetime.strptime(partes[0], "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    if data.strftime("%Y-%m-%d %H:%M") != partes[0]:
        return None
    if not all(2 <= len(p) <= 72 for p in partes[1:]):
        return None
    if any(any(ord(c) < 32 for c in p) for p in partes):
        return None
    alvo = data.replace(tzinfo=TZ_PT)
    if not agora.timestamp() < alvo.timestamp() <= (agora + timedelta(days=7)).timestamp():
        return None
    return alvo, partes[1], partes[2]


def _reserva(permite):
    return callable(permite) and bool(permite("ODDS_AUTO", 25))


def _cotacao_extra(dados, tipo, escolha):
    """Somente empate (X) e BTTS Nao: nao entram na selecao do modelo."""
    encontrados = []
    for mercado in dados.get("mercados") or []:
        if not isinstance(mercado, dict) or not AuditoriaOdds._mercado_compativel(tipo, mercado):
            continue
        for odd in mercado.get("odds") or []:
            if not isinstance(odd, dict):
                continue
            nome = AuditoriaOdds._normalizar(odd.get("seleção"))
            ref = AuditoriaOdds._normalizar(odd.get("ref"))
            if nome not in escolha and ref not in escolha:
                continue
            valor = AuditoriaOdds._odd_numero(odd.get("odd"))
            if valor is not None and isfinite(valor):
                encontrados.append((valor, AuditoriaOdds._timestamp_odd(mercado, odd)))
    return encontrados[0] if len(encontrados) == 1 else None


def _precos(dados):
    itens = (
        ("1 - Casa", "Vitória Casa", None),
        ("X - Empate", "Vitória Casa", {"x", "draw", "empate"}),
        ("2 - Fora", "Vitória Fora", None),
        ("Mais 2,5", "Over 2.5 Golos", None),
        ("Menos 2,5", "Under 2.5 Golos", None),
        ("Ambas SIM", "Ambas Marcam", None),
        ("Ambas NAO", "Ambas Marcam", {"no", "nao"}),
    )
    linhas = []
    for titulo, mercado, especial in itens:
        cotacao = (
            _cotacao_extra(dados, mercado, especial)
            if especial is not None
            else AuditoriaOdds._extrair_odd_diagnostico(dados, mercado)[0]
        )
        if cotacao is None:
            linhas.append(f"• {titulo}: sem preco identificado no payload")
        else:
            valor, atualizado = cotacao
            linhas.append(
                f"• {titulo}: {valor:.2f}"
                + (f" | atualizacao fonte {_curto(atualizado, 35)}" if atualizado else
                   " | sem hora de atualizacao")
            )
    return linhas


def confrontar_betano(odds, argumento, permissao_quota, agora=None):
    agora = (agora or datetime.now(TZ_PT)).astimezone(TZ_PT)
    alvo = _alvo(argumento, agora)
    if alvo is None:
        return FORMATO + "\n⛔ Apenas jogos futuros nos proximos 7 dias; zero chamadas API."
    dia, casa, fora = alvo
    if getattr(odds, "provider", None) != "oddspapi" or not getattr(odds, "configurada", False):
        return "⚪ OddsPapi indisponivel ou nao configurada. Zero chamadas."
    if not _reserva(permissao_quota):
        return "⛔ Reserva de quota/CLV: consulta suspensa. Zero chamadas."

    meia_noite = dia.replace(hour=0, minute=0, second=0, microsecond=0)
    fim = meia_noite + timedelta(days=1)
    params = {
        "sportId": 10,
        "from": meia_noite.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "to": fim.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "language": "en",
        # Sem statusId: nao excluir jogos por estado de listagem.
    }
    contexto = getattr(odds, "contexto_operacao", None)
    with (contexto("MANUAL") if callable(contexto) else nullcontext()):
        fixtures = odds._get_papi("/fixtures", params)
    if not isinstance(fixtures, list) or len(fixtures) > 20000:
        return "⚠️ Formato ou dimensao inesperada em /fixtures. Sem consulta /odds."
    candidatos = []
    pistas = []
    for item in fixtures:
        if not isinstance(item, dict):
            continue
        tc = str(item.get("participant1Name") or "")
        tf = str(item.get("participant2Name") or "")
        if (AuditoriaOdds._nome_equipa_compativel(casa, tc)
                or AuditoriaOdds._nome_equipa_compativel(fora, tf)):
            pistas.append(item)
        if not (
            AuditoriaOdds._nome_equipa_compativel(casa, tc)
            and AuditoriaOdds._nome_equipa_compativel(fora, tf)
        ):
            continue
        ts = AuditoriaOdds._timestamp_iso(item.get("startTime"))
        if ts is not None and abs(ts - dia.timestamp()) <= 90 * 60:
            candidatos.append(item)

    titulo = (
        f"🔎 CONFRONTO BETANO PT x ODDSPAPI — SHADOW | {dia:%d/%m/%Y %H:%M}\n"
        f"⚽ {_curto(casa)} vs {_curto(fora)}\n"
        f"📚 Fixtures recebidos: {len(fixtures)} | "
        f"ambas equipas + hora: {len(candidatos)}\n"
    )
    if len(candidatos) != 1:
        linhas = [titulo, "⚠️ Fixture nao identificado de forma unica; /odds NAO consultado."]
        for item in pistas[:4]:
            linhas.append(
                f"• Pista nao validada: {_curto(item.get('participant1Name'), 48)} "
                f"vs {_curto(item.get('participant2Name'), 48)} "
                f"| {_curto(item.get('startTime'), 35)}"
            )
        linhas.extend([
            "⚠️ Ausente na listagem nao comprova que falte na Betano PT.",
            "🔒 So leitura. Sem associacoes, odds guardadas ou mudancas de modelo.",
        ])
        return "\n".join(linhas)

    item = candidatos[0]
    fixture_id = item.get("fixtureId")
    if not isinstance(fixture_id, (str, int)) or not str(fixture_id).strip():
        return titulo + "⚠️ Fixture sem ID seguro; /odds NAO consultado."
    if not _reserva(permissao_quota):
        return titulo + "⛔ Reserva de quota/CLV: /odds suspenso."
    with (contexto("MANUAL") if callable(contexto) else nullcontext()):
        dados = odds.odds_evento(str(fixture_id))
    linhas = [
        titulo,
        f"🆔 Fixture: {_curto(fixture_id, 55)}",
        f"🏆 Competicao fonte: {_curto(item.get('tournamentName'), 90)}",
        f"🕒 Inicio fonte: {_curto(item.get('startTime'), 40)}",
        f"🏦 Bookmaker pedido: {_curto(getattr(odds, 'papi_bookmaker', 'betano.pt'), 30)}",
    ]
    if not isinstance(dados, dict):
        diagnostico = odds.diagnostico_evento(str(fixture_id))
        linhas.extend([
            f"⚠️ /odds sem resposta utilizavel: {_curto(diagnostico, 55)}",
            "⚠️ Isto nao prova ausencia do mercado na Betano PT.",
            "🔒 Sem mudar picks, VALUE, CLV ou registos.",
        ])
        return "\n".join(linhas)
    if not AuditoriaOdds._payload_evento_compativel(
        dados, {"casa": item.get("participant1Name"), "fora": item.get("participant2Name")},
        fixture_id,
    ):
        return titulo + "⚠️ Payload de /odds incompativel com fixture; precos ocultados."
    presente = dados.get("bookmaker_disponivel") is True
    linhas.extend([
        f"🏦 Betano no payload OddsPapi: {'SIM' if presente else 'NAO'}",
        f"📊 Mercados com cotacao: {len(dados.get('mercados') or [])}",
        f"🕘 Atualizacao geral: {_curto(dados.get('updatedAt') or 'nao indicada', 42)}",
    ])
    if presente:
        linhas.extend(["", "🎯 PRECOS IDENTIFICADOS PELA EXTRACAO ATUAL"])
        linhas.extend(_precos(dados))
        desconhecidos = sum(
            1 for m in (dados.get("mercados") or [])
            if isinstance(m, dict) and str(m.get("name") or "").startswith("Market ")
        )
        if desconhecidos:
            linhas.append(
                f"⚠️ {desconhecidos} mercado(s) sem nome de catalogo: "
                "precos ausentes podem ser falha de traducao."
            )
    linhas.extend([
        "",
        "⚠️ Comparar com screenshot da Betano PT do MESMO INSTANTE: "
        "precos e mercados podem mudar entretanto.",
        "⚠️ Ausencia no payload nao prova mercado inexistente na Betano PT.",
        "🔒 Consulta OWNER manual; sem snapshots, VALUE, picks, V1.2/V1.3/Platt ou CLV alterados.",
    ])
    return "\n".join(linhas)
