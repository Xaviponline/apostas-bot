"""Auditoria descritiva de mercados da coorte prospetiva V1.3 (SHADOW).

Lê a MESMA coorte oficial. Sem IO, rede, apostas, alteração de filtros,
preços, snapshots, CLV, SEL1, Platt ou gate. Os grupos são exploratórios.
"""
from collections import defaultdict
from math import isfinite

MIN_N_MERCADO = 10


def _n(v):
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return f if isfinite(f) else None


def _indice(v, limite):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        i = v
    elif isinstance(v, str) and v.isascii() and v.isdecimal():
        i = int(v)
    else:
        return None
    return i if 1 <= i <= limite else None


def _novo():
    return {
        "entradas": 0, "liquidadas": 0, "ganhos": 0,
        "pnl_n": 0, "pnl": 0.0,
        "clv_n": 0, "clv_soma": 0.0, "clv_pos": 0,
        "cal_n": 0, "previstas": 0.0, "reais": 0.0, "brier_soma": 0.0,
    }


def _add(g, p, item):
    g["entradas"] += 1
    clv = _n(item.get("clv"))
    if clv is not None:
        g["clv_n"] += 1
        g["clv_soma"] += clv
        g["clv_pos"] += int(clv > 0)
    y = item.get("resultado_binario")
    if isinstance(y, bool) or y not in (0, 1):
        return
    g["liquidadas"] += 1
    g["ganhos"] += int(y)
    pnl = _n(item.get("lucro_unidades"))
    if pnl is not None:
        g["pnl_n"] += 1
        g["pnl"] += pnl
    prob = _n(p.get("probabilidade"))
    if prob is not None and 0 < prob < 1:
        g["cal_n"] += 1
        g["previstas"] += prob
        g["reais"] += int(y)
        g["brier_soma"] += (prob - int(y)) ** 2


def _percent(p):
    return f"{p * 100:+.1f}%".replace(".", ",")


def _fmt(x, casas=2):
    return f"{x:.{casas}f}".replace(".", ",")


def _linha(titulo, g):
    partes = [
        f"• {titulo}: {g['entradas']} entradas, {g['liquidadas']} liquidadas",
        f"  Acertos {g['ganhos']}/{g['liquidadas']}",
    ]
    if g["pnl_n"] == g["liquidadas"] and g["pnl_n"]:
        partes[-1] += f" | ROI {_percent(g['pnl'] / g['pnl_n'])} | P/L {_fmt(g['pnl'])}u"
    elif g["liquidadas"]:
        partes[-1] += f" | P/L utilizavel {g['pnl_n']}/{g['liquidadas']} (ROI incompleto)"
    partes.append(
        f"  CLV oficial: {g['clv_n']}/{g['entradas']}"
        + (f" | medio {_percent(g['clv_soma'] / g['clv_n'])} | positivos {g['clv_pos']}"
           if g["clv_n"] else " | media indisponivel")
    )
    if g["cal_n"]:
        partes.append(
            f"  Prev {_percent(g['previstas'] / g['cal_n'])}"
            f" | real {_percent(g['reais'] / g['cal_n'])}"
            f" | gap {_fmt(100 * (g['reais'] - g['previstas']) / g['cal_n'], 1)}pp"
            f" | Brier {_fmt(g['brier_soma'] / g['cal_n'], 4)}"
            f" | n calib {g['cal_n']}"
        )
    else:
        partes.append("  Calibracao indisponivel (sem probabilidade+resultado validos)")
    if g["liquidadas"] < MIN_N_MERCADO:
        partes.append(f"  ⚠️ Subgrupo pequeno (<{MIN_N_MERCADO}); sem conclusao")
    return "\n".join(partes)


def relatorio_mercados_v13(registo):
    """Resume mercado original, Under 2.5 vs restantes e totais, sem mutações."""
    metricas = registo.metricas_v13_comercial()
    coorte = metricas.get("coorte")
    originais = registo.dados.get("previsoes")
    if not isinstance(coorte, list) or not isinstance(originais, list):
        raise ValueError("Coorte oficial ou snapshots nao disponiveis")
    grupos = defaultdict(_novo)
    under = _novo()
    outros = _novo()
    geral = _novo()
    vistos = set()
    inconsistencias = 0
    for item in coorte:
        if not isinstance(item, dict):
            inconsistencias += 1
            continue
        i = _indice(item.get("snapshot"), len(originais))
        if i is None or i in vistos or not isinstance(originais[i - 1], dict):
            inconsistencias += 1
            continue
        vistos.add(i)
        p = originais[i - 1]
        mercado = str(p.get("mercado") or "").strip()
        declarado = str(item.get("mercado") or "").strip()
        if not mercado or not declarado or mercado != declarado:
            inconsistencias += 1
            continue
        mercado = mercado.replace("\r", " ").replace("\n", " ")[:90]
        _add(grupos[mercado], p, item)
        _add(under if mercado == "Under 2.5 Golos" else outros, p, item)
        _add(geral, p, item)
    linhas = [
        "📊 MERCADOS DA V1.3 — AUDITORIA SHADOW",
        f"🔒 Coorte FIXA: {len(coorte)}/{metricas.get('alvo', 50)}; "
        f"ligacoes invalidas ou inconsistentes: {inconsistencias}",
        f"📚 Entradas auditaveis: {geral['entradas']} | liquidadas: {geral['liquidadas']}",
        "",
        "🎯 UNDER 2.5 VS RESTANTES (grupos disjuntos)",
        _linha("Under 2.5 Golos", under),
        _linha("Todos os outros", outros),
        "",
        "⚽ POR MERCADO (ordenados por quantidade)",
    ]
    for nome, g in sorted(grupos.items(), key=lambda x: (-x[1]["entradas"], x[0])):
        linhas.append(_linha(nome, g))
    linhas += [
        "",
        "ℹ️ CLV so entre fechos oficiais existentes; nenhum T-10m substitui T-30m.",
        "⚠️ Comparacao exploratoria: n pequeno, mercados/dias diferentes; nao seleccionar filtros pelo ROI.",
        "⚠️ Ultima alteracao do preco nao prova a disponibilidade na Betano.",
        "🔒 Zero HTTP / zero escrita; V1.2, SEL1, V1.3, Platt e gate intactos.",
    ]
    return "\n".join(linhas)
