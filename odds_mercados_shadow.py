"""Diagnóstico OWNER de um mercado OddsPapi; só leitura e consulta explícita.

Não regista preços, não cria snapshots, não altera VALUE nem associa fixture
sem validação dos dois nomes e da hora. Máximo: descoberta, /odds e
sondagem de /markets se o catálogo estiver vazio (sujeito a quota).
"""
from contextlib import nullcontext
from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo

from odds_auditoria import AuditoriaOdds


TZ_PT = ZoneInfo("Europe/Lisbon")


def _curto(valor, limite=80):
    txt = " ".join(str(valor or "?").split())
    return "".join(x for x in txt if x.isprintable())[:limite]


def _reserva(permissao):
    return callable(permissao) and bool(permissao("ODDS_AUTO", 25))


def _hora_fonte(valor):
    ts = AuditoriaOdds._timestamp_iso(valor)
    if ts is None:
        return "indisponível"
    return datetime.fromtimestamp(ts, TZ_PT).strftime("%H:%M")


def diagnosticar_mercado(previsoes, odds, argumento, permissao_quota, agora=None):
    """Consulta UM fixture de ranking atual; sem qualquer mutação persistente."""
    agora = (agora or datetime.now(TZ_PT)).astimezone(TZ_PT)
    argumento = str(argumento or "").strip()
    if not argumento.isascii() or not argumento.isdecimal() or len(argumento) > 2:
        return "Formato: /odds_mercados 1 (ranking de 1 a 20, apenas OWNER)."
    rank = int(argumento)
    if not 1 <= rank <= 20:
        return "Formato: /odds_mercados 1 (ranking de 1 a 20, apenas OWNER)."
    hoje = agora.date().isoformat()
    candidatas = [
        p for p in previsoes or []
        if isinstance(p, dict) and p.get("data_jogo") == hoje
        and p.get("modelo_versao") == "V1.2"
        and p.get("ranking_modelo") == rank
    ]
    if len(candidatas) != 1:
        return "⚪ Ranking inexistente ou repetido hoje. Zero consultas OddsPapi."

    p = candidatas[0]
    try:
        kickoff = float(p.get("timestamp_jogo"))
    except (TypeError, ValueError, OverflowError):
        kickoff = float("nan")
    if p.get("estado") != "pendente" or not isfinite(kickoff) or kickoff <= agora.timestamp():
        return "⛔ Só jogos pendentes ainda por começar. Zero consultas OddsPapi."
    if getattr(odds, "provider", None) != "oddspapi" or not getattr(odds, "configurada", False):
        return "⚪ Fonte OddsPapi não configurada. Zero consultas."
    if not _reserva(permissao_quota):
        return "⛔ Consulta suspensa pelo orçamento diário/reserva CLV. Zero pedidos."

    # Preferir cache da listagem normal. Sem cache, só uma descoberta habitual.
    cache = getattr(odds, "_eventos_cache", None)
    if not isinstance(cache, list) or not cache:
        eventos = odds.eventos_hoje() or []
        origem_eventos = "listagem consultada"
    else:
        eventos = cache
        origem_eventos = "cache da listagem"
    candidatos = AuditoriaOdds._candidatos_evento(
        eventos, p.get("casa"), p.get("fora")
    )
    if len(candidatos) != 1:
        candidatos = AuditoriaOdds._desempatar_evento_por_hora(candidatos, kickoff)
    if len(candidatos) != 1:
        return (
            f"🔬 MERCADOS SHADOW — #{rank} | {hoje}\n"
            f"⚽ {_curto(p.get('casa'))} vs {_curto(p.get('fora'))}\n"
            f"⚪ Fixtures compatíveis: {len(candidatos)}; associação inconclusiva.\n"
            "🔒 Nenhuma consulta /odds nem modificação às previsões."
        )
    evento = candidatos[0]
    ts_fonte = AuditoriaOdds._timestamp_iso(evento.get("data"))
    if ts_fonte is None or abs(ts_fonte - kickoff) > AuditoriaOdds.TOLERANCIA_HORA_EVENTO_SEG:
        return "⚠️ Hora do fixture não validada; consulta /odds bloqueada."
    ident = evento.get("id")
    if ident in (None, ""):
        return "⚠️ Fixture sem ID seguro; consulta /odds bloqueada."
    if not _reserva(permissao_quota):
        return "⛔ Consulta /odds bloqueada pelo orçamento diário/reserva CLV."

    contexto = getattr(odds, "contexto_operacao", None)
    # A consulta normal pode obter /markets uma única vez se ainda não estiver
    # em cache. Não executar análise, enriquecer picks ou persistir odds.
    with (contexto("MANUAL") if callable(contexto) else nullcontext()):
        dados = odds.odds_evento(ident)
    if not isinstance(dados, dict):
        return (
            f"🔬 MERCADOS SHADOW — #{rank}\n"
            f"⚠️ Consulta do fixture indisponível: "
            f"{_curto(odds.diagnostico_evento(ident), 48)}.\n"
            "🔒 Sem alterações a snapshots, VALUE, CLV ou modelo."
        )

    catalogo = getattr(odds, "_catalogo_mercados", None)
    n_catalogo = len(catalogo) if isinstance(catalogo, dict) else None
    mercados = dados.get("mercados")
    mercados = mercados if isinstance(mercados, list) else []
    nome_modelo = str(p.get("mercado") or "")
    compativeis = [
        m for m in mercados if isinstance(m, dict)
        and AuditoriaOdds._mercado_compativel(nome_modelo, m)
    ]
    extraida, motivo = AuditoriaOdds._extrair_odd_diagnostico(dados, nome_modelo)
    desconhecidos = [
        m for m in mercados if isinstance(m, dict)
        and str(m.get("name") or "").startswith("Market ")
    ]
    linhas = [
        f"🔬 MERCADOS ODDS PAPI — SHADOW | {hoje} | #{rank}",
        f"⚽ {_curto(p.get('casa'))} vs {_curto(p.get('fora'))}",
        f"🎯 {_curto(nome_modelo)}",
        f"📍 Fixture fonte: {_curto(ident, 45)} | {_hora_fonte(evento.get('data'))}",
        f"📚 Descoberta: {origem_eventos}",
        f"🏷️ Catálogo /markets em memória: "
        + (str(n_catalogo) if n_catalogo is not None else "indisponível"),
        f"🏦 Betano no payload: "
        + ("sim" if dados.get("bookmaker_disponivel") is True else "não"),
        f"📊 Mercados com preços no payload: {len(mercados)}",
        f"⚪ Mercados com nome genérico 'Market ID': {len(desconhecidos)}",
        f"🔍 Mercados compatíveis com a seleção: {len(compativeis)}",
        f"🔎 Extração: "
        + ("preço identificado no payload (NÃO confirmado para entrada V1.3)"
           if extraida is not None else _curto(motivo, 55)),
    ]
    # Não incluir preços, chaves de API, cookies nem respostas integrais.
    mostrados = sorted(
        (m for m in mercados if isinstance(m, dict)),
        key=lambda m: (0 if AuditoriaOdds._mercado_compativel(nome_modelo, m) else 1,
                       str(m.get("id") or "")),
    )[:10]
    if mostrados:
        linhas.extend(["", "📋 Amostra de mercados recebidos (IDs, nomes, linha, período):"])
        for m in mostrados:
            linhas.append(
                f"• {_curto(m.get('id'), 18)} — {_curto(m.get('name'), 44)}"
                f" | linha {_curto(m.get('handicap'), 12)}"
                f" | {_curto(m.get('period'), 18)}"
                f" | outcomes {len(m.get('odds') or [])}"
            )
    # Se catálogo em memória estiver vazio, fazer no máximo UMA consulta
    # independente ao /markets e apresentar a forma/contagem, sem substituir a
    # cache de produção ou reprocessar preços. Se falhar, fica inconclusivo.
    if n_catalogo == 0:
        if _reserva(permissao_quota):
            try:
                with (contexto("MANUAL") if callable(contexto) else nullcontext()):
                    cru = odds._get_papi("/markets", {"language": "en"})
                if isinstance(cru, list):
                    ids = {
                        str(m.get("marketId")) for m in cru
                        if isinstance(m, dict) and m.get("marketId") is not None
                    }
                    comuns = sum(
                        1 for m in mercados
                        if isinstance(m, dict) and str(m.get("id")) in ids
                    )
                    linhas.append(
                        f"🧪 Sondagem /markets independente: {len(cru)} entradas; "
                        f"{comuns} IDs presentes no payload."
                    )
                else:
                    linhas.append("🧪 Sondagem /markets: formato inesperado (sem usar dados).")
            except (OSError, RuntimeError, ValueError, TypeError):
                linhas.append("🧪 Sondagem /markets indisponível; sem conclusão.")
        else:
            linhas.append("🧪 Sondagem /markets não executada: reserva CLV/orçamento.")
    if n_catalogo == 0 and desconhecidos:
        linhas.append("⚠️ HIPÓTESE FORTE: mercado com ID mas sem tradução do catálogo.")
    elif not compativeis:
        linhas.append("⚠️ Mercado pretendido não identificado na resposta; causa por confirmar.")
    else:
        linhas.append("ℹ️ Encontrado nome de mercado; verificar linha/outcome e período.")
    linhas.extend([
        "🔒 Apenas diagnóstico explícito. Não guarda odds nem altera V1.2, SEL1, V1.3, Platt ou CLV.",
        "ℹ️ Esta consulta PODE gastar quota. Repetições devem usar cache do comando.",
    ])
    return "\n".join(linhas)
