"""Auditoria temporal de calibracao; nunca recalibra nem altera previsoes oficiais."""
from collections import defaultdict
from datetime import datetime, timezone
from math import isfinite


def _float(v):
    try:
        x = float(v)
        return x if isfinite(x) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _metricas(rows):
    n = len(rows)
    if not n:
        return "n=0 (insuficiente)"
    p = sum(x[1] for x in rows) / n
    y = sum(x[2] for x in rows) / n
    b = sum((x[1]-x[2])**2 for x in rows)/n
    return f"n={n} | previsto {p*100:.1f}% | real {y*100:.1f}% | desvio {(p-y)*100:+.1f}pp | Brier {b:.3f}"


def relatorio_calibracao_shadow(dados):
    snapshots = dados.get("previsoes", []) if isinstance(dados, dict) else []
    rows = []
    for s in snapshots:
        if not isinstance(s, dict) or s.get("resultado_binario") not in (0, 1):
            continue
        p = _float(s.get("probabilidade"))
        if p is None or not 0 <= p <= 1:
            continue
        data = str(s.get("data_jogo") or "")
        if len(data) != 10 or data[4] != "-" or data[7] != "-":
            continue
        rows.append((data, p, int(s["resultado_binario"]), str(s.get("mercado") or "?")))
    rows.sort(key=lambda r: r[0])
    linhas = ["🧪 CALIBRAÇÃO SHADOW — APENAS LEITURA", f"📚 Seleções liquidadas com data: {len(rows)}", "📊 Global: " + _metricas(rows)]
    if not rows:
        linhas.append("Sem dados suficientes para avaliar calibração.")
        return "\n".join(linhas)
    por_mercado = defaultdict(list)
    por_faixa = defaultdict(list)
    por_mes = defaultdict(list)
    for r in rows:
        por_mercado[r[3]].append(r)
        por_faixa[min(9, int(r[1]*10))].append(r)
        por_mes[r[0][:7]].append(r)
    linhas.append("🎯 Por mercado:")
    for nome, sub in sorted(por_mercado.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:12]:
        linhas.append(f"• {nome}: {_metricas(sub)}")
    linhas.append("📈 Por probabilidade prevista:")
    for i, sub in sorted(por_faixa.items()):
        linhas.append(f"• {i*10}–{(i+1)*10}%: {_metricas(sub)}")
    linhas.append("📅 Últimos meses:")
    for mes, sub in sorted(por_mes.items())[-6:]:
        linhas.append(f"• {mes}: {_metricas(sub)}")
    # Corte temporal por data (sem baralhar registos do mesmo dia entre treino e teste).
    dias = sorted(set(r[0] for r in rows))
    if len(dias) >= 4:
        corte = dias[max(1, int(len(dias)*.7))]
        treino = [r for r in rows if r[0] < corte]
        teste = [r for r in rows if r[0] >= corte]
        linhas.append(f"🧭 Validação temporal: corte {corte}")
        linhas.append("• Anterior: " + _metricas(treino))
        linhas.append("• Posterior (não usada para ajuste): " + _metricas(teste))
        if len(treino) >= 100 and len(teste) >= 50:
            # Um único deslocamento treinado exclusivamente no período anterior;
            # compara Brier no período posterior, sem alterar previsões.
            delta = sum(y-p for _,p,y,_ in treino)/len(treino)
            delta = max(-.15, min(.15, delta))
            b_original = sum((p-y)**2 for _,p,y,_ in teste)/len(teste)
            b_shadow = sum((max(0.,min(1.,p+delta))-y)**2 for _,p,y,_ in teste)/len(teste)
            linhas.append(f"• Simulação SHADOW: correção {delta*100:+.1f}pp (aprendida antes do corte)")
            linhas.append(f"• Brier posterior original {b_original:.3f} | simulado {b_shadow:.3f}")
            linhas.append("• Simulação ilustrativa, NÃO aprovada para produção.")
        else:
            linhas.append("• Amostra temporal insuficiente para comparar correção SHADOW.")
    else:
        linhas.append("⚠️ Dias distintos insuficientes para validação temporal.")
    linhas.append("🔒 Zero APIs, zero escrita, V1.2/V1.3/CLV intactos.")
    return "\n".join(linhas)
