"""Classificador SHADOW de payloads de odds ja obtidos (sem HTTP/IO).

Apenas produz motivos agregados, sem divulgar IDs ou precos. Uma ultima
alteracao recente NAO equivale a disponibilidade atual na Betano.
Esta camada nao fornece odds ao motor comercial.
"""
from collections import Counter
from datetime import datetime, timezone
from math import isfinite

from mercados_diagnostico_shadow import test_item

MAX_MERCADOS = 50000


def _instante(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), timezone.utc) if isfinite(float(value)) else None
        dt = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _preco_valido(valor):
    if valor is None or isinstance(valor, bool):
        return False
    try:
        n = float(valor)
    except (TypeError, ValueError, OverflowError):
        return False
    return isfinite(n) and 1.0 < n < 1000.0


def _estado_tempo(market, item, capturada, inicio):
    if capturada is None:
        return 'captura_sem_hora_comprovada'
    if inicio is not None and capturada >= inicio:
        return 'captura_pos_kickoff'
    alteracao = _instante(item.get('bookmakerChangedAt') or item.get('changedAt') or market.get('updatedAt'))
    if alteracao is None:
        return 'ultima_alteracao_sem_data'
    idade = (capturada - alteracao).total_seconds()
    if idade < -300:
        return 'ultima_alteracao_futura'
    if idade > 6 * 3600:
        return 'ultima_alteracao_ha_mais_6h'
    return 'ultima_alteracao_recente_nao_prova_disponibilidade'


def diagnosticar_payload(payload, mercado_modelo, capturada_em=None, inicio_jogo=None):
    """Resume compatibilidade estrutural, validade do preco e idade observada.

    Classificacao passiva: so mede campos presentes. Nao associa um evento,
    nao verifica se a Betano aceita aposta e nao devolve qualquer cotacao.
    """
    if not isinstance(payload, dict):
        return {'estado': 'payload_invalido', 'contagens': {}}
    if payload.get('bookmaker_disponivel') is False:
        return {'estado': 'bookmaker_explicitamente_inativo', 'contagens': {}}
    mercados = payload.get('mercados')
    if not isinstance(mercados, list) or len(mercados) > MAX_MERCADOS:
        return {'estado': 'lista_mercados_ausente_ou_excessiva', 'contagens': {}}

    capturada = _instante(capturada_em)
    inicio = _instante(inicio_jogo)
    contagens = Counter()
    conformes = 0
    precos = 0
    for mercado in mercados:
        if not isinstance(mercado, dict):
            contagens['mercado_malformado'] += 1
            continue
        if mercado.get('marketActive') is False:
            contagens['mercado_inativo'] += 1
            continue
        itens = mercado.get('odds')
        if not isinstance(itens, list):
            contagens['selecao_sem_lista'] += 1
            continue
        for item in itens:
            if not isinstance(item, dict):
                contagens['selecao_malformada'] += 1
                continue
            if item.get('active') is False:
                contagens['selecao_inativa'] += 1
                continue
            aceite, motivo = test_item(mercado_modelo, mercado, item)
            if not aceite:
                contagens[motivo] += 1
                continue
            conformes += 1
            if not _preco_valido(item.get('odd')):
                contagens['preco_ausente_ou_invalido'] += 1
                continue
            precos += 1
            contagens[_estado_tempo(mercado, item, capturada, inicio)] += 1
    if precos > 1:
        estado = 'multiplas_cotacoes_estruturalmente_compativeis'
    elif precos == 1:
        estado = 'uma_cotacao_observada_sem_prova_de_execucao'
    elif conformes:
        estado = 'estrutura_compativel_mas_sem_preco_valido'
    else:
        estado = 'sem_correspondencia_estrutural_segura'
    return {
        'estado': estado,
        'mercados_recebidos': len(mercados),
        'selecoes_estruturalmente_compativeis': conformes,
        'precos_validos_observados': precos,
        'contagens': dict(sorted(contagens.items())),
    }
