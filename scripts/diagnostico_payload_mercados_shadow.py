"""Diagnostico conservador de mercados JA RECEBIDOS; zero HTTP, zero escrita.

Nao devolve odds ou IDs; nao e um matcher para uso comercial.
"""
import re
from collections import Counter

P = re.compile(r'^(Over|Under) ([0-9]+(?:\.[0-9]+)?) Golos$')
N = re.compile(r'(?<![\d.,])\d+(?:[.,]\d+)?(?![\d.,])')
ALLOWED = ('over under full time', 'total goals', 'goals over under', 'match goals')
BANNED = ('corner', 'team 1', 'team 2', 'first half', 'second half',
          'player', 'card', 'booking', 'shot', 'offside')


def inspect(mercado_modelo, payload):
    """Sumario SHADOW; status 'compativel' nao confirma preco executavel."""
    m = P.fullmatch(str(mercado_modelo or ''))
    if not m:
        return {'estado': 'mercado_modelo_nao_suportado'}
    mercados = payload.get('mercados') if isinstance(payload, dict) else None
    if not isinstance(mercados, list):
        return {'estado': 'catalogo_ausente'}
    lado, linha = m.group(1).lower(), float(m.group(2))
    contagens = Counter()
    for mercado in mercados:
        if not isinstance(mercado, dict):
            continue
        nome = str(mercado.get('name') or '').lower()
        periodo = re.sub(r'[^a-z]', '', str(mercado.get('period') or '').lower())
        if periodo not in ('fulltime', 'ft', 'match', 'regulartime'):
            contagens['periodo_ausente_ou_divergente'] += 1
            continue
        if any(x in nome for x in BANNED):
            contagens['mercado_de_outra_familia'] += 1
            continue
        if not any(x in nome for x in ALLOWED):
            contagens['designacao_desconhecida'] += 1
            continue
        for odd in mercado.get('odds') or []:
            if not isinstance(odd, dict):
                continue
            escolha = str(odd.get('seleção') or '').lower()
            ref = str(odd.get('ref') or '').lower()
            if not re.search(r'\b' + lado + r'\b', escolha + ' ' + ref):
                contagens['selecao_lado_divergente'] += 1
                continue
            valores = N.findall(escolha)
            if not valores and re.search(r'\b(over|under)\b', ref):
                valores = N.findall(ref)
            try:
                handicap = (float(mercado['handicap']) if mercado.get('handicap') is not None
                            else None)
            except (ValueError, TypeError):
                contagens['linha_invalida'] += 1
                continue
            if handicap is not None and abs(handicap - linha) > 1e-9:
                contagens['linha_divergente'] += 1
                continue
            if valores and any(abs(float(x.replace(',', '.')) - linha) > 1e-9 for x in valores):
                contagens['linha_textual_contraditoria'] += 1
                continue
            if handicap is None and not valores:
                nome_numeros = N.findall(nome)
                if not nome_numeros:
                    contagens['linha_nao_comprovada'] += 1
                    continue
                if any(abs(float(x.replace(',', '.')) - linha) > 1e-9 for x in nome_numeros):
                    contagens['linha_divergente'] += 1
                    continue
            try:
                cotacao = float(odd.get('odd'))
            except (TypeError, ValueError, OverflowError):
                contagens['odd_nao_numerica'] += 1
                continue
            if not 1 < cotacao < 1000:
                contagens['odd_fora_de_intervalo'] += 1
                continue
            contagens['possivel_correspondencia'] += 1
    n = contagens['possivel_correspondencia']
    estado = ('sem_correspondencia_segura' if n == 0 else
              'um_candidato_shadow' if n == 1 else 'ambiguo_multiplos_candidatos')
    return {'estado': estado, 'mercados_recebidos': len(mercados),
            'contagens': dict(contagens)}
