"""Contrafactuais SHADOW de lambda em seleções históricas liquidadas.

Não altera o motor, previsões, ranking, odds ou snapshots.
"""
from datetime import date
from math import isfinite
from estatisticas_espn import EstatisticasESPN


def _num(v):
    try:
        n = float(v)
        return n if isfinite(n) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _brier(rows, metodo):
    return sum((metodo(r)-r["y"])**2 for r in rows)/len(rows)


def _prob(r, variante):
    lc, lf = r["lc"], r["lf"]
    if variante == "base":
        return r["p"]
    if variante == "shrink20":
        lc = .8*lc+.2*r["bc"]
        lf = .8*lf+.2*r["bf"]
    elif variante == "shrink40":
        lc = .6*lc+.4*r["bc"]
        lf = .6*lf+.4*r["bf"]
    elif variante == "delta15":
        total = lc+lf
        diferenca = (lc-lf)*.85
        lc,lf = (total+diferenca)/2,(total-diferenca)/2
    elif variante == "delta30":
        total = lc+lf
        diferenca = (lc-lf)*.70
        lc,lf = (total+diferenca)/2,(total-diferenca)/2
    return EstatisticasESPN._probabilidades(max(.01,lc),max(.01,lf))[r["mercado"]]


def relatorio_lambda_shadow(dados):
    snaps = dados.get("previsoes",[]) if isinstance(dados,dict) else []
    rows=[]
    n_sem=0
    for s in snaps:
        if not isinstance(s,dict) or s.get("mercado") not in ("Vitória Casa","Vitória Fora"):
            continue
        if s.get("resultado_binario") not in (0,1):
            continue
        p=_num(s.get("probabilidade"))
        if p is None or not 0<=p<=1:
            continue
        d=s.get("diagnostico_modelo")
        if not isinstance(d,dict):
            n_sem+=1
            continue
        lc,lf=_num(d.get("lambda_casa")),_num(d.get("lambda_fora"))
        bc,bf=_num(d.get("media_liga_casa")),_num(d.get("media_liga_fora"))
        if any(v is None or v<=0 for v in (lc,lf,bc,bf)):
            n_sem+=1
            continue
        try:
            dt=date.fromisoformat(str(s.get("data_jogo")))
        except (TypeError,ValueError):
            n_sem+=1
            continue
        rows.append({"data":dt,"mercado":s["mercado"],"p":p,"y":int(s["resultado_binario"]),
                     "lc":lc,"lf":lf,"bc":bc,"bf":bf})
    linhas=["🧪 LAMBDA SHADOW — CONTRAFACTUAIS",f"📚 Seleções elegíveis: {len(rows)} | sem dados: {n_sem}"]
    if len(set(r["data"] for r in rows))<4:
        return "\n".join(linhas+["⚠️ Dias insuficientes para validação temporal."])
    dias=sorted(set(r["data"] for r in rows))
    corte=dias[max(1,int(len(dias)*.7))]
    treino=[r for r in rows if r["data"]<corte]
    teste=[r for r in rows if r["data"]>=corte]
    linhas.append(f"🧭 Corte {corte.isoformat()} | treino n={len(treino)} | teste n={len(teste)}")
    variantes=("shrink20","shrink40","delta15","delta30")
    nomes={"shrink20":"20% médias liga","shrink40":"40% médias liga",
           "delta15":"diferença λ −15%","delta30":"diferença λ −30%"}
    for mercado in ("Vitória Casa","Vitória Fora"):
        a=[r for r in treino if r["mercado"]==mercado]
        b=[r for r in teste if r["mercado"]==mercado]
        linhas.append(f"🎯 {mercado}: treino {len(a)} | teste {len(b)}")
        if len(a)<30 or len(b)<20:
            linhas.append("• ⚠️ EXPLORATÓRIO: amostra insuficiente; sem escolha de variante.")
            for rotulo, grupo in (("treino",a),("teste",b)):
                if not grupo:
                    linhas.append(f"• {rotulo}: sem observações")
                    continue
                base=_brier(grupo,lambda r:r["p"])
                linhas.append(f"• {rotulo} | original Brier {base:.3f} | real {sum(r['y'] for r in grupo)/len(grupo)*100:.1f}% | previsto {sum(r['p'] for r in grupo)/len(grupo)*100:.1f}%")
                for v in variantes:
                    valor=_brier(grupo,lambda r:_prob(r,v))
                    linhas.append(f"  · {nomes[v]}: Brier {valor:.3f} | Δ {valor-base:+.3f}")
            continue
        # Selecionar variante exclusivamente no treino, incluindo base (sem mudança).
        candidatos=("base",)+variantes
        escolhido=min(candidatos,key=lambda v:_brier(a,lambda r:_prob(r,v)))
        original=_brier(b,lambda r:r["p"])
        testado=_brier(b,lambda r:_prob(r,escolhido))
        linhas.append(f"• Escolha no treino: {nomes.get(escolhido,'modelo original')}")
        linhas.append(f"• Brier teste: original {original:.3f} | SHADOW {testado:.3f}")
        for v in variantes:
            linhas.append(f"• {nomes[v]}: treino {_brier(a,lambda r:_prob(r,v)):.3f} | teste {_brier(b,lambda r:_prob(r,v)):.3f}")
    linhas.append("ℹ️ Apenas seleções históricas; viés de seleção e amostras pequenas. Não mede jogos não selecionados.")
    linhas.append("🔒 Zero APIs, zero escrita, nenhuma correção em produção ou nas coortes.")
    return "\n".join(linhas)
