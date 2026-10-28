"""Diagnóstico PASSIVO de linhas Over/Under presentes nas respostas já recebidas.

Não altera associação de odds, não consulta APIs e não guarda preços. O handicap
no catálogo é uma pista observável, não uma garantia de oferta na Betano.
"""
import math
import re

_ALVO = re.compile(r"^(Over|Under) ([0-9]+(?:\.[0-9]+)?) Golos$")


def _handicap(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        n = float(valor)
    except (ValueError, TypeError, OverflowError):
        return None
    return n if math.isfinite(n) and 0 <= n <= 20 else None


def _lado_outcome(odd):
    texto = " ".join([str(odd.get("seleção") or ""), str(odd.get("ref") or "")]).casefold()
    encontrados = set(re.findall(r"(?<![a-z])(?:over|under)(?![a-z])", texto))
    return next(iter(encontrados)) if len(encontrados) == 1 else None


def resumo_linha_shadow(mercados, mercado_modelo, compativel, odd_valida):
    """Conta apenas provas observadas nos mercados compatíveis já normalizados.

    As seleções sem handicap são inconclusivas mesmo que contenham 'Over' ou
    'Under'; este diagnóstico não serve para autorizar associações de odds.
    """
    alvo = _ALVO.fullmatch(str(mercado_modelo or ""))
    if not alvo:
        return None
    lado, linha = alvo.group(1).casefold(), float(alvo.group(2))
    compativeis = [
        m for m in (mercados or [])
        if isinstance(m, dict) and compativel(mercado_modelo, m)
    ]
    linhas = set()
    contagem = {
        "mercados_linha_alvo": 0,
        "mercados_outra_linha": 0,
        "mercados_sem_handicap": 0,
        "lado_alvo_linha_alvo": 0,
        "lado_alvo_outra_linha": 0,
        "lado_alvo_sem_handicap": 0,
        "lado_desconhecido_linha_alvo": 0,
    }
    for mercado in compativeis:
        handicap = _handicap(mercado.get("handicap"))
        if handicap is None:
            classe = "sem_handicap"
        elif abs(handicap - linha) < 1e-9:
            classe = "linha_alvo"
            linhas.add(handicap)
        else:
            classe = "outra_linha"
            linhas.add(handicap)
        contagem["mercados_" + classe] += 1
        for odd in mercado.get("odds") or []:
            if not isinstance(odd, dict) or odd_valida(odd.get("odd")) is None:
                continue
            lado_observado = _lado_outcome(odd)
            if lado_observado == lado:
                contagem["lado_alvo_" + classe] += 1
            elif lado_observado is None and classe == "linha_alvo":
                contagem["lado_desconhecido_linha_alvo"] += 1
    return {
        "alvo": linha,
        "linhas_handicap": sorted(linhas)[:8],
        **{k: min(v, 999) for k, v in contagem.items()},
    }
