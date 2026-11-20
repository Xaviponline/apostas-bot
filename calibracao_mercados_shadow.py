"""Validação por mercado com corte temporal comum e intervalos de incerteza.

Apenas leitura. Sem alterar previsões nem odds.
"""
from collections import defaultdict
from math import sqrt
from calibracao_shadow import _float


def _resumo(rows):
    n = len(rows)
    if not n:
        return "n=0"
    previsto = sum(p for p, y in rows) / n
    real = sum(y for p, y in rows) / n
    brier = sum((p-y)**2 for p,y in rows)/n
    # Intervalo Wilson aproximado para a taxa observada, z=1.96.
    z = 1.96
    centro = (real+z*z/(2*n))/(1+z*z/n)
    margem = z*sqrt(real*(1-real)/n+z*z/(4*n*n))/(1+z*z/n)
    return (f"n={n} | prev {previsto*100:.1f}% | real {real*100:.1f}% "
            f"(IC95% {max(0,centro-margem)*100:.1f}–{min(1,centro+margem)*100:.1f}%) "
            f"| Brier {brier:.3f}")


def relatorio_calibracao_mercados(dados):
    snapshots = dados.get("previsoes", []) if isinstance(dados, dict) else []
    por_dia = defaultdict(list)
    for s in snapshots:
        if not isinstance(s, dict) or s.get("resultado_binario") not in (0,1):
            continue
        p = _float(s.get("probabilidade"))
        data = str(s.get("data_jogo") or "")
        if p is None or not 0 <= p <= 1 or len(data) != 10:
            continue
        try:
            from datetime import date
            date.fromisoformat(data)
        except ValueError:
            continue
        por_dia[data].append((str(s.get("mercado") or "?"), p, int(s["resultado_binario"])))
    dias = sorted(por_dia)
    linhas = ["🧪 MERCADOS SHADOW — VALIDAÇÃO TEMPORAL", f"📚 Dias distintos: {len(dias)}"]
    if len(dias) < 4:
        return "\n".join(linhas+["⚠️ Dias insuficientes. Zero alterações."])
    corte = dias[max(1,int(len(dias)*.7))]
    linhas.append(f"🧭 Corte comum: {corte} | treino antes, teste a partir desta data")
    mercados = sorted({m for d in dias for m,_,_ in por_dia[d]})
    for mercado in mercados:
        anterior = [(p,y) for d in dias if d < corte for m,p,y in por_dia[d] if m == mercado]
        posterior = [(p,y) for d in dias if d >= corte for m,p,y in por_dia[d] if m == mercado]
        linhas.append(f"🎯 {mercado}")
        linhas.append("• Antes: "+_resumo(anterior))
        linhas.append("• Depois: "+_resumo(posterior))
        if len(anterior) < 40 or len(posterior) < 25:
            linhas.append("• Sem simulação: amostra insuficiente por mercado.")
            continue
        delta = max(-.15,min(.15,sum(y-p for p,y in anterior)/len(anterior)))
        original = sum((p-y)**2 for p,y in posterior)/len(posterior)
        ajustado = sum((max(0,min(1,p+delta))-y)**2 for p,y in posterior)/len(posterior)
        linhas.append(f"• Ajuste ilustrativo {delta*100:+.1f}pp | Brier teste {original:.3f} → {ajustado:.3f}")
        linhas.append("• NÃO aplicar automaticamente.")
    linhas.append("ℹ️ IC95% apenas da taxa de acerto; não corrige dependência entre seleções do mesmo jogo.")
    linhas.append("🔒 Sem APIs, sem escrita, sem mexer em V1.2/V1.3/CLV.")
    return "\n".join(linhas)
