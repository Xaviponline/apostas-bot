"""Base histórica alargada para taças e provas UEFA.

As ligas regulares continuam a usar a janela normal do V1. Taças nacionais e
provas UEFA usam uma janela maior apenas para calcular a média/base da própria
competição; a forma recente das equipas continua a vir da camada
multicompetição de EstatisticasESPNResiliente.
"""
from datetime import datetime, timedelta
from time import monotonic
from zoneinfo import ZoneInfo

import requests

from main_enriquecido import EstatisticasESPNEnriquecidas


class EstatisticasESPNCompeticoes(EstatisticasESPNEnriquecidas):
    DIAS_BASE_COMPETICAO = 420

    def _fetch_liga(self, liga_codigo, data_ref=None):
        if liga_codigo not in self.FORMA_MULTICOMPETICAO:
            return super()._fetch_liga(liga_codigo, data_ref)

        agora = data_ref or datetime.now(ZoneInfo("Europe/Lisbon"))
        if agora.tzinfo is None:
            agora = agora.replace(tzinfo=ZoneInfo("Europe/Lisbon"))
        fim = agora.date() - timedelta(days=1)
        inicio = fim - timedelta(days=self.DIAS_BASE_COMPETICAO)
        chave = ("base_alargada", liga_codigo, inicio.isoformat(), fim.isoformat())

        with self._lock:
            cached = self._cache.get(chave)
            if cached and monotonic() - cached[0] < self.cache_segundos:
                return cached[1]

        try:
            eventos = self._consultar_intervalo(liga_codigo, inicio, fim)
            por_id = self._normalizar_eventos(eventos, liga_codigo)
        except (requests.RequestException, RuntimeError, ValueError, TypeError):
            # Para uma janela de 420 dias não fazemos fallback diário: seriam
            # centenas de pedidos. O fallback por blocos mantém a recolha segura.
            por_id = self._recolher_por_blocos(liga_codigo, inicio, fim)

        resultados = sorted(
            por_id.values(), key=lambda x: x["timestamp"], reverse=True
        )
        with self._lock:
            self._cache[chave] = (monotonic(), resultados)
        return resultados
