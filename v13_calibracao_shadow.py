"""Calibracao descritiva da MESMA coorte comercial V1.3.

Exclusivamente read-only: a selecao V1.2, VALUE, odds, CLV, ROI,
liquidacoes e gate continuam fixos. Sem acesso a rede ou ao disco.
Avaliacao por mercado e global sao exploratorias, sem promocao automatica.
"""
from collections import defaultdict
from math import isfinite


MIN_AMOSTRA_GLOBAL = 30
MIN_AMOSTRA_MERCADO = 10


def _probabilidade(valor):
    if isinstance(valor, bool):
        return None
    try:
        x = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if isfinite(x) and 0.0 < x < 1.0 else None


def _resumo(amostras):
    n = len(amostras)
    if not n:
        return None
    previstas = sum(p for p, _ in amostras)
    reais = sum(y for _, y in amostras)
    brier = sum((p - y) ** 2 for p, y in amostras) / n
    return {
        "n": n,
        "previstas": previstas,
        "reais": reais,
        "media_prob": previstas / n,
        "taxa_real": reais / n,
        "gap_pp": (reais - previstas) / n * 100,
        "brier": brier,
    }


def _pc(fracao):
    return f"{fracao * 100:.1f}%".replace(".", ",")


def _pp(pontos):
    return f"{pontos:+.1f}pp".replace(".", ",")


def _f(numero, casas=3):
    return f"{numero:.{casas}f}".replace(".", ",")


def relatorio_calibracao_v13(registo):
    """Usa indices snapshot da coorte oficial, sem criar entradas adicionais."""
    metricas = registo.metricas_v13_comercial()
    coorte = metricas.get("coorte")
    originais = registo.dados.get("previsoes")
    if not isinstance(coorte, list) or not isinstance(originais, list):
        raise ValueError("Coorte ou snapshots invalidos.")

    amostras = []
    mercados = defaultdict(list)
    dias_liquidados = set()
    anomalias = 0
    pendentes = 0
    vistos = set()

    for item in coorte:
        if not isinstance(item, dict):
            anomalias += 1
            continue
        try:
            indice = int(item.get("snapshot"))
        except (ValueError, TypeError, OverflowError):
            anomalias += 1
            continue
        if indice < 1 or indice > len(originais) or indice in vistos:
            anomalias += 1
            continue
        vistos.add(indice)
        resultado = item.get("resultado_binario")
        if resultado is None:
            pendentes += 1
            continue
        if isinstance(resultado, bool) or resultado not in (0, 1):
            anomalias += 1
            continue
        p_original = originais[indice - 1]
        if not isinstance(p_original, dict):
            anomalias += 1
            continue
        prob = _probabilidade(p_original.get("probabilidade"))
        if prob is None:
            anomalias += 1
            continue
        mercado = str(item.get("mercado") or p_original.get("mercado") or "Sem mercado")
        y = int(resultado)
        amostras.append((prob, y))
        mercados[mercado].append((prob, y))
        data = str(item.get("data_jogo") or "")
        if data:
            dias_liquidados.add(data)

    global_ = _resumo(amostras)
    linhas = [
        "📐 CALIBRACAO V1.3 — SHADOW / TOP5 + VALUE",
        f"🔒 Coorte oficial: {len(coorte)}/{metricas.get('alvo', 50)} | estado: {metricas.get('estado', '?')}",
        f"📚 Liquidadas com probabilidade valida: {len(amostras)} | pendentes: {pendentes}",
        f"📅 Dias com liquidacoes: {len(dias_liquidados)} | dados incompletos: {anomalias}",
        "",
    ]
    if global_ is None:
        linhas += [
            "⏳ Sem resultados suficientes para comparar previsao com frequencia real.",
            "Nao inferir qualidade do modelo a partir de jogos pendentes.",
        ]
    else:
        g = global_
        linhas += [
            "🎯 CALIBRACAO GLOBAL (descritiva)",
            f"• Probabilidade media prevista: {_pc(g['media_prob'])}",
            f"• Acertos observados: {g['reais']}/{g['n']} ({_pc(g['taxa_real'])})",
            f"• Acertos esperados pelo modelo: {_f(g['previstas'], 2)}",
            f"• Diferenca real − previsto: {_pp(g['gap_pp'])}",
            f"• Brier Score na coorte: {_f(g['brier'], 4)} (menor e melhor)",
            "",
            "⚽ SEGMENTACAO POR MERCADO",
        ]
        for nome, valores in sorted(mercados.items(), key=lambda v: (-len(v[1]), v[0]))[:8]:
            m = _resumo(valores)
            if m["n"] < MIN_AMOSTRA_MERCADO:
                linhas.append(
                    f"• {nome}: n={m['n']} | amostra pequena (<{MIN_AMOSTRA_MERCADO}); "
                    "sem inferencia por mercado"
                )
            else:
                linhas.append(
                    f"• {nome}: n={m['n']} | esperado {_pc(m['media_prob'])}"
                    f" | real {_pc(m['taxa_real'])} | desvio {_pp(m['gap_pp'])}"
                    f" | Brier {_f(m['brier'], 4)}"
                )
        if len(mercados) > 8:
            linhas.append(f"• +{len(mercados) - 8} mercados adicionais (nao exibidos)")
        if len(amostras) < MIN_AMOSTRA_GLOBAL or len(dias_liquidados) < 10:
            linhas += [
                "",
                f"⚠️ Amostra ainda reduzida: exigir >= {MIN_AMOSTRA_GLOBAL} resultados",
                "   e >= 10 dias para um diagnostico exploratorio mais util.",
            ]
        else:
            linhas += [
                "",
                "⚠️ Estes indicadores continuam exploratorios. A coorte VALUE",
                "   seleciona jogos, pelo que nao valida a calibracao global da V1.2.",
            ]
    linhas += [
        "",
        "ℹ️ Uma diferenca em pp nao prova vies do modelo numa amostra pequena.",
        "ℹ️ Calibracao nao prova rentabilidade nem disponibilidade das odds na Betano.",
        "🔒 Zero HTTP / zero escrita. Gate original, ROI, CLV e coorte intocados.",
    ]
    return "\n".join(linhas)
