"""Cruzamento exploratorio V1.3 por mercado e idade da ultima mudanca de odd.

SHADOW / OWNER: usa exclusivamente indices da coorte oficial e snapshots
ja carregados. Zero HTTP, IO, alteracao de odds, CLV, previsoes ou gate.
Os resultados descrevem associacoes, nao causalidade nem provas Betano.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import isfinite
from statistics import median

from auditoria_idade_odds_v13_shadow import _instante

BIN_NAMES = (
    ("ate6", "ate 6h"),
    ("6a24", "6-24h"),
    ("mais24", "mais 24h"),
    ("semhora", "sem comparacao"),
    ("futura", "hora futura >5m"),
)
MERCADOS = {
    "under35": "Under 3.5 Golos",
    "under25": "Under 2.5 Golos",
    "over25": "Over 2.5 Golos",
    "casa": "Vitória Casa",
    "fora": "Vitória Fora",
}


def _numero(valor):
    if isinstance(valor, bool):
        return None
    try:
        n = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if isfinite(n) else None


def _indice(valor, limite):
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        n = valor
    elif isinstance(valor, str) and valor.isascii() and valor.isdecimal():
        n = int(valor)
    else:
        return None
    return n if 1 <= n <= limite else None


def _idade(p):
    captura = _instante(p.get("odds_capturada_em") or p.get("valor_confirmado_em"))
    mudanca = _instante(p.get("odds_atualizada_em"))
    if captura is None or mudanca is None:
        return "semhora", None
    delta = (captura - mudanca).total_seconds()
    if delta < -300:
        return "futura", delta / 3600
    if delta > 86400:
        return "mais24", delta / 3600
    if delta > 21600:
        return "6a24", delta / 3600
    return "ate6", delta / 3600


def _empty():
    return {
        "entradas": 0, "liquidadas": 0, "ganhos": 0,
        "pnl_n": 0, "pnl": 0., "cal_n": 0,
        "previstas": 0., "reais": 0., "brier": 0.,
        "clv": [], "dias": set(), "pnl_por_dia": defaultdict(float),
        "ligas": Counter(),
    }


def _adicionar(g, p, e, idade):
    g["entradas"] += 1
    clv = _numero(e.get("clv"))
    if clv is not None:
        g["clv"].append(clv)
    diag = p.get("diagnostico_modelo")
    liga = diag.get("liga_codigo") if isinstance(diag, dict) else None
    if isinstance(liga, str) and liga.strip():
        g["ligas"][liga.strip()[:40]] += 1
    y = e.get("resultado_binario")
    if isinstance(y, bool) or y not in (0, 1):
        return
    g["liquidadas"] += 1
    g["ganhos"] += y
    dia = str(e.get("data_jogo") or "")
    if len(dia) == 10 and dia[4] == "-" and dia[7] == "-":
        g["dias"].add(dia)
    lucro = _numero(e.get("lucro_unidades"))
    if lucro is not None:
        g["pnl_n"] += 1
        g["pnl"] += lucro
        if dia in g["dias"]:
            g["pnl_por_dia"][dia] += lucro
    prob = _numero(p.get("probabilidade"))
    if prob is not None and 0 < prob < 1:
        g["cal_n"] += 1
        g["previstas"] += prob
        g["reais"] += y
        g["brier"] += (prob - y) ** 2


def _pct(n, sinal=False):
    return f"{n * 100:{'+.1f' if sinal else '.1f'}}%".replace(".", ",")


def _decimal(n, dig=2):
    return f"{n:+.{dig}f}".replace(".", ",")


def _linha(g):
    ent, liq = g["entradas"], g["liquidadas"]
    texto = f"{ent} ent/{liq} liq"
    if liq:
        texto += f" | {g['ganhos']}/{liq} acertos"
    if liq and g["pnl_n"] == liq:
        texto += f" | P/L {_decimal(g['pnl'])}u | ROI {_pct(g['pnl']/liq, True)}"
    elif liq:
        texto += f" | P/L valido {g['pnl_n']}/{liq}; sem ROI"
    if g["cal_n"]:
        n = g["cal_n"]
        gap = 100 * (g["reais"] - g["previstas"]) / n
        texto += f" | gap {_decimal(gap, 1)}pp | Brier {g['brier']/n:.3f}"
    texto += f" | CLV {len(g['clv'])}/{ent}"
    return texto


def _resumo_clv(clvs):
    if not clvs:
        return "sem fechos"
    mean = sum(clvs) / len(clvs)
    highest = max(clvs)
    no_max = ((sum(clvs) - highest) / (len(clvs) - 1)) if len(clvs) > 1 else None
    return (
        f"n={len(clvs)} | media {_pct(mean, True)}"
        f" | mediana {_pct(median(clvs), True)}"
        f" | positivos {sum(x > 0 for x in clvs)}/{len(clvs)}"
        f" | maior {_pct(highest, True)}"
        + (f" | media excluindo maior {_pct(no_max, True)}" if no_max is not None else "")
    )


def _extrair(registo):
    met = registo.metricas_v13_comercial()
    coorte = met.get("coorte")
    previsoes = registo.dados.get("previsoes") if isinstance(registo.dados, dict) else None
    if not isinstance(coorte, list) or not isinstance(previsoes, list):
        raise ValueError("Coorte ou previsoes invalidas")
    linhas, vistos, erros = [], set(), 0
    for item in coorte:
        if not isinstance(item, dict):
            erros += 1
            continue
        i = _indice(item.get("snapshot"), len(previsoes))
        if i is None or i in vistos or not isinstance(previsoes[i-1], dict):
            erros += 1
            continue
        vistos.add(i)
        p = previsoes[i-1]
        nome = str(p.get("mercado") or "").strip()
        if not nome or nome != str(item.get("mercado") or "").strip():
            erros += 1
            continue
        grupo, horas = _idade(p)
        linhas.append((i, nome, grupo, horas, p, item))
    return met, linhas, erros


def relatorio_cruzamento_v13(registo, argumento=""):
    """Resumo cruzado ou detalhe por mercado; nao modifica estado."""
    escolha = str(argumento or "").strip().lower()
    if escolha not in ("", "resumo", *MERCADOS.keys()):
        return "Formato: /v13_cruzamento [resumo|under35|under25|over25|casa|fora] — OWNER."
    met, entradas, invalidas = _extrair(registo)
    todos = _empty()
    grupos = defaultdict(_empty)
    por_mercado = defaultdict(_empty)
    for i, mercado, age, horas, p, e in entradas:
        _adicionar(todos, p, e, age)
        _adicionar(grupos[(mercado, age)], p, e, age)
        _adicionar(por_mercado[mercado], p, e, age)
    cabecalho = [
        "🔬 V1.3 — MERCADO × IDADE ODD | SHADOW",
        f"🔒 Coorte oficial {len(met['coorte'])}/{met.get('alvo', 50)}"
        f" | validas {len(entradas)} | inconsistencias {invalidas}",
        f"📚 Liquidadas {todos['liquidadas']} | pendentes {todos['entradas'] - todos['liquidadas']}",
    ]
    inconsistencias = []
    for chave, atual in (
        ("coorte_tamanho", todos["entradas"]),
        ("liquidadas", todos["liquidadas"]),
        ("clv_amostras", len(todos["clv"])),
    ):
        esperado = met.get(chave)
        if esperado is not None and esperado != atual:
            inconsistencias.append(f"{chave}: relatorio {atual}, oficial {esperado}")
    pnl_oficial = _numero(met.get("lucro_unidades"))
    if pnl_oficial is not None and (todos["pnl_n"] != todos["liquidadas"]
                                   or abs(todos["pnl"] - pnl_oficial) > 0.000001):
        inconsistencias.append("lucro nao reconcilia com a coorte oficial")
    if inconsistencias:
        cabecalho.append("⚠️ DADOS INCONSISTENTES — " + "; ".join(inconsistencias))
    else:
        cabecalho.append("✅ Totais reconciliados com metricas oficiais disponiveis")
    if escolha in ("", "resumo"):
        linhas = cabecalho + ["", "📊 GLOBAL: " + _linha(todos), "",
                             "⚽ GRUPOS POR MERCADO E IDADE DA ULTIMA ALTERACAO"]
        for mercado in sorted(por_mercado, key=lambda m: (-por_mercado[m]["entradas"], m)):
            linhas.append(f"• {mercado} — {por_mercado[mercado]['entradas']} entradas")
            for bin_id, nome in BIN_NAMES:
                g = grupos.get((mercado, bin_id))
                if g and g["entradas"]:
                    linhas.append("  " + nome + ": " + _linha(g))
        u = por_mercado.get("Under 3.5 Golos")
        if u:
            linhas += ["", "🔎 CLV UNDER 3.5: " + _resumo_clv(u["clv"])]
        linhas += [
            "", "ℹ️ Idade = captura menos ULTIMA alteracao do preco; nao e disponibilidade Betano.",
            "⚠️ Cruzamentos exploratorios, amostras pequenas, datas e ligas diferentes.",
            "🔒 Sem HTTP/escrita; sem mudar odds, snapshots, VALUE, CLV ou gate.",
            "🔍 /v13_cruzamento under35 — casos individuais sem novas consultas.",
        ]
        return "\n".join(linhas)
    mercado = MERCADOS[escolha]
    g = por_mercado.get(mercado, _empty())
    linhas = cabecalho + ["", f"🎯 DETALHE: {mercado}", _linha(g),
                         "CLV: " + _resumo_clv(g["clv"])]
    if g["pnl_por_dia"]:
        piores = sorted(g["pnl_por_dia"].items(), key=lambda x: (x[1], x[0]))
        dia, pl = piores[0]
        linhas.append(f"📅 Dias com liquidacoes: {len(g['dias'])} | pior dia: {dia} P/L {_decimal(pl)}u")
    if g["ligas"]:
        ligas = ", ".join(f"{nome}:{n}" for nome, n in g["ligas"].most_common(5))
        linhas.append("🏆 Codigos liga modelo: " + ligas)
    linhas += ["", "📋 ENTRADAS DA COORTE (nao todas as rondas de odds):"]
    for i, nome, bin_id, horas, p, e in entradas:
        if nome != mercado:
            continue
        y = e.get("resultado_binario")
        simbolo = "✅" if y == 1 and not isinstance(y, bool) else (
            "❌" if y == 0 and not isinstance(y, bool) else "⏳")
        age_label = next(nome for b, nome in BIN_NAMES if b == bin_id)
        idade = (f"{horas:.1f}h".replace(".", ",") if horas is not None else "?")
        prob = _numero(p.get("probabilidade"))
        odds = _numero(e.get("odd_entrada"))
        clv = _numero(e.get("clv"))
        pnl = _numero(e.get("lucro_unidades"))
        curto = lambda s: str(s or "?").replace("\n", " ").replace("\r", " ")[:34]
        linhas.append(
            f"#{i} {curto(e.get('data_jogo'))} {curto(p.get('casa'))} vs {curto(p.get('fora'))} {simbolo}"
        )
        linhas.append(
            f"   {age_label} ({idade}) | p={_pct(prob) if prob is not None else '?'}"
            f" | odd @{str(odds).replace('.', ',') if odds is not None else '?'}"
            f" | PL {_decimal(pnl) + 'u' if pnl is not None and y in (0,1) else '-'}"
            f" | CLV {_pct(clv, True) if clv is not None else 'falta'}"
        )
    linhas += [
        "", "ℹ️ CLV oficial: nao recuperar ausencias nem substituir por observacoes T-10m.",
        "⚠️ Subgrupos/dias e odds nao demonstram causa, edge ou executabilidade.",
        "🔒 Zero HTTP / zero escrita; todos os protocolos existentes intactos.",
    ]
    return "\n".join(linhas)
