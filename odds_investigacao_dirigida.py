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
    total_nome_compativel = 0
    total_exato = 0
    total_exato_dia = 0
    origem_id = "lista geral consultada nesta ronda" if pesquisa_geral else "cache da lista geral"
    for e in cache:
        if not isinstance(e, dict):
            continue
        if AuditoriaOdds._nome_equipa_compativel(p.get("casa"), e.get("casa")):
            total_nome_compativel += 1
        if AuditoriaOdds._canon_equipa(e.get("casa")) != nome_casa:
            continue
        total_exato += 1
        d = _instante(e.get("data"))
        if d is None or d.astimezone(TZ).date().isoformat() != hoje:
            continue
        total_exato_dia += 1
        identificador = _int_id(e.get("participant1_id"))
        if identificador is not None:
            ids.add(identificador)

    # Não usar nomes parcialmente compatíveis para escolher participantId:
    # podem designar equipas B, femininas ou sub-20. Uma ambiguidade de IDs
    # existentes também nunca é resolvida por uma consulta adicional.
    if len(ids) > 1:
        return (
            f"🔎 INVESTIGAÇÃO DIRIGIDA — #{ranking}\n"
            f"• Nomes compatíveis na listagem: {total_nome_compativel}; "
            f"nomes exatos: {total_exato}; exatos na data: {total_exato_dia}.\n"
            "⚪ mais do que um ID de equipa; pesquisa bloqueada por ambiguidade.\n"
            "🔒 Zero odds e snapshots alterados."
        )
    if not ids:
        # GET /participants é o catálogo oficial de IDs por modalidade.
        # Não depende de a equipa surgir nos fixtures filtrados por hora.
        if not permissao_quota("ODDS_AUTO", 25):
            return "⛔ Catálogo de participantes suspenso pela reserva CLV. Zero consultas adicionais."
        contexto = getattr(odds, "contexto_operacao", None)
        with (contexto("MANUAL") if callable(contexto) else nullcontext()):
            participantes = odds._get_papi(
                "/participants", {"sportId": 10, "language": "en"}
            )
        if not isinstance(participantes, dict) or len(participantes) > 300000:
            return "⚠️ Catálogo de participantes inválido ou excessivo. Sem pesquisa dirigida."
        exatos = {
            n for bruto, nome in participantes.items()
            if AuditoriaOdds._canon_equipa(nome) == nome_casa
            for n in [_int_id(bruto)] if n is not None
        }
        if len(exatos) != 1:
            semelhantes = sum(
                1 for nome in participantes.values()
                if AuditoriaOdds._nome_equipa_compativel(p.get("casa"), nome)
            )
            return (
                f"🔎 INVESTIGAÇÃO DIRIGIDA — #{ranking}\n"
                f"• Listagem geral: nomes compatíveis {total_nome_compativel}; "
                f"exatos {total_exato}; exatos na data {total_exato_dia}.\n"
                f"• Catálogo de participantes: {len(exatos)} ID(s) exato(s); "
                f"{min(semelhantes, 999)} nome(s) parcialmente compatível(is).\n"
                "⚪ Sem ID único e exato. Nenhum evento ou odd associado."
            )
        ids = exatos
        origem_id = "catálogo de participantes (nome exato)"
    participante = next(iter(ids))
    # Se o catálogo exigiu um pedido, confirmar novamente a reserva CLV
    # antes do segundo pedido de quota (/fixtures).
    if origem_id == "catálogo de participantes (nome exato)" and not permissao_quota("ODDS_AUTO", 25):
        return "⛔ Pesquisa de fixtures suspensa após catálogo pela reserva CLV."

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
        f"• Origem do ID: {origem_id}.",
        f"• Nomes na listagem geral: compatíveis {total_nome_compativel}, "
        f"exatos {total_exato}, exatos na data {total_exato_dia}.",
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
