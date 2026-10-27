"""Proposta SHADOW: valida apenas a linha de totais, sem modificar produção.

Não resolve sozinho a identidade do evento, mercado ou disponibilidade.
"""
import math
import re

def _numeros(texto):
    return {float(v.replace(",", ".")) for v in re.findall(r"(?<![\d.])\d+(?:[.,]\d+)?(?![\d.])", str(texto or ""))}

def validar_linha_totais(alvo, mercado, selecao):
    """Retorna (valido, motivo); falha de forma conservadora se houver contradição."""
    match = re.fullmatch(r"(Over|Under) (\d+(?:\.\d+)?) Golos", str(alvo))
    if not match or not isinstance(mercado, dict) or not isinstance(selecao, dict):
        return False, "dados_invalidos"
    desejada = float(match.group(2))
    lado = match.group(1).lower()
    escolha = str(selecao.get("seleção") or "")
    ref = str(selecao.get("ref") or "")
    if not re.search(r"\b" + lado + r"\b", escolha + " " + ref, re.I):
        return False, "lado_diferente"
    handicap = mercado.get("handicap")
    if handicap is not None:
        if isinstance(handicap, bool):
            return False, "handicap_invalido"
        try:
            h = float(handicap)
        except (ValueError, TypeError, OverflowError):
            return False, "handicap_invalido"
        if not math.isfinite(h) or abs(h - desejada) > 1e-9:
            return False, "handicap_diferente"
    else:
        h = None
    linhas = _numeros(escolha)
    if re.search(r"\b(over|under)\b", ref, re.I):
        linhas |= _numeros(ref)
    linhas |= _numeros(mercado.get("name"))
    if linhas and linhas != {desejada}:
        return False, "linha_textual_contraditoria"
    if h is None and not linhas:
        return False, "linha_nao_comprovada"
    return True, "linha_validada"
