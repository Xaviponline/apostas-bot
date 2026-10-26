"""Diagnostico SHADOW de mercados ja recebidos em memoria.

Nao efetua HTTP, nao utiliza credenciais, nao grava snapshots, nem altera regras V1.3.
Apenas gera diagnostico agregado; nao guarda IDs/cotacoes de clientes.
Sera uma alternativa em testes, nao um patch aprovado para producao.
"""
import math
import re
import unicodedata
from collections import Counter


def normalize(s):
    s=''.join(c for c in unicodedata.normalize('NFKD',str(s or '').lower()) if not unicodedata.combining(c))
    return re.sub(r'\s+',' ',s).strip()


def numeric_lines(s):
    """Extrai linhas como 2.5/12.5 sem tratar 2.5 como substring de 12.5."""
    text=normalize(s)
    return {float(t.replace(',','.')) for t in re.findall(r'(?<![\d.])\b\d+(?:[.,]\d+)?\b(?![\d.])',text)}


def read_handicap(v):
    if v is None or isinstance(v,bool): return None
    try:f=float(v)
    except (TypeError,ValueError,OverflowError):return None
    return f if math.isfinite(f) else None


def expected(target):
    m=re.fullmatch(r'(Over|Under) (\d+(?:\.\d+)?) Golos',target)
    if m:return 'totals',m.group(1).lower(),float(m.group(2))
    if target=='Ambas Marcam':return 'btts','yes',None
    if target=='Vitória Casa':return '1x2','home',None
    if target=='Vitória Fora':return '1x2','away',None
    return None,None,None


def test_item(target, market, selection):
    """(aceite, motivo) estrito; nunca decide so pela proximidade textual."""
    kind,side,wanted=expected(target)
    if kind is None:return False,'mercado_modelo_nao_suportado'
    if not isinstance(market,dict) or not isinstance(selection,dict):return False,'dados_invalidos'
    if bool(market.get('playerProp')):return False,'mercado_de_jogador'
    period=normalize(market.get('period')).replace(' ','')
    if period not in ('fulltime','ft','match','regulartime'):
        return False,'periodo_ausente_ou_incompativel'
    name=normalize(market.get('name'))
    if not name:return False,'nome_mercado_ausente'
    sel=normalize(selection.get('seleção'))
    ref=normalize(selection.get('ref'))
    if kind=='totals':
        forbidden=('corner','team 1','team 2','first half','second half','player','card','booking','shot','offside')
        if any(x in name for x in forbidden):return False,'categoria_mercado_incompativel'
        if not any(x in name for x in ('over under full time','total goals','goals over under','match goals')):
            return False,'nome_mercado_incompativel'
        if side not in re.findall(r'\b(?:over|under)\b',sel+' '+ref):return False,'lado_incompativel'
        handicap=read_handicap(market.get('handicap'))
        extracted_sel=numeric_lines(sel)
        # Outcome ID numeric (ref) nao representa uma linha, exceto quando ref
        # e um texto estruturado do tipo '2.5/under' ou 'under 2.5'.
        if re.search(r'(?i)\b(over|under)\b',ref) and not ref.isdecimal():
            extracted_sel |= numeric_lines(ref)
        extracted_name=numeric_lines(name)
        if handicap is not None:
            if abs(handicap-wanted)>1e-9:return False,'handicap_incompativel'
            if extracted_sel and extracted_sel!={wanted}:return False,'selecao_contradiz_handicap'
            if extracted_name and extracted_name!={wanted}:return False,'nome_contradiz_handicap'
            return True,'compativel'
        lines=extracted_sel|extracted_name
        if not lines:return False,'linha_ausente'
        if lines!={wanted}:return False,'linha_textual_diferente_ou_ambigua'
        return True,'compativel'
    if kind=='btts':
        if not any(s in name for s in ('both teams to score','both teams score','btts')):
            return False,'nome_mercado_incompativel'
        if any(s in name for s in ('corner','first half','second half','team 1','team 2')):
            return False,'categoria_mercado_incompativel'
        return (True,'compativel') if sel in ('yes','sim') or ref in ('yes','sim') else (False,'selecao_incompativel')
    if any(s in name for s in ('corner','handicap','first half','second half')):
        return False,'categoria_mercado_incompativel'
    if not any(s in name for s in ('full time result','match result','1x2')):
        return False,'nome_mercado_incompativel'
    allowed=('1','home') if side=='home' else ('2','away')
    return (True,'compativel') if sel in allowed or ref in allowed else (False,'selecao_incompativel')


def diagnose_payload(payload,target):
    """Contagens agregadas, sem publicar cotacoes nem selecoes completas."""
    markets=payload.get('mercados') if isinstance(payload,dict) else None
    if not isinstance(markets,list):return {'estado':'payload_sem_lista_mercados','mercados_recebidos':0,'itens_avaliados':0,'motivos':{}}
    reasons=Counter(); valid=0; n=0
    for m in markets:
        if not isinstance(m,dict):continue
        for item in m.get('odds') or []:
            if not isinstance(item,dict):continue
            n+=1; ok,why=test_item(target,m,item)
            reasons[why]+=1
            if ok:valid+=1
    return {
        'estado':'associacao_unica' if valid==1 else 'associacao_ambigua' if valid>1 else 'sem_correspondencia_segura',
        'mercados_recebidos':len(markets),'itens_avaliados':n,
        'itens_compativeis':valid,'motivos':dict(sorted(reasons.items())),
    }
