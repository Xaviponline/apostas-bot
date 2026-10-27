"""Auditoria por etapas, SOMENTE SHADOW. Sem rede, escrita, chaves ou apostas.

Usa apenas payload normalizado ja recebido (OddsBetano._normalizar_odds_papi),
fixture da mesma resposta de descoberta e selecao do modelo. Nao aceita
cotacoes; distingue observacao tecnica de disponibilidade na Betano.
"""
from collections import Counter
from datetime import datetime, timezone
from math import isfinite
import re
import unicodedata

from mercados_diagnostico_shadow import test_item
from odds_diagnostico_passivo_shadow import diagnosticar_payload

LIMITE_MINUTOS = 90
FASE_MOTIVO = {
    'nome_mercado_ausente': 'catalogo',
    'mercado_de_jogador': 'familia',
    'nome_mercado_incompativel': 'familia',
    'categoria_mercado_incompativel': 'familia',
    'periodo_ausente_ou_incompativel': 'periodo',
    'handicap_incompativel': 'linha',
    'selecao_contradiz_handicap': 'linha',
    'nome_contradiz_handicap': 'linha',
    'linha_ausente': 'linha',
    'linha_textual_diferente_ou_ambigua': 'linha',
    'lado_incompativel': 'selecao',
    'selecao_incompativel': 'selecao',
    'preco_ausente_ou_invalido': 'preco',
    'selecao_inativa': 'preco',
    'mercado_inativo': 'preco',
    'captura_sem_hora_comprovada': 'tempo',
    'captura_pos_kickoff': 'tempo',
    'ultima_alteracao_sem_data': 'tempo',
    'ultima_alteracao_futura': 'tempo',
    'ultima_alteracao_ha_mais_6h': 'tempo',
    'ultima_alteracao_recente_nao_prova_disponibilidade': 'tempo',
}


def _instante(valor):
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        if isinstance(valor, (int, float)):
            return datetime.fromtimestamp(float(valor), timezone.utc) if isfinite(float(valor)) else None
        data = datetime.fromisoformat(str(valor).strip().replace('Z', '+00:00'))
        return data.astimezone(timezone.utc) if data.tzinfo else None
    except (ValueError, TypeError, OSError, OverflowError):
        return None


def _nome(valor):
    normal = unicodedata.normalize('NFKD', str(valor or '').casefold())
    normal = ''.join(c for c in normal if not unicodedata.combining(c))
    for antiga, nova in (('ø', 'o'), ('æ', 'ae'), ('œ', 'oe'), ('ł', 'l')):
        normal = normal.replace(antiga, nova)
    return ' '.join(re.findall(r'[a-z0-9]+', normal))


def _categoria(nome):
    n = _nome(nome)
    idade = re.findall(r'\b(?:u|sub)\s*(?:17|18|19|20|21|23)\b', n)
    return bool(idade), bool(re.search(r'\b(?:women|feminino|feminina|w)\b', n)), bool(re.search(r'\b(?:reserves|reserve|b|ii)\b', n))


def verificar_evento(modelo, fixture, payload, capturada_em=None):
    """Exige a mesma identidade OddsPapi no fixture e na resposta de odds.

    Event_id do ESPN/modelo NAO e comparavel ao fixture ID da OddsPapi.
    Liga divergente e apenas aviso porque os nomes variam entre fornecedores.
    """
    if not all(isinstance(x, dict) for x in (modelo, fixture, payload)):
        return 'evento_sem_contexto', []
    fi = str(fixture.get('id') or '').strip()
    pi = str(payload.get('id') or '').strip()
    if not fi or not pi:
        return 'fixture_id_fonte_nao_comprovado', []
    if fi != pi:
        return 'fixture_id_fonte_divergente', []
    for chave in ('casa', 'fora'):
        a, b, c = (_nome(obj.get(chave)) for obj in (modelo, fixture, payload))
        if not a or not b or not c:
            return 'equipas_sem_nomes_completos', []
        if _categoria(modelo[chave]) != _categoria(fixture[chave]) or _categoria(fixture[chave]) != _categoria(payload[chave]):
            return 'categoria_equipa_incompativel', []
        if len({a, b, c}) != 1:
            return 'nome_equipa_nao_confirmado', []
    inicio_m = _instante(modelo.get('timestamp_jogo') or modelo.get('timestamp'))
    inicio_f = _instante(fixture.get('data'))
    if inicio_m is None or inicio_f is None:
        return 'inicio_sem_hora_comprovada', []
    if abs((inicio_f - inicio_m).total_seconds()) > LIMITE_MINUTOS * 60:
        return 'hora_fixture_incompativel', []
    capturada = _instante(capturada_em)
    if capturada is None:
        return 'captura_sem_hora_comprovada', []
    if capturada >= inicio_m or capturada >= inicio_f:
        return 'captura_pos_kickoff', []
    avisos = []
    a, b = _nome(fixture.get('liga')), _nome(payload.get('liga'))
    if a and b and a != b:
        avisos.append('nome_competicao_por_confirmar')
    return 'evento_identificado_com_hora_prejogo', avisos


def diagnosticar_etapas(modelo, fixture, payload, capturada_em):
    """Contagens por fase sem IDs, odds ou nomes. Nao altera o payload recebido."""
    estado_evento, avisos = verificar_evento(modelo, fixture, payload, capturada_em)
    alvo = modelo.get('mercado') if isinstance(modelo, dict) else None
    inicio = modelo.get('timestamp_jogo') if isinstance(modelo, dict) else None
    base = diagnosticar_payload(payload, alvo, capturada_em, inicio)
    motivos = Counter(base.get('contagens', {}))
    fases = Counter()
    for motivo, quantidade in motivos.items():
        fases[FASE_MOTIVO.get(motivo, 'dados_incompletos')] += quantidade
    mercados = payload.get('mercados') if isinstance(payload, dict) else None
    if isinstance(mercados, list):
        for m in mercados:
            if isinstance(m, dict) and re.fullmatch(r'market\s+\d+',str(m.get('name') or ''),re.I):
                fases['catalogo'] += 1
                motivos['catalogo_id_sem_metadados'] += 1
    if base['estado'] in {'lista_mercados_ausente_ou_excessiva', 'payload_invalido'}:
        fases['catalogo'] += 1
        motivos[base['estado']] += 1
    if base['estado'] == 'bookmaker_explicitamente_inativo':
        fases['bookmaker'] += 1
        motivos['bookmaker_explicitamente_inativo'] += 1
    n = int(base.get('precos_validos_observados') or 0)
    if estado_evento != 'evento_identificado_com_hora_prejogo':
        etapa = 'evento'
        resultado = 'evento_nao_comprovado'
    elif base['estado'] == 'bookmaker_explicitamente_inativo':
        etapa = 'bookmaker'
        resultado = 'bookmaker_indisponivel_no_payload'
    elif n > 1:
        etapa = 'ambiguidade'
        resultado = 'multiplos_precos_observados'
    elif n == 1:
        etapa = ('tempo' if any(m in motivos for m in (
            'captura_pos_kickoff', 'ultima_alteracao_futura',
            'ultima_alteracao_ha_mais_6h', 'captura_sem_hora_comprovada'
        )) else 'execucao_nao_verificada')
        resultado = 'um_preco_observado_nao_executabilidade'
    else:
        exclusoes = [fase for fase in ('preco', 'selecao', 'linha', 'periodo', 'familia', 'catalogo', 'dados_incompletos') if fases.get(fase)]
        etapa = (exclusoes[0] if len(exclusoes) == 1 else 'multiplas_exclusoes'
                 if exclusoes else 'catalogo_ou_lista_vazia')
        resultado = 'sem_correspondencia_confirmada'
    return {
        'resultado': resultado,
        'etapa_a_investigar': etapa,
        'evento': estado_evento,
        'avisos': avisos,
        'mercados_recebidos': int(base.get('mercados_recebidos') or 0),
        'selecoes_estruturalmente_compativeis': int(base.get('selecoes_estruturalmente_compativeis') or 0),
        'precos_observados': n,
        'fases': dict(sorted(fases.items())),
        'motivos': dict(sorted(motivos.items())),
    }


MOTIVOS_HISTORICOS = {
    'evento_nao_encontrado': 'evento',
    'evento_ambiguo': 'evento',
    'horario_recuperacao_nao_validado': 'evento',
    'odds_payload_evento_divergente': 'evento',
    'fixture_omitido_no_lote': 'lote',
    'betano_sem_odds_no_evento': 'bookmaker',
    'mercado_nao_disponivel': 'mercado_ou_catalogo_indeterminado',
    'linha_ou_selecao_nao_disponivel': 'linha_ou_selecao_indeterminada',
    'fixture_u19_confirmado_tff': 'seguranca_categoria',
}


def resumir_rastreio_historico(registos):
    """Resumir evidencias ja persistidas; sem inferir causa sem payload bruto."""
    resumo = Counter()
    for r in registos:
        if not isinstance(r, dict):
            resumo['registo_invalido'] += 1
            continue
        motivo = str(r.get('diagnostico') or '').strip()
        resumo[MOTIVOS_HISTORICOS.get(motivo, 'sem_motivo_detalhado' if not motivo else 'outro_motivo')] += 1
    return dict(sorted(resumo.items()))
