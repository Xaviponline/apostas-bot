"""Diagnóstico de horários de fixtures: somente leitura, zero consultas externas.

Usa apenas os timestamps do modelo e do evento já recebido. Nunca torna
um fixture válido, não altera odds ou snapshots e não inventa fusos horários.
"""
from datetime import datetime, timezone
from math import isfinite
from zoneinfo import ZoneInfo

_PT = ZoneInfo("Europe/Lisbon")


def _instante_fonte(valor):
    if not isinstance(valor, str) or not 0 < len(valor) <= 64:
        return None
    try:
        dt = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def detalhe_horario_shadow(timestamp_modelo, inicio_fonte):
    """Diferença *fonte - modelo*; positivo = fonte começa mais tarde.

    Devolve None para horas incompletas, inválidas ou compatíveis (<=30 min).
    O formato para Portugal inclui sempre o desvio UTC para evitar
    ambiguidades durante as mudanças de hora de verão/inverno.
    """
    if isinstance(timestamp_modelo, bool):
        return None
    fonte = _instante_fonte(inicio_fonte)
    if fonte is None:
        return None
    try:
        ts = float(timestamp_modelo)
        if not isfinite(ts):
            return None
        modelo = datetime.fromtimestamp(ts, timezone.utc)
        diferenca = (fonte - modelo).total_seconds() / 60
        if abs(diferenca) <= 30:
            return None
        return {
            "modelo_utc": modelo.isoformat().replace("+00:00", "Z"),
            "fornecedor_utc": fonte.isoformat().replace("+00:00", "Z"),
            "modelo_pt": modelo.astimezone(_PT).strftime("%d/%m/%Y %H:%M %z"),
            "fornecedor_pt": fonte.astimezone(_PT).strftime("%d/%m/%Y %H:%M %z"),
            "desvio_min": round(diferenca, 1),
        }
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def normalizar_detalhe_horario_shadow(dados, timestamp_modelo=None):
    """Reconstrói valores canónicos: ignora campos arbitrários/injetados.

    Se o timestamp oficial estiver disponível, exige que coincida com o
    registado. Nunca recupera odds nem horários históricos ausentes.
    """
    if not isinstance(dados, dict):
        return None
    modelo = _instante_fonte(dados.get("modelo_utc"))
    if modelo is None:
        return None
    if timestamp_modelo is not None:
        try:
            if isinstance(timestamp_modelo, bool) or abs(
                float(timestamp_modelo) - modelo.timestamp()
            ) > 0.001:
                return None
        except (TypeError, ValueError, OverflowError):
            return None
    return detalhe_horario_shadow(
        modelo.timestamp(), dados.get("fornecedor_utc")
    )
