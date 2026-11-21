"""Relatório prospetivo 1X2: apenas resultados finais já guardados no histórico.

Não consulta APIs, não altera registos, não inventa resultados para jogos
não selecionados. Os jogos sem marcador confirmado permanecem pendentes.
"""
import json
from pathlib import Path

MERCADOS=("Vitória Casa","Empate","Vitória Fora")


def relatorio_prospectivo(caminho, previsoes):
    path=Path(caminho)
    linhas=["🧪 LAMBDA PROSPETIVO — 1X2",
            "🔒 Apenas leitura; zero APIs, zero alterações às previsões."]
    if not path.exists():
        return "\n".join(linhas+["📭 Sem registos SHADOW guardados neste volume."])
    registos=[]
    for linha in path.read_text(encoding="utf-8").splitlines():
        try:
            r=json.loads(linha)
            if r.get("versao")==1 and all(k in r.get("original_1x2",{}) and k in r.get("alternativa_1x2",{}) for k in MERCADOS):
                registos.append(r)
        except (ValueError,TypeError):
            continue
    # Apenas marcadores completos e IDs exatos, sem inferir por nome ou data.
    resultados={}
    ambiguos=set()
    for p in (previsoes or {}).get("previsoes",[]):
        try:
            if p.get("resultado_binario") not in (0,1):
                continue
            gc,gf=int(p["golos_casa"]),int(p["golos_fora"])
            ident=int(p["event_id"])
            if gc<0 or gf<0: continue
            if ident in resultados and resultados[ident]!=(gc,gf):
                ambiguos.add(ident)
            else: resultados[ident]=(gc,gf)
        except (TypeError,ValueError,KeyError):
            continue
    valores=[]
    for r in registos:
        try:
            ident=int(r["jogo"]["id"])
            if ident in ambiguos or ident not in resultados:continue
            gc,gf=resultados[ident]
            y=(1.,0.,0.) if gc>gf else ((0.,1.,0.) if gc==gf else (0.,0.,1.))
            a=[float(r["original_1x2"][k]) for k in MERCADOS]
            b=[float(r["alternativa_1x2"][k]) for k in MERCADOS]
            if any(not 0<=v<=1 for v in a+b):continue
            if abs(sum(a)-1)>.02 or abs(sum(b)-1)>.02:continue
            valores.append((sum((v-t)**2 for v,t in zip(a,y))/3,
                            sum((v-t)**2 for v,t in zip(b,y))/3))
        except (KeyError,TypeError,ValueError):
            continue
    linhas.append(f"📚 Registos: {len(registos)} | com resultado oficial associado: {len(valores)} | sem resultado: {len(registos)-len(valores)}")
    if valores:
        a=sum(v[0] for v in valores)/len(valores)
        b=sum(v[1] for v in valores)/len(valores)
        linhas.extend([f"📊 Brier 1X2 médio (3 classes): original {a:.4f} | 40% médias liga {b:.4f} | Δ {b-a:+.4f}",
                       "⚠️ Subconjunto com previsões oficiais liquidadas; não representa todos os jogos analisados."])
    else:
        linhas.append("⏳ Ainda sem resultados oficiais associados; aguardar liquidação.")
    linhas.append("ℹ️ Não promover variantes com esta amostra; resultados não selecionados ainda não estão disponíveis.")
    return "\n".join(linhas)
