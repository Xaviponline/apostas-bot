"""Idade das timestamps de odds na coorte V1.3: relatório retrospetivo.

Não trata "última mudança de preço" como "última disponibilidade".
Só lê registos já guardados. Sem rede, reclassificação ou mutações de coorte.
"""
from datetime import datetime, timezone
from math import isfinite
from zoneinfo import ZoneInfo

PT = ZoneInfo("Europe/Lisbon")
DIA = 24 * 3600


def _instante(valor):
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        dt = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def _hora(valor):
    dt = _instante(valor)
    return dt.astimezone(PT).strftime("%d/%m %H:%M") if dt else "não registada"


def _odd(valor):
    try:
        n = float(valor)
    except (TypeError, ValueError, OverflowError):
        return "?"
    return f"{n:.2f}" if isfinite(n) and n > 1 else "?"


def _horas(valor):
    return f"{valor:.1f}".replace(".", ",")


def _inicio(valor):
    try:
        n = float(valor)
        if not isfinite(n):
            return None
        return datetime.fromtimestamp(n, timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _detalhe(item, p):
    captura = _instante(p.get("odds_capturada_em") or p.get("valor_confirmado_em"))
    mudanca = _instante(p.get("odds_atualizada_em"))
    idade = (captura - mudanca).total_seconds() if captura and mudanca else None
    if idade is None:
        estado = "sem timestamps comparáveis"
    elif idade < -300:
        estado = "timestamp futuro face à captura"
    elif idade < 0:
        estado = "diferença negativa pequena"
    elif idade > 6 * 3600:
        estado = "última alteração há mais de 6h"
    else:
        estado = "última alteração até 6h"
    jogo = _inicio(p.get("timestamp_jogo"))
    ate_jogo = ((jogo - captura).total_seconds() / 3600) if jogo and captura else None
    return {
        "snapshot": int(item["snapshot"]),
        "casa": str(p.get("casa") or "?"),
        "fora": str(p.get("fora") or "?"),
        "mercado": str(p.get("mercado") or "?"),
        "origem": str(p.get("odds_fonte") or "não registada"),
        "fixture": str(p.get("odds_event_id") or "não registado"),
        "alteracao": _hora(p.get("odds_atualizada_em")),
        "captura": _hora(p.get("odds_capturada_em") or p.get("valor_confirmado_em")),
        "confirmacao": _hora(p.get("valor_confirmado_em")),
        "inicio": jogo.astimezone(PT).strftime("%d/%m %H:%M") if jogo else "não registado",
        "idade": idade,
        "estado": estado,
        "horas_ate_jogo": ate_jogo,
        "odd_real": _odd(p.get("odd_real")),
        "odd_confirmada": _odd(p.get("odd_valor_confirmado")),
    }


def relatorio_idade_odds_v13(registo, argumento=""):
    """Coorte exatamente como pré-registada, sem recomputação independente."""
    filtro = str(argumento or "").strip()
    if filtro and (not filtro.isascii() or not filtro.isdecimal()
                   or not 1 <= len(filtro) <= 6):
        return "Formato: /v13_idade_odds [numero_snapshot] — OWNER."
    alvo = int(filtro) if filtro else None
    dados = registo.metricas_v13_comercial()
    previsoes = registo.dados.get("previsoes", [])
    entradas = []
    for item in dados.get("coorte", []):
        try:
            indice = int(item["snapshot"])
            if indice < 1 or indice > len(previsoes):
                continue
            p = previsoes[indice - 1]
            if not isinstance(p, dict):
                continue
            entradas.append(_detalhe(item, p))
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
    if alvo is not None and alvo not in {e["snapshot"] for e in entradas}:
        return (
            f"⚪ Snapshot #{alvo} não pertence às entradas já fixadas na coorte V1.3. "
            "Não foram consultadas odds."
        )

    categorias = {
        "ate_6h": 0, "mais_6h_ate_24h": 0,
        "mais_24h": 0, "sem_comparacao": 0, "timestamp_futuro": 0,
    }
    for e in entradas:
        delta = e["idade"]
        if delta is None:
            categorias["sem_comparacao"] += 1
        elif delta < -300:
            categorias["timestamp_futuro"] += 1
        elif delta > DIA:
            categorias["mais_24h"] += 1
        elif delta > 6 * 3600:
            categorias["mais_6h_ate_24h"] += 1
        else:
            categorias["ate_6h"] += 1
    linhas = [
        "🕒 IDADE DAS ODDS — COORTE V1.3 | SHADOW",
        f"📊 Entradas: {len(entradas)} | ≤6h: {categorias['ate_6h']}"
        f" | 6–24h: {categorias['mais_6h_ate_24h']}"
        f" | >24h: {categorias['mais_24h']}"
        f" | sem comparação: {categorias['sem_comparacao']}"
        f" | futuras: {categorias['timestamp_futuro']}",
        "ℹ️ Idade = captura pelo bot − última mudança de preço indicada pela fonte.",
        "⚠️ Preço não alterado há horas NÃO prova cotação indisponível ou errada.",
    ]
    destacados = [e for e in entradas if e["idade"] is not None
                   and (e["idade"] > 6 * 3600 or e["idade"] < -300)]
    if alvo is not None:
        destacados = [e for e in entradas if e["snapshot"] == alvo]
    if not destacados:
        linhas.append("⚪ Nenhuma entrada com timestamp suspeito neste filtro.")
    for e in destacados[:8 if alvo is None else 1]:
        idade = (_horas(e["idade"] / 3600) + "h"
                 if e["idade"] is not None else "não calculável")
        falta = (_horas(e["horas_ate_jogo"]) + "h"
                 if e["horas_ate_jogo"] is not None else "?")
        linhas.extend([
            "",
            f"• #{e['snapshot']} {e['casa']} vs {e['fora']}",
            f"  Mercado: {e['mercado']} | fonte: {e['origem']}",
            f"  Hora de alteração: {e['alteracao']} | captura: {e['captura']}",
            f"  Idade da alteração: {idade} — {e['estado']}",
            f"  Entrada: @{e['odd_confirmada']} | primeira odd: @{e['odd_real']}",
            f"  Início: {e['inicio']} | captura antes do início: {falta}",
            f"  Fixture fonte: {e['fixture']} | VALUE confirmado: {e['confirmacao']}",
        ])
    if len(destacados) > 8 and alvo is None:
        linhas.append(f"… mais {len(destacados) - 8} entradas; pedir por snapshot.")
    linhas += [
        "",
        "🔒 Zero HTTP. Não altera entradas, odds, ROI, CLV, ranking nem critérios V1.3.",
        "🔎 Para prova adicional consultar /odds_rastreio_detalhe NOME (local).",
    ]
    return "\n".join(linhas)
