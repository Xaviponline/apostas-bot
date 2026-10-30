"""Impacto descritivo da idade da ultima alteracao de preco na coorte V1.3.

SHADOW / somente leitura: nao faz HTTP, nao reclassifica entradas VALUE,
nao altera odds, resultados, snapshot, gate, V1.2, CLV ou carteira comercial.
Idade de mudanca de preco NAO prova disponibilidade/executabilidade.
"""
from math import isfinite

from auditoria_idade_odds_v13_shadow import _instante

LIMIAR_SEG = 6 * 3600
GRUPOS = (
    ("ate_6h", "Alteracao ate 6h"),
    ("mais_6h", "Alteracao ha mais de 6h"),
    ("desconhecida", "Sem timestamps comparaveis"),
    ("futura", "Alteracao futura >5m"),
)


def _numero(valor):
    if isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (ValueError, TypeError, OverflowError):
        return None
    return numero if isfinite(numero) else None


def _grupo(p):
    captura = _instante(p.get("odds_capturada_em") or p.get("valor_confirmado_em"))
    alteracao = _instante(p.get("odds_atualizada_em"))
    if captura is None or alteracao is None:
        return "desconhecida"
    delta = (captura - alteracao).total_seconds()
    if delta < -300:
        return "futura"
    if delta > LIMIAR_SEG:
        return "mais_6h"
    return "ate_6h"


def _novo():
    return {
        "entradas": 0, "liquidadas": 0, "ganhos": 0,
        "lucro": 0.0, "fechos": 0, "sem_pnl": 0,
        "probs": [], "dias": set(),
    }


def relatorio_impacto_frescura_v13(registo):
    """Usa os indices OFICIAIS da coorte; nunca volta a selecionar entradas."""
    met = registo.metricas_v13_comercial()
    coorte = met.get("coorte")
    originais = registo.dados.get("previsoes") if isinstance(registo.dados, dict) else None
    if not isinstance(coorte, list) or not isinstance(originais, list):
        raise ValueError("Coorte V1.3 indisponivel")
    grupos = {nome: _novo() for nome, _ in GRUPOS}
    vistos = set()
    inconsistentes = 0
    for item in coorte:
        if not isinstance(item, dict):
            inconsistentes += 1
            continue
        idx = _numero(item.get("snapshot"))
        if idx is None or not idx.is_integer() or not 1 <= idx <= len(originais):
            inconsistentes += 1
            continue
        indice = int(idx)
        if indice in vistos or not isinstance(originais[indice - 1], dict):
            inconsistentes += 1
            continue
        vistos.add(indice)
        p = originais[indice - 1]
        g = grupos[_grupo(p)]
        g["entradas"] += 1
        clv = _numero(item.get("clv"))
        if clv is not None:
            g["fechos"] += 1
        resultado = item.get("resultado_binario")
        if isinstance(resultado, bool) or resultado not in (0, 1):
            continue
        lucro = _numero(item.get("lucro_unidades"))
        if lucro is None:
            g["sem_pnl"] += 1
            continue
        g["liquidadas"] += 1
        g["ganhos"] += int(resultado)
        g["lucro"] += lucro
        data = str(item.get("data_jogo") or "")
        if len(data) == 10 and data[4:5] == "-" and data[7:8] == "-":
            g["dias"].add(data)
        prob = _numero(p.get("probabilidade"))
        if prob is not None and 0 < prob < 1:
            g["probs"].append((prob, int(resultado)))
    linhas = [
        "🧪 IMPACTO DA IDADE DAS ODDS — V1.3 SHADOW",
        "🔒 Mesma coorte fixa /v13_comercial; nenhuma mudanca no motor.",
        f"📚 Entradas: {len(coorte)}/{met.get('alvo', 50)} | ligacoes inconsistentes: {inconsistentes}",
        "ℹ️ Grupos por idade da ULTIMA ALTERACAO do preco ate a captura, nao por disponibilidade na Betano.",
        "",
    ]
    for chave, titulo in GRUPOS:
        g = grupos[chave]
        n = g["liquidadas"]
        linhas.append(f"📍 {titulo}: {g['entradas']} entradas | {n} liquidadas | {len(g['dias'])} dias")
        if n:
            roi = 100 * g["lucro"] / n
            linhas.append(
                f"   ✅ {g['ganhos']}/{n} | P/L {g['lucro']:+.2f}u | ROI {roi:+.1f}%".replace(".", ",")
            )
        else:
            linhas.append("   ⏳ Sem P/L liquidado valido neste grupo")
        linhas.append(f"   CLV com fecho: {g['fechos']}/{g['entradas']}")
        if g["probs"]:
            previsto = sum(pr for pr, _ in g["probs"]) / len(g["probs"])
            real = sum(y for _, y in g["probs"]) / len(g["probs"])
            linhas.append(
                f"   Prev {previsto * 100:.1f}% | real {real * 100:.1f}% | gap {(real-previsto) * 100:+.1f}pp".replace(".", ",")
            )
        if g["sem_pnl"]:
            linhas.append(f"   ⚠️ {g['sem_pnl']} liquidacoes sem P/L utilizavel (omitidas do ROI)")
        linhas.append("")
    linhas.extend([
        "⚠️ Comparacao observacional e exploratoria; grupos pequenos, mercados e datas diferentes.",
        "⚠️ Ultima alteracao antiga nao prova que a odd estivesse errada ou indisponivel.",
        "🔒 Zero HTTP; sem alterar odds, CLV, ROI oficial, coorte, selecao ou gate.",
    ])
    return "\n".join(linhas)
