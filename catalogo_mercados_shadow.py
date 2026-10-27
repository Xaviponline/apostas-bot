"""Diagnostico passivo do catalogo OddsPapi ja recebido; sem HTTP nem persistencia."""
from collections import Counter
from math import isfinite

def analisar_catalogo(catalogo, odds_normalizadas):
    if not isinstance(catalogo, dict) or not isinstance(odds_normalizadas, dict):
        return {'estado':'dados_insuficientes','motivos':{}}
    mercados=odds_normalizadas.get('mercados')
    if not isinstance(mercados,list):
        return {'estado':'mercados_ausentes','motivos':{}}
    motivos=Counter()
    for m in mercados:
        if not isinstance(m,dict):
            motivos['mercado_malformado']+=1;continue
        mid=str(m.get('id') or '')
        meta=catalogo.get(mid)
        if not isinstance(meta,dict):
            motivos['id_ausente_no_catalogo']+=1;continue
        if not str(meta.get('name') or '').strip() or str(meta.get('name')).lower().startswith('market '):
            motivos['nome_sem_metadados']+=1
        if not str(meta.get('period') or '').strip():
            motivos['periodo_nao_informado']+=1
        handicap=meta.get('handicap')
        if isinstance(handicap,bool):
            motivos['handicap_invalido']+=1
        elif handicap is not None:
            try:
                if not isfinite(float(handicap)):motivos['handicap_invalido']+=1
            except (ValueError,TypeError,OverflowError):motivos['handicap_invalido']+=1
        outcomes=meta.get('outcomes')
        if not isinstance(outcomes,dict):
            motivos['outcomes_sem_catalogo']+=1;continue
        for odd in m.get('odds') or []:
            if not isinstance(odd,dict):continue
            ref=str(odd.get('ref') or '')
            sel=str(odd.get('seleção') or '')
            if sel.isdecimal() and sel not in set(str(v) for v in outcomes.values()):
                motivos['outcome_nome_numerico_nao_resolvido']+=1
    return {'estado':'avaliado_sem_prova_de_disponibilidade','mercados_avaliados':len(mercados),'motivos':dict(sorted(motivos.items()))}
