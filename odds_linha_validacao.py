"""Validação conservadora de linha Over/Under, sem rede nem efeitos colaterais.

Usar apenas depois de validar o tipo/período do mercado e o fixture.
Contradições de handicap, identificação de seleção ou linha textual rejeitam a odd.
"""
import math
import re

_TARGET = re.compile(r"^(Over|Under) (\d+(?:\.\d+)?) Golos$")
_SIDE = re.compile(r"\b(over|under)\b", re.I)
_DECIMAL = re.compile(r"(?<![\d.])(\d{1,2}[.,]\d+)(?![\d.])")
_EXPLICIT_INTEGER = re.compile(r"\b(?:line|linha|handicap)\s*[:=]?\s*(\d{1,2})\b", re.I)

def _lines(value):
    s = str(value or "")
    result = {float(v.replace(",", ".")) for v in _DECIMAL.findall(s)}
    result.update(float(v) for v in _EXPLICIT_INTEGER.findall(s))
    return {x for x in result if math.isfinite(x)}

def validar_linha_totais(alvo, mercado, selecao):
    """Retorna (válido, motivo); chamar depois de validar identidade e tipo de mercado."""
    match = _TARGET.fullmatch(str(alvo))
    if not match or not isinstance(mercado, dict) or not isinstance(selecao, dict):
        return False, "dados_invalidos"
    wanted, side = float(match.group(2)), match.group(1).lower()
    selection = str(selecao.get("seleção") or "")
    ref = str(selecao.get("ref") or "")
    selection_sides = {s.lower() for s in _SIDE.findall(selection)}
    ref_sides = {s.lower() for s in _SIDE.findall(ref)}
    if (selection_sides and selection_sides != {side}) or (ref_sides and ref_sides != {side}):
        return False, "lado_contraditorio"
    if not selection_sides and not ref_sides:
        return False, "lado_incompativel"
    handicap = mercado.get("handicap")
    if handicap is not None:
        if isinstance(handicap, bool):
            return False, "handicap_invalido"
        try:
            number = float(handicap)
        except (ValueError, TypeError, OverflowError):
            return False, "handicap_invalido"
        if not math.isfinite(number):
            return False, "handicap_invalido"
        if abs(number - wanted) > 1e-9:
            return False, "handicap_diferente"
    selection_lines = _lines(selection)
    ref_lines = _lines(ref) if _SIDE.search(ref) else set()
    name_lines = _lines(mercado.get("name"))
    observed = selection_lines | ref_lines | name_lines
    if observed and observed != {wanted}:
        return False, "linha_textual_contraditoria"
    if handicap is None and not observed:
        return False, "linha_nao_comprovada"
    return True, "linha_validada"
