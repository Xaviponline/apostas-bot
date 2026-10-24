"""Verificações determinísticas de identidade e frescura para odds.

Só atua sobre novas observações; não reescreve snapshots nem odds antigas.
Sem APIs, tokens, heurísticas fuzzy ou dependências externas.
"""
from datetime import datetime, timezone
import re
import unicodedata

# Desvio tolerável de hora entre o jogo do modelo e o fixture do fornecedor.
# Uma diferença de 1 h (fuso, jogo distinto ou adiamento) não deve ser ignorada.
MAX_DESVIO_KICKOFF_SEG = 30 * 60
MAX_IDADE_ODD_SEG = 6 * 3600
MAX_FUTURO_ODD_SEG = 5 * 60


def _normalizar(texto):
    v = unicodedata.normalize("NFKD", str(texto or "")).casefold()
    v = "".join(c for c in v if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", v).strip()


def _categoria_equipa(texto):
    n = _normalizar(texto)
    if not n:
        return None, False, False
    idade = re.findall(r"\b(?:u|sub)\s*(17|18|19|20|21|23)\b", n)
    genero_feminino = bool(re.search(
        r"\b(?:women|womens|woman|ladies|feminino|feminina|"
        r"femenina|femenino|femminile)\b", n
    ))
    reserva = bool(re.search(r"\b(?:b|ii|reserves|reserva|reservas)\b$", n))
    return (idade[0] if idade else None), genero_feminino, reserva


def equipas_categoria_incompativel(nome_modelo, nome_fonte):
    """Nome de clube principal nunca valida como nome juvenil, B ou feminino."""
    esperado = _categoria_equipa(nome_modelo)
    observado = _categoria_equipa(nome_fonte)
    return esperado != observado


def _instante_iso(valor):
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        dt = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.timestamp()


def verificar_hora_fixture(timestamp_modelo, inicio_fonte, exigir_hora=False):
    """(aprovado, diagnóstico). Não equiparar nunca times mal identificados."""
    inicio = _instante_iso(inicio_fonte)
    try:
        modelo = float(timestamp_modelo)
        from math import isfinite
        if not isfinite(modelo):
            modelo = None
    except (TypeError, ValueError, OverflowError):
        modelo = None
    if inicio is None or modelo is None:
        return (False, "horario_fixture_nao_comprovado") if exigir_hora else (True, "")
    if abs(inicio - modelo) > MAX_DESVIO_KICKOFF_SEG:
        return False, "horario_fixture_incompativel"
    return True, ""


def classificar_frescura(atualizada_em, referencia):
    """Diagnóstico passivo: timestamps ausentes e antigos nao viram odds frescas."""
    ts = _instante_iso(atualizada_em)
    if ts is None:
        return "odd_sem_data_atualizacao"
    agora_ts = referencia.timestamp()
    delta = agora_ts - ts
    if delta < -MAX_FUTURO_ODD_SEG:
        return "odd_data_futura"
    if delta > MAX_IDADE_ODD_SEG:
        return "odd_desatualizada"
    return None
