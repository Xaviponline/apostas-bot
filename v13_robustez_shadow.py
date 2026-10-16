"""Auditoria exploratória V1.3 Comercial: apenas métricas de coorte já congelada.

Nunca executa consultas externas, escreve no histórico ou modifica o gate.
O bootstrap reamostra DIAS completos (clusters), em vez de tratar seleções
no mesmo dia como observações independentes. Intervalos são exploratórios.
"""
from collections import Counter, defaultdict
from math import isfinite
from random import Random
import re


MIN_LIQUIDADAS_IC = 20
MIN_DIAS_IC = 8
REPETICOES = 1200
SEMENTE = 20261017


def _percentagem(valor):
    return f"{valor * 100:+.1f}%".replace(".", ",")


def _numero(valor):
    try:
        n = float(valor)
    except (ValueError, TypeError, OverflowError):
        return None
    return n if isfinite(n) else None


def _intervalo_roi_por_dia(dias):
    """IC percentil bootstrap 95% por dia; não pressupõe independência intra-dia."""
    amostras = list(dias.values())
    n_dias = len(amostras)
    sorteio = Random(SEMENTE)
    rois = []
    for _ in range(REPETICOES):
        amostras_dia = [amostras[sorteio.randrange(n_dias)] for _ in range(n_dias)]
        soma = sum(soma for soma, _ in amostras_dia)
        quantidade = sum(n for _, n in amostras_dia)
        if quantidade:
            rois.append(soma / quantidade)
    if len(rois) != REPETICOES:
        return None
    rois.sort()
    return rois[int(0.025 * (REPETICOES - 1))], rois[int(0.975 * (REPETICOES - 1))]


def relatorio_robustez_v13(metricas):
    """Relatório passivo exclusivamente sobre a coorte FIXA definida pela V1.3."""
    coorte = metricas.get("coorte") or []
    if not isinstance(coorte, list):
        raise ValueError("Coorte inválida")
    entradas = []
    datas_invalidas = 0
    for item in coorte:
        if not isinstance(item, dict):
            raise ValueError("Entrada inválida")
        resultado = item.get("resultado_binario")
        if resultado not in (0, 1):
            continue
        lucro = _numero(item.get("lucro_unidades"))
        if lucro is None:
            raise ValueError("P/L liquidado inválido")
        data = str(item.get("data_jogo") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data):
            datas_invalidas += 1
        entradas.append((data, str(item.get("mercado") or "Não indicado"), lucro))

    total = len(entradas)
    lucro_total = sum(e[2] for e in entradas)
    dias = defaultdict(lambda: [0.0, 0])
    mercados = Counter()
    for data, mercado, pnl in entradas:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", data):
            dias[data][0] += pnl
            dias[data][1] += 1
        mercados[mercado] += 1

    linhas = [
        "🛡️ V1.3 ROBUSTEZ — AUDITORIA SHADOW",
        "🔒 Mesma coorte fixa Top5 + VALUE do /v13_comercial",
        f"• Estado do gate original: {metricas.get('estado') or '?'} (inalterado)",
        f"• Coorte: {metricas.get('coorte_tamanho', len(coorte))}/{metricas.get('alvo', '?')} | Liquidadas: {total}",
        "• Comparador descritivo: ROI de equilíbrio = 0%",
        "• Stakes virtuais fixas: 1u por entrada elegível liquidada",
    ]
    if not total:
        linhas += [
            "", "⏳ Sem entradas VALUE liquidadas suficientes para calcular risco ou ROI.",
            "Nenhum resultado inferido a partir de entradas pendentes.",
        ]
    else:
        roi = lucro_total / total
        linhas += [
            "", "📊 RISCO OBSERVADO (descritivo)",
            f"• ROI observado: {_percentagem(roi)} | P/L: {lucro_total:+.2f}u".replace(".", ","),
            f"• Dias com liquidações: {len(dias)} | CLV com fecho: {metricas.get('clv_amostras', 0)}",
            f"• Máximo drawdown da coorte: {float(metricas.get('max_drawdown') or 0):.2f}u".replace(".", ","),
            f"• Maior sequência de perdas: {metricas.get('max_streak_perdas', 0)}",
        ]
        if dias:
            pior_data, (pior_lucro, _) = min(dias.items(), key=lambda x: (x[1][0], x[0]))
            linhas.append(f"• Pior dia liquidado: {pior_data} | {pior_lucro:+.2f}u".replace(".", ","))
        if mercados:
            mercado, n = sorted(mercados.items(), key=lambda x: (-x[1], x[0]))[0]
            linhas.append(f"• Mercado mais frequente: {mercado} — {n}/{total} ({n / total * 100:.1f}%)".replace(".", ","))

        linhas += ["", "📐 INCERTEZA DO ROI"]
        if total < MIN_LIQUIDADAS_IC or len(dias) < MIN_DIAS_IC or datas_invalidas:
            linhas.append(
                f"• Intervalo não estimado: exigir ≥{MIN_LIQUIDADAS_IC} liquidadas, "
                f"≥{MIN_DIAS_IC} dias válidos e datas completas. "
                f"Atual: {total} liquidadas, {len(dias)} dias, {datas_invalidas} datas inválidas."
            )
        else:
            limites = _intervalo_roi_por_dia(dias)
            if limites is None:
                linhas.append("• Intervalo indisponível; nenhum valor inventado.")
            else:
                linhas.append(
                    f"• IC95% bootstrap por dia: {_percentagem(limites[0])} a {_percentagem(limites[1])}"
                )
                if limites[0] <= 0 <= limites[1]:
                    linhas.append("• O intervalo inclui ROI 0%: a vantagem não está demonstrada.")
                elif limites[1] < 0:
                    linhas.append("• Intervalo abaixo de ROI 0%; investigar o desempenho.")
                else:
                    linhas.append("• Intervalo acima de ROI 0%; validação adicional ainda obrigatória.")
        linhas.append("• Bootstrap exploratório; poucos dias e dependência entre jogos limitam a inferência.")

    linhas += [
        "", "⚠️ Coorte parcial e subgrupos não permitem inferir rentabilidade futura.",
        "⚠️ Não confirma apostas executadas, liquidez nem preços disponíveis na Betano.",
        "🔒 Zero OddsPapi/ESPN/Telegram externo; sem alterar ROI oficial, gate, seleção,",
        "   probabilidades, V1.2, SEL1, V1.3, odds, CLV ou snapshots.",
    ]
    return "\n".join(linhas)
