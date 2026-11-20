"""Diagnostico de vitorias: segmentacao de amostra, golos e ligas; read-only."""
from collections import defaultdict
from calibracao_shadow import _float


def _resumo(rows):
    n = len(rows)
    if not n:
        return "n=0"
    p = sum(x[0] for x in rows)/n
    y = sum(x[1] for x in rows)/n
    b = sum((x[0]-x[1])**2 for x in rows)/n
    return f"n={n} | prev {100*p:.1f}% | real {100*y:.1f}% | desvio {100*(p-y):+.1f}pp | Brier {b:.3f}"


def relatorio_vitorias_shadow(dados):
    snaps = dados.get("previsoes", []) if isinstance(dados, dict) else []
    rows = []
    sem_diag = 0
    for s in snaps:
        if not isinstance(s, dict) or s.get("mercado") not in ("Vitória Casa","Vitória Fora"):
            continue
        if s.get("resultado_binario") not in (0,1):
            continue
        p = _float(s.get("probabilidade"))
        if p is None or not 0 <= p <= 1:
            continue
        d = s.get("diagnostico_modelo")
        if not isinstance(d, dict):
            sem_diag += 1
            d = {}
        rows.append((s["mercado"], p, int(s["resultado_binario"]), s.get("liga") or "?", d))
    linhas = ["🔬 VITÓRIAS SHADOW — DIAGNÓSTICO",f"📚 Liquidadas: {len(rows)} | sem diagnóstico: {sem_diag}"]
    if not rows:
        return "\n".join(linhas+["Sem seleções suficientes. Zero alterações."])
    for mercado in ("Vitória Casa","Vitória Fora"):
        grupo = [r for r in rows if r[0] == mercado]
        linhas.append(f"🎯 {mercado}: {_resumo([(r[1],r[2]) for r in grupo])}")
        if not grupo:
            continue
        por_liga = defaultdict(list)
        por_amostra = defaultdict(list)
        por_delta = defaultdict(list)
        for _,p,y,liga,d in grupo:
            par = (p,y)
            por_liga[str(liga)[:65]].append(par)
            a,b = _float(d.get("amostra_casa")), _float(d.get("amostra_fora"))
            if a is not None and b is not None:
                por_amostra["pequena (<6)" if min(a,b)<6 else ">=6"].append(par)
            lc,lf = _float(d.get("lambda_casa")),_float(d.get("lambda_fora"))
            if lc is not None and lf is not None:
                vantagem = (lc-lf) if mercado == "Vitória Casa" else (lf-lc)
                faixa = "vantagem <0.5" if vantagem<.5 else ("0.5–1.5" if vantagem<1.5 else ">=1.5")
                por_delta[faixa].append(par)
        linhas.append("📚 Amostra mínima por equipa:")
        for k,v in sorted(por_amostra.items()):
            linhas.append(f"• {k}: {_resumo(v)}")
        linhas.append(f"• Sem amostra guardada: {len(grupo)-sum(map(len,por_amostra.values()))}")
        linhas.append("⚽ Vantagem de golos esperados (equipa escolhida):")
        for k,v in sorted(por_delta.items()):
            linhas.append(f"• {k}: {_resumo(v)}")
        linhas.append(f"• Sem lambdas: {len(grupo)-sum(map(len,por_delta.values()))}")
        linhas.append("🗺️ Ligas (mínimo 5 previsões):")
        ligas = [(k,v) for k,v in por_liga.items() if len(v)>=5]
        for k,v in sorted(ligas,key=lambda x:(-len(x[1]),x[0]))[:10]:
            linhas.append(f"• {k}: {_resumo(v)}")
        linhas.append(f"• Outras ligas/amostra <5: {sum(len(v) for v in por_liga.values() if len(v)<5)}")
    linhas.append("ℹ️ Segmentos descritivos; amostras pequenas e seleções correlacionadas. Não validar mudanças por estes resultados isoladamente.")
    linhas.append("🔒 Zero APIs, zero escrita, V1.2/V1.3/CLV intactos.")
    return "\n".join(linhas)
