"""Protecao conservadora de categorias — apenas exposicao e odds FUTURAS.

Nao altera snapshots originais, V1.2, regras VALOR V1.3 ou coortes.
Calendario de 24/10/2026 verificado na federacao turca (TFF):
https://www.tff.org/default.aspx?pageID=1750
Os tres jogos abaixo sao U19 PAF Ligi, apesar do rotulo senior ESPN.
"""
import re
import unicodedata


def _normalizar(nome):
    s = unicodedata.normalize("NFKD", str(nome or "")).casefold()
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def categoria_juvenil(nome):
    n = _normalizar(nome)
    # Apenas etiquetas explicitas de idade, nao siglas vagas.
    return bool(re.search(r"\bu ?(?:17|18|19|20|21|23)\b|\bunder ?(?:17|18|19|20|21|23)\b", n))


def categorias_incompativeis(liga_modelo, liga_fonte):
    """So declara incompatibilidade inequivoca quando ambas as ligas existem."""
    if not str(liga_modelo or "").strip() or not str(liga_fonte or "").strip():
        return False
    return categoria_juvenil(liga_modelo) != categoria_juvenil(liga_fonte)


# Conjunto finito de fixtures verificados como U19 pela TFF. O dia e obrigatorio:
# impossivel bloquear futuramente o mesmo par senior por engano.
_U19_TFF_2026_10_24 = {
    ("samsunspor", "amed sfk"),
    ("gaziantep fk", "erzurum bb"),
    ("eyupspor", "kasimpasa"),
}


def juventude_confirmada_hoje(p):
    """Match estrito de data, liga declarada senior e equipas originais."""
    if not isinstance(p, dict):
        return False
    if p.get("data_jogo") != "2026-10-24":
        return False
    if _normalizar(p.get("liga")) != "turkish super lig":
        return False
    return (_normalizar(p.get("casa")), _normalizar(p.get("fora"))) in _U19_TFF_2026_10_24
