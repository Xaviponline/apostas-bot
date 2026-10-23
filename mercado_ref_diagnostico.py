"""Diagnostico local OWNER para associacao entre fixture e snapshots congelados.

Apenas memoria: sem HTTP, sem mutacoes, sem guardar nada, sem consultar odds.
A regra de elegibilidade e identica a _resumo_modelo de odds_referencia_shadow.
"""
from collections import Counter
from datetime import datetime
import math
from zoneinfo import ZoneInfo

from odds_referencia_shadow import _equipa, _mercado_modelo, _numero
from odds_alternativa_shadow import _seguro

TZ_PT = ZoneInfo("Europe/Lisbon")
TOLERANCIA_SEG = 15 * 60


def _timestamp(p):
    try:
        ts = float(p.get("timestamp_jogo"))
    except (TypeError, ValueError, OverflowError):
        return None
    return ts if math.isfinite(ts) else None


def _hora_local(ts):
    if ts is None:
        return "hora ausente"
    try:
        return datetime.fromtimestamp(ts, TZ_PT).strftime("%d/%m %H:%M")
    except (ValueError, OverflowError, OSError):
        return "hora invalida"


def _motivo(p, casa, fora, alvo_ts):
    """Motivo exclusivo ou 'elegivel' segundo os filtros do comparador."""
    if p.get("estado") != "pendente":
        return "estado_nao_pendente"
    if not _equipa(p.get("casa"), casa) or not _equipa(p.get("fora"), fora):
        return "equipas_ou_ordem"
    ts = _timestamp(p)
    if ts is None:
        return "sem_hora"
    if abs(ts - alvo_ts) > TOLERANCIA_SEG:
        return "hora_diferente"
    if _mercado_modelo(p) is None:
        return "mercado_nao_coberto"
    prob = _numero(p.get("probabilidade"), minimo=0, maximo=1.000001)
    minima = _numero(p.get("odd_minima"), minimo=1)
    if prob is None or prob > 1 or minima is None:
        return "probabilidade_ou_minima_invalida"
    return "elegivel"


def diagnosticar_snapshot_mercado(argumentos, snapshots):
    """Formato 'YYYY-MM-DD HH:MM | casa | fora', hora local de Portugal."""
    exemplo = (
        "Formato: /mercado_ref_diag 2026-10-24 20:30 | Gil Vicente | FC Porto\n"
        "🔒 Apenas snapshots em memoria, zero chamadas e zero creditos."
    )
    partes = [p.strip() for p in str(argumentos or "").split("|")]
    if len(partes) != 3:
        return exemplo
    hora_txt, casa, fora = partes
    if len(casa) < 2 or len(fora) < 2 or len(casa) > 65 or len(fora) > 65:
        return exemplo
    if not all(c.isprintable() for c in casa + fora) or _equipa(casa, fora):
        return exemplo
    try:
        hora = datetime.strptime(hora_txt, "%Y-%m-%d %H:%M").replace(tzinfo=TZ_PT)
    except ValueError:
        return exemplo
    if hora.year < 2020 or hora.year > 2100:
        return exemplo
    alvo_ts = hora.timestamp()
    dia = hora.strftime("%Y-%m-%d")
    lista = [p for p in snapshots if isinstance(p, dict)] if isinstance(snapshots, list) else []
    do_dia = [p for p in lista if p.get("data_jogo") == dia]
    exatas = [
        p for p in lista if
        _equipa(p.get("casa"), casa) and _equipa(p.get("fora"), fora)
    ]
    invertidas = sum(
        1 for p in do_dia if _equipa(p.get("casa"), fora)
        and _equipa(p.get("fora"), casa)
    )
    contagem = Counter(_motivo(p, casa, fora, alvo_ts) for p in exatas)
    perto = []
    for p in do_dia:
        if p in exatas:
            continue
        if (_equipa(p.get("casa"), casa) or _equipa(p.get("fora"), fora)
                or _equipa(p.get("casa"), fora) or _equipa(p.get("fora"), casa)):
            perto.append(p)
    linhas = [
        "🔎 DIAGNOSTICO LOCAL — MODELO vs MERCADO SHADOW",
        f"⚽ {_seguro(casa)} vs {_seguro(fora)}",
        f"🕘 {hora.strftime('%d/%m/%Y %H:%M')} (Portugal)",
        f"📚 Snapshots existentes: {len(lista)} | na data: {len(do_dia)}",
        f"🔗 Equipas+ordem exatas (qualquer data): {len(exatas)}",
        f"🔄 Ordem invertida na data: {invertidas}",
        f"✅ Compativeis para mostrar junto da referencia: {contagem['elegivel']}",
        "",
    ]
    if exatas:
        nomes = {
            "estado_nao_pendente": "estado diferente de pendente",
            "sem_hora": "hora ausente/invalida",
            "hora_diferente": "hora fora da tolerancia de 15 min",
            "mercado_nao_coberto": "mercado nao suportado no comparador",
            "probabilidade_ou_minima_invalida": "probabilidade/odd minima ausente ou invalida",
        }
        for chave, descricao in nomes.items():
            if contagem[chave]:
                linhas.append(f"• {descricao}: {contagem[chave]}")
        linhas.append("📋 Amostra de registos do mesmo confronto (max. 5):")
        for p in sorted(exatas, key=lambda q: abs((_timestamp(q) or 0) - alvo_ts))[:5]:
            motivo = _motivo(p, casa, fora, alvo_ts)
            linhas.append(
                f"• {_hora_local(_timestamp(p))} | {_seguro(p.get('mercado'), 33)} "
                f"| {_seguro(p.get('estado'), 16)} | {motivo}"
            )
    elif not do_dia:
        linhas.append("⚪ Sem snapshots nessa data. Nao ha selecao do modelo para associar.")
    else:
        linhas.append("⚪ Existem snapshots nessa data, mas nenhum com as duas equipas e ordem exatas.")
        if perto:
            linhas.append("🔍 Coincidencias parciais (NAO associadas):")
            for p in perto[:3]:
                linhas.append(
                    f"• {_hora_local(_timestamp(p))} | "
                    f"{_seguro(p.get('casa'), 27)} vs {_seguro(p.get('fora'), 27)}"
                )
    if contagem["elegivel"] > 0:
        linhas.append("ℹ️ Pelo menos uma previsao devia ser associavel; verificar a versao e o resultado do comparador.")
    else:
        linhas.append("ℹ️ Sem snapshot elegivel: NAO atribuir odd minima, VALUE ou pick nova.")
    linhas.extend([
        "🔒 Zero HTTP / zero creditos The Odds API ou OddsPapi.",
        "🛡️ Apenas leitura. Sem alterar previsoes, V1.2, V1.3, CLV ou historico.",
    ])
    return "\n".join(linhas)
