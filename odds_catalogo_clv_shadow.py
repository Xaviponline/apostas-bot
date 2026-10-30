"""Investigação PASSIVA de rótulos OddsPapi quando não há mercado compatível.

Usa exclusivamente a resposta já recebida na captura CLV: zero HTTP, zero
preços, zero IDs de outcomes e zero alteração da lógica de associação.
Os rótulos são pistas, NUNCA prova de linha/seleção Betano disponível.
"""
from math import isfinite
import re
import unicodedata


def _texto_seguro(valor, limite=64):
    """Reduz informação de terceiros a rótulos curtos, imprimíveis e sem URLs."""
    s = unicodedata.normalize("NFKD", str(valor or ""))
    s = "".join(c for c in s if ord(c) < 128 and
                (c.isalnum() or c in " ._-"))
    return re.sub(r"\s+", " ", s).strip()[:limite]


def _linha_segura(valor):
    if valor is None or isinstance(valor, bool):
        return "?"
    try:
        n = float(valor)
    except (TypeError, ValueError, OverflowError):
        return "?"
    return f"{n:g}" if isfinite(n) and 0 <= n <= 20 else "?"


def _perfil(nome):
    palavras = set(re.findall(r"[a-z]+", nome.casefold()))
    if palavras & {
        "corner", "corners", "card", "cards", "booking", "bookings",
        "shot", "shots", "offside", "offsides", "player",
    } or ({"team", "1"} <= set(nome.casefold().split())) or "team" in palavras:
        return 0, "outro_mercado"
    golos = bool(palavras & {"goal", "goals", "golo", "golos"})
    total = bool(palavras & {"total", "totals", "over", "under"})
    if golos and total:
        return 3, "potencial_total_golos"
    if golos:
        return 2, "golos_nome_incompleto"
    if {"over", "under"} <= palavras or "total" in palavras:
        return 1, "total_generico_sem_golos"
    return 0, "outro_mercado"


def resumo_catalogo_sem_match(mercados, mercado_modelo, periodo_compativel):
    """Só apura hipóteses; jamais devolve uma odd ou um objeto de mercado."""
    if not isinstance(mercados, list):
        return None
    if not re.fullmatch(r"(?:Over|Under) [0-9]+(?:\.[0-9]+)? Golos",
                        str(mercado_modelo or "")):
        return None
    candidatos = []
    potenciais = 0
    nao_ft = 0
    nomes_em_falta = 0
    for index, mercado in enumerate(mercados):
        if not isinstance(mercado, dict):
            continue
        nome = _texto_seguro(mercado.get("name"))
        if not nome:
            nomes_em_falta += 1
            continue
        score, perfil = _perfil(nome)
        if score:
            potenciais += 1
            try:
                if not periodo_compativel(mercado):
                    nao_ft += 1
            except (ValueError, TypeError, AttributeError):
                nao_ft += 1
        # ID do mercado é apenas metadado, nunca um outcomeRef ou segredo.
        identificador = str(mercado.get("id") or "").strip()
        if not re.fullmatch(r"[0-9]{1,18}", identificador):
            identificador = "?"
        periodo = _texto_seguro(mercado.get("period"), 22) or "?"
        candidatos.append((
            -score, index,
            {"id": identificador, "nome": nome,
             "periodo": periodo, "linha": _linha_segura(mercado.get("handicap")),
             "pista": perfil}
        ))
    candidatos.sort(key=lambda item: (item[0], item[1]))
    return {
        "potenciais": min(potenciais, 999),
        "potenciais_outro_periodo": min(nao_ft, 999),
        "sem_nome": min(nomes_em_falta, 999),
        "amostra": [item[2] for item in candidatos[:4]],
    }
