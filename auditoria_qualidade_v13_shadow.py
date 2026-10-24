"""Auditoria V1.3 de integridade de fontes; só leitura, zero HTTP.

A coorte oficial é consultada como existe. Nenhuma entrada é criada,
removida, ordenada de novo nem reclassificada. Anomalia != aposta errada.
"""
from collections import Counter
from datetime import datetime, timezone
from math import isfinite
from zoneinfo import ZoneInfo

from fixture_guard_shadow import juventude_confirmada_hoje
from odds_identidade_guard import classificar_frescura

PT = ZoneInfo("Europe/Lisbon")


def _ts(valor):
    if not valor or not isinstance(valor, str):
        return None
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def _num(valor):
    try:
        n = float(valor)
        return n if isfinite(n) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _avaliar(p):
    motivos = []
    if juventude_confirmada_hoje(p):
        motivos.append("fixture_u19_confirmado")
    if not str(p.get("odds_event_id") or "").strip():
        motivos.append("id_fixture_odds_ausente")
    instante_entrada = _ts(p.get("odds_capturada_em") or p.get("valor_confirmado_em"))
    if instante_entrada is None:
        motivos.append("hora_captura_entrada_ausente")
    else:
        frescura = classificar_frescura(
            p.get("odds_atualizada_em"), instante_entrada
        )
        if frescura:
            motivos.append(frescura)
    if p.get("odd_fecho") not in (None, ""):
        ts_jogo = _num(p.get("timestamp_jogo"))
        momento_fecho = _ts(p.get("odd_fecho_capturada_em"))
        if ts_jogo is None or momento_fecho is None:
            motivos.append("hora_fecho_nao_comprovada")
        elif not 0 < ts_jogo - momento_fecho.timestamp() <= 30 * 60:
            motivos.append("fecho_fora_janela_t30")
    return motivos


def relatorio_qualidade_v13(registo):
    """Lê a coorte pré-registada, sem qualquer IO além do estado já carregado."""
    m = registo.metricas_v13_comercial()
    previews = registo.dados.get("previsoes", [])
    coorte = m.get("coorte", [])
    motivos = Counter()
    problematicas = []
    analisadas = 0
    for item in coorte:
        try:
            indice = int(item["snapshot"])
            if indice < 1:
                continue
            p = previews[indice - 1]
        except (KeyError, ValueError, IndexError, TypeError):
            motivos["referencia_snapshot_invalida"] += 1
            continue
        if not isinstance(p, dict):
            motivos["referencia_snapshot_invalida"] += 1
            continue
        analisadas += 1
        atual = _avaliar(p)
        if atual:
            motivos.update(atual)
            problematicas.append((
                indice, str(p.get("casa") or "?"), str(p.get("fora") or "?"), atual
            ))
    alvo = int(m.get("alvo") or 50)
    linhas = [
        "🛡️ QUALIDADE DA COORTE V1.3 — SHADOW",
        f"📊 Entradas auditadas: {analisadas}/{alvo} | observacoes: {sum(motivos.values())}",
        f"⚠️ Entradas com sinais a rever: {len(problematicas)}",
        "🔒 Coorte, ranking, odds, resultados, CLV e critérios oficiais inalterados.",
    ]
    if motivos:
        linhas += ["", "🔎 Tipos de sinais:"]
        linhas.extend(f"• {nome}: {n}" for nome, n in motivos.most_common(10))
        linhas += ["", "🏟️ Entradas a rever (ate 8):"]
        for i, casa, fora, atual in problematicas[:8]:
            linhas.append(f"• Snapshot #{i} {casa} vs {fora} — {', '.join(atual[:3])}")
    else:
        linhas.append(
            "⚪ Nenhum sinal identificado nos metadados guardados. "
            "Nao equivale a identidade externa comprovada."
        )
    linhas += [
        "",
        "ℹ️ A ausencia de timestamp ou ID pode refletir dados historicos legados.",
        "ℹ️ Este diagnostico NAO altera nem reprova automaticamente a V1.3.",
        "ℹ️ Zero pedidos de odds ou resultados; sem recolha nova.",
    ]
    return "\n".join(linhas)
