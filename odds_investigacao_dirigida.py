"""Consulta dirigida SHADOW por participantId; nunca associa odds nem grava snapshots.

Uma pesquisa por equipa deve ser executada APENAS por OWNER através de comando
explícito. No máximo uma descoberta geral quando não há cache, mais uma
consulta dirigida /fixtures, sujeitas aos limites/retries do cliente OddsPapi.
"""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from math import isfinite
from zoneinfo import ZoneInfo

from odds_auditoria import AuditoriaOdds


TZ = ZoneInfo("Europe/Lisbon")


def _int_id(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        num = int(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return num if 0 < num < 2_147_483_647 else None


def _segundos(valor):
    try:
        ts = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return ts if isfinite(ts) else None


def _instante(valor):
    try:
        d = datetime.fromisoformat(str(valor or "").strip().replace("Z", "+00:00"))
        if d.tzinfo is None:
            return None
        return d
    except (TypeError, ValueError, OverflowError):
        return None


def _limpo(valor, limite=65):
    return " ".join(str(valor or "?").split())[:limite]


def investigar_fixture_por_equipa(previsoes, odds, argumento, permissao_quota, agora=None):
    """Retorna diagnóstico, sem escrever, sem /odds e sem atualizar qualquer modelo."""
    agora = agora or datetime.now(TZ)
    agora = agora.astimezone(TZ)
    txt = str(argumento or "").strip()
    if not txt.isascii() or not txt.isdecimal() or not (1 <= len(txt) <= 3):
        return "Formato: /odds_investigar 3 (ranking do dia; apenas OWNER)."
    ranking = int(txt)
    hoje = agora.date().isoformat()
    jogos = [
        p for p in previsoes or []
        if isinstance(p, dict) and p.get("data_jogo") == hoje
        and p.get("modelo_versao") == "V1.2"
        and p.get("ranking_modelo") == ranking
    ]
    if len(jogos) != 1:
        return "⚪ Ranking de hoje inexistente ou repetido. Usa /odds_falhas."
    p = jogos[0]
    alvo = _segundos(p.get("timestamp_jogo"))
    if p.get("estado") != "pendente" or alvo is None or alvo <= agora.timestamp():
        return "⛔ Apenas jogos V1.2 ainda por começar. Sem consulta OddsPapi."
    if getattr(odds, "provider", None) != "oddspapi" or not getattr(odds, "configurada", False):
        return "⚪ Fonte OddsPapi indisponível; não houve consulta."
    if not callable(permissao_quota) or not permissao_quota("ODDS_AUTO", 25):
        return "⛔ Pesquisa suspensa pela reserva CLV ou orçamento diário. Zero fixtures consultados."

    # A cache existente pode estar expirada para odds, mas o participantId é
    # apenas uma pista estática: reutilizá-lo poupa um pedido /fixtures.
    cache = getattr(odds, "_eventos_cache", None)
    cache = cache if isinstance(cache, list) and cache else None
    pesquisa_geral = cache is None
    if cache is None:
        cache = odds.eventos_hoje()  # no máximo uma descoberta global normal
    if not isinstance(cache, list):
        return "⚪ Listagem principal indisponível. Nenhuma pesquisa dirigida efetuada."

    nome_casa = AuditoriaOdds._canon_equipa(p.get("casa"))
    ids = set()
    total_equipa = 0
    for e in cache:
        if not isinstance(e, dict):
            continue
        if AuditoriaOdds._canon_equipa(e.get("casa")) != nome_casa:
            continue
        d = _instante(e.get("data"))
        if d is None or d.astimezone(TZ).date().isoformat() != hoje:
            continue
        total_equipa += 1
        identificador = _int_id(e.get("participant1_id"))
        if identificador is not None:
            ids.add(identificador)
    if len(ids) != 1:
        motivo = (
            "nenhum ID de equipa confirmado" if not ids else
            "mais do que um ID de equipa possível"
        )
        return (
            f"🔎 INVESTIGAÇÃO DIRIGIDA — #{ranking}\n"
            f"• Ponte Preta/mandante visto em {total_equipa} evento(s) da listagem.\n"
            f"⚪ {motivo}; sem consulta dirigida para evitar associação arriscada.\n"
            f"🔒 Zero odds e snapshots alterados."
        )
    participante = next(iter(ids))
    inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    fim = inicio + timedelta(days=1)
    parametros = {
        "sportId": 10,
        "participantId": participante,
        "from": inicio.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "to": fim.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "language": "en",
    }
    contexto = getattr(odds, "contexto_operacao", None)
    with (contexto("MANUAL") if callable(contexto) else nullcontext()):
        dados = odds._get_papi("/fixtures", parametros)  # só fixtures, nunca /odds
    if not isinstance(dados, list):
        return "⚠️ Resposta de fixtures inválida; nenhuma odd ou snapshot alterado."
    validos = []
    for e in dados:
        if not isinstance(e, dict):
            continue
        id_casa, id_fora = _int_id(e.get("participant1Id")), _int_id(e.get("participant2Id"))
        if participante not in (id_casa, id_fora):
            continue
        dt = _instante(e.get("startTime"))
        if dt is None or dt.astimezone(TZ).date().isoformat() != hoje:
            continue
        ts = dt.timestamp()
        validos.append((abs(ts - alvo), e, dt))
    validos.sort(key=lambda triplo: triplo[0])
    linhas = [
        f"🔎 PESQUISA DIRIGIDA ODDS — SHADOW | #{ranking}",
        f"⚽ {_limpo(p.get('casa'))} vs {_limpo(p.get('fora'))}",
        f"• Identificador verificado da equipa da casa: {participante}",
        f"• Origem do ID: {'lista geral consultada nesta ronda' if pesquisa_geral else 'cache da lista geral'}",
        f"• Eventos devolvidos pela consulta dirigida: {len(dados)}",
        f"• Eventos da equipa na data do jogo: {len(validos)}",
        "📍 Possíveis fixtures (sem associação):",
    ]
    if not validos:
        linhas.append("⚪ Nenhum evento encontrado para a equipa nesta data.")
    for distancia, e, data in validos[:6]:
        h = data.astimezone(TZ).strftime("%H:%M")
        diferenca = round(distancia / 60)
        tag = "horário próximo" if distancia <= 90 * 60 else "horário divergente"
        linhas.append(
            f"• {h} · {_limpo(e.get('participant1Name'))} vs "
            f"{_limpo(e.get('participant2Name'))}"
        )
        linhas.append(
            f"  {_limpo(e.get('tournamentName'), 55)} | {tag} ({diferenca} min)"
        )
    if len(validos) > 6:
        linhas.append(f"… mais {len(validos) - 6} eventos não apresentados.")
    linhas.extend([
        "⚠️ Listas incompletas ou resultados vazios não provam ausência na Betano.",
        "⚠️ hasOdds, se presente, não confirma preço Betano para este mercado.",
        "🔒 Apenas /fixtures. Sem /odds, sem VALUE, sem escrita de snapshots, sem seleção automática.",
    ])
    return "\n".join(linhas)
