"""Auditoria manual OWNER: inspeciona apenas metadados do payload /odds bruto.

Nao extrai nem apresenta precos; nao cria snapshots, nao escreve ficheiros,
nao modifica os modelos, o catalogo, odds, VALUE ou CLV.
Uma unica operacao /odds por comando (o cliente pode repetir HTTP 429).
"""
from contextlib import nullcontext
import re

from odds_auditoria import AuditoriaOdds


FORMATO = (
    "Formato: /odds_payload_audit ID_DO_FIXTURE\n"
    "Exemplo: /odds_payload_audit id1000015573265458\n"
    "🔒 So OWNER; zero consultas com formato invalido."
)
# Apenas identificadores de fixture OddsPapi, nunca URL nem parametros livres.
PADRAO_ID = re.compile(r"id[0-9]{8,24}\Z", re.ASCII)
ALVOS = (
    ("Resultado Final (1X2)", "Vitória Casa"),
    ("Ambas Marcam", "Ambas Marcam"),
    ("Mais/Menos 2.5", "Over 2.5 Golos"),
)


def _curto(valor, limite=72):
    return "".join(c for c in " ".join(str(valor or "").split())
                   if c.isprintable())[:limite]


def _contar(mercado):
    """Replica apenas os filtros estruturais da normalizacao, sem copiar odds."""
    if not isinstance(mercado, dict):
        return 0, 0, 0, 0
    outcomes = mercado.get("outcomes")
    if not isinstance(outcomes, dict):
        return 0, 0, 0, 0
    total_outcomes = len(outcomes)
    jogadores = inativos = preco_disponivel = 0
    for outcome in outcomes.values():
        if not isinstance(outcome, dict):
            continue
        players = outcome.get("players")
        if not isinstance(players, dict):
            continue
        for player in players.values():
            if not isinstance(player, dict):
                continue
            jogadores += 1
            if not player.get("active", True):
                inativos += 1
            elif player.get("price") is not None:
                preco_disponivel += 1
    return total_outcomes, jogadores, inativos, preco_disponivel


def _alvo_compativel(meta, mercado_modelo):
    if not isinstance(meta, dict) or not meta.get("name"):
        return False
    if not AuditoriaOdds._mercado_compativel(mercado_modelo, meta):
        return False
    if mercado_modelo.startswith("Over "):
        linha = AuditoriaOdds._linha_numero(meta.get("handicap"))
        # Sem linha inequivoca, nao declarar que o mercado e Over/Under 2.5.
        return linha is not None and abs(linha - 2.5) < 1e-9
    return True


def auditar_payload_bruto(odds, fixture_id, permite):
    fixture_id = str(fixture_id or "").strip()
    if not PADRAO_ID.fullmatch(fixture_id):
        return FORMATO
    if getattr(odds, "provider", None) != "oddspapi" or not getattr(odds, "configurada", False):
        return "⚪ OddsPapi nao configurada. Zero chamadas."
    if not callable(permite) or not permite("ODDS_AUTO", 25):
        return "⛔ Reserva de quota/CLV: consulta suspensa. Zero chamadas."

    contexto = getattr(odds, "contexto_operacao", None)
    with (contexto("MANUAL") if callable(contexto) else nullcontext()):
        bruto = odds._get_papi("/odds", {
            "fixtureId": fixture_id,
            "bookmakers": getattr(odds, "papi_bookmaker", "betano.pt"),
            "oddsFormat": "decimal",
            "language": "en",
            "verbosity": 3,
        })
    if not isinstance(bruto, dict):
        return "⚠️ Resposta bruta invalida. Sem interpretacao nem alteracoes."
    if str(bruto.get("fixtureId") or "") != fixture_id:
        return "⚠️ ID do payload nao corresponde ao fixture pedido. Dados ocultados."

    bookmaker = getattr(odds, "papi_bookmaker", "betano.pt")
    por_book = bruto.get("bookmakerOdds")
    book = por_book.get(bookmaker) if isinstance(por_book, dict) else None
    if not isinstance(book, dict):
        return (
            f"🔬 PAYLOAD BRUTO — {fixture_id}\n"
            "🏦 Betano sem bloco reconhecido nesta resposta OddsPapi.\n"
            "⚠️ Nao prova indisponibilidade na Betano.pt.\n"
            "🔒 Sem alterar odds, snapshots ou modelo."
        )
    mercados = book.get("markets")
    if not isinstance(mercados, dict) or len(mercados) > 50000:
        return "⚠️ Bloco de mercados inesperado. Sem interpretacao nem alteracoes."

    catalogo = getattr(odds, "_catalogo_mercados", None)
    catalogo = catalogo if isinstance(catalogo, dict) and catalogo else None
    total = len(mercados)
    ativos = inativos = malformados = visiveis = sem_preco = 0
    outcomes = jogadores = jogadores_inativos = precos_visiveis = 0
    alvos = {nome: [0, 0] for nome, _ in ALVOS}
    exemplos = []
    for mid, item in mercados.items():
        if not isinstance(item, dict):
            malformados += 1
            continue
        activo = bool(item.get("marketActive", True))
        o, j, ji, pv = _contar(item)
        outcomes += o
        jogadores += j
        jogadores_inativos += ji
        meta = catalogo.get(str(mid)) if catalogo else None
        if catalogo:
            for nome, mercado_modelo in ALVOS:
                if _alvo_compativel(meta, mercado_modelo):
                    alvos[nome][0] += 1
                    if activo and pv:
                        alvos[nome][1] += 1
        if not activo:
            inativos += 1
        else:
            ativos += 1
            if pv:
                visiveis += 1
                precos_visiveis += pv
            else:
                sem_preco += 1
        # Mostrar nomes/IDs do catalogo apenas; nunca JSON, selecoes ou precos.
        if isinstance(meta, dict) and len(exemplos) < 8:
            nome_meta = str(meta.get("name") or "")
            if any(x in nome_meta.casefold() for x in ("goal", "result", "score", "match", "both teams", "over under full time")):
                exemplos.append((
                    _curto(mid, 24), _curto(nome_meta, 48),
                    _curto(meta.get("handicap"), 8),
                    "ativo" if activo else "inativo",
                    "com preco" if activo and pv else "sem preco utilizavel",
                ))
    linhas = [
        f"🔬 AUDITORIA PAYLOAD BRUTO — {fixture_id}",
        f"⚽ {_curto(bruto.get('participant1Name'))} vs {_curto(bruto.get('participant2Name'))}",
        f"🏆 {_curto(bruto.get('tournamentName'))}",
        f"🕘 Atualizacao geral da fonte: {_curto(bruto.get('updatedAt') or 'nao indicada', 45)}",
        f"🏦 Bloco bookmaker: {bookmaker}",
        f"📦 Mercados brutos: {total} | ativos: {ativos} | inativos: {inativos} | invalidos: {malformados}",
        f"🔎 Mercados ativos com preco: {visiveis} | sem preco: {sem_preco}",
        f"🔢 Outcomes brutos: {outcomes} | players: {jogadores} | inativos: {jogadores_inativos}",
        f"📊 Selecoes ativas com preco: {precos_visiveis} (contagem; valores ocultados)",
        f"🏷️ Catalogo em memoria: {len(catalogo) if catalogo else 'indisponivel; sem chamada /markets'}",
    ]
    if catalogo:
        linhas.extend(["", "🎯 MERCADOS PROCURADOS (bruto → ativos com preco):"])
        for nome, _ in ALVOS:
            a, b = alvos[nome]
            linhas.append(f"• {nome}: {a} → {b}")
        linhas.append("ℹ️ A correspondencia depende do nome, periodo e linha do catalogo.")
    else:
        linhas.append("⚠️ Sem catalogo nao e seguro identificar os mercados por nome.")

    if exemplos:
        linhas.append("")
        linhas.append("🔎 AMOSTRA DE MERCADOS DE GOLOS/RESULTADO:")
        for mid, nome, linha, estado, precos in exemplos:
            linhas.append(f"• {mid} — {nome} | linha {linha} | {estado} | {precos}")
    linhas.extend([
        "",
        "⚠️ O payload pode estar desatualizado; ausencia nao prova falta de mercado na Betano.",
        "🔒 So leitura; nao publica cotacoes nem guarda payload, odds, picks ou snapshots.",
    ])
    return "\n".join(linhas)
