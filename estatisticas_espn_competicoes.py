"""Base histórica alargada para taças e provas UEFA.

As ligas regulares continuam a usar a janela normal do V1. Taças nacionais e
provas UEFA usam uma janela maior apenas para calcular a média/base da própria
competição; a forma recente das equipas continua a vir da camada
multicompetição de EstatisticasESPNResiliente.

A ESPN pode falhar em intervalos extensos ou num bloco isolado. Para estas
competições a recolha tenta primeiro a janela completa e, se não obtiver a
amostra mínima, percorre blocos recentes de 60 dias. Um bloco isolado pode
falhar sem invalidar toda a competição, mas a base só é aceite se existirem
pelo menos 10 jogos concluídos reais, o mesmo mínimo exigido pelo modelo.
"""
from datetime import datetime, timedelta
from time import monotonic
from zoneinfo import ZoneInfo

import requests

from main_enriquecido import EstatisticasESPNEnriquecidas


class EstatisticasESPNCompeticoes(EstatisticasESPNEnriquecidas):
    DIAS_BASE_COMPETICAO = 420
    DIAS_BLOCO_BASE = 60
    MIN_JOGOS_BASE = 10
    ALVO_JOGOS_BASE = 50

    def _recolher_base_tolerante(self, liga_codigo, inicio, fim):
        """Recolhe blocos recentes, tolerando falhas isoladas sem inventar dados."""
        por_id = {}
        falhas = []
        cursor_fim = fim

        while cursor_fim >= inicio:
            cursor_inicio = max(
                inicio,
                cursor_fim - timedelta(days=self.DIAS_BLOCO_BASE - 1),
            )
            try:
                eventos = self._consultar_intervalo(
                    liga_codigo, cursor_inicio, cursor_fim
                )
                por_id.update(self._normalizar_eventos(eventos, liga_codigo))
            except (requests.RequestException, RuntimeError, ValueError, TypeError) as exc:
                falhas.append(exc)

            if len(por_id) >= self.ALVO_JOGOS_BASE:
                break
            cursor_fim = cursor_inicio - timedelta(days=1)

        if len(por_id) < self.MIN_JOGOS_BASE and falhas:
            # Só marcar a competição como tecnicamente indisponível quando,
            # depois de percorrer a janela, nem sequer há a amostra mínima.
            raise falhas[0]
        return por_id

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

        por_id = {}
        erro_janela = None
        try:
            eventos = self._consultar_intervalo(liga_codigo, inicio, fim)
            por_id = self._normalizar_eventos(eventos, liga_codigo)
        except (requests.RequestException, RuntimeError, ValueError, TypeError) as exc:
            erro_janela = exc

        # Mesmo uma resposta HTTP válida pode vir vazia/incompleta para uma
        # janela muito longa. Nesse caso tenta blocos menores e recentes.
        if len(por_id) < self.MIN_JOGOS_BASE:
            try:
                blocos = self._recolher_base_tolerante(liga_codigo, inicio, fim)
                por_id.update(blocos)
            except (requests.RequestException, RuntimeError, ValueError, TypeError):
                if erro_janela is not None:
                    raise erro_janela
                raise

        resultados = sorted(
            por_id.values(), key=lambda x: x["timestamp"], reverse=True
        )
        with self._lock:
            self._cache[chave] = (monotonic(), resultados)
        return resultados
