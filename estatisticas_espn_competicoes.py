"""Base histórica alargada para taças e provas UEFA.

As ligas regulares continuam a usar a janela normal do V1. Taças nacionais e
provas UEFA usam uma janela maior apenas para calcular a média/base da própria
competição; a forma recente das equipas continua a vir da camada
multicompetição de EstatisticasESPNResiliente.

A ESPN pode rejeitar intervalos longos em algumas taças. Para essas provas a
base é recolhida do presente para trás em blocos curtos de 14 dias, o mesmo
tamanho já usado pelo coletor resiliente do projeto. Falhas isoladas são
toleradas, mas nunca se aceita uma base com menos de 10 jogos reais.
"""
from datetime import datetime, timedelta
from time import monotonic
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter

from main_enriquecido import EstatisticasESPNEnriquecidas


class EstatisticasESPNCompeticoes(EstatisticasESPNEnriquecidas):
    DIAS_BASE_COMPETICAO = 420
    # Competições de seleções são muito espaçadas no calendário. Para a Liga
    # das Nações precisamos alcançar pelo menos o ciclo anterior (2024/25)
    # quando analisamos a edição 2026/27.
    DIAS_BASE_POR_LIGA = {"uefa.nations": 900}
    DIAS_BLOCO_BASE = 14
    MIN_JOGOS_BASE = 10
    ALVO_JOGOS_BASE = 24
    TENTATIVAS_BLOCO = 2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.diagnostico_base = {}
        # carregar_historicos pode consultar ligas e formas em paralelo. Aumenta
        # apenas o pool de ligações reutilizáveis; não aumenta o nº de workers.
        if hasattr(self.session, "mount"):
            adapter = HTTPAdapter(pool_connections=24, pool_maxsize=24, max_retries=0)
            self.session.mount("https://", adapter)

    def _recolher_base_tolerante(self, liga_codigo, inicio, fim):
        """Recolhe blocos recentes de 14 dias e devolve dados + diagnóstico seguro."""
        por_id = {}
        falhas = []
        blocos_total = 0
        blocos_ok = 0
        cursor_fim = fim

        while cursor_fim >= inicio:
            cursor_inicio = max(
                inicio,
                cursor_fim - timedelta(days=self.DIAS_BLOCO_BASE - 1),
            )
            blocos_total += 1
            eventos = None
            ultimo_erro = None

            for _ in range(self.TENTATIVAS_BLOCO):
                try:
                    eventos = self._consultar_intervalo(
                        liga_codigo, cursor_inicio, cursor_fim
                    )
                    ultimo_erro = None
                    break
                except (requests.RequestException, RuntimeError, ValueError, TypeError) as exc:
                    ultimo_erro = exc

            if ultimo_erro is not None:
                falhas.append(ultimo_erro)
            else:
                blocos_ok += 1
                por_id.update(self._normalizar_eventos(eventos or [], liga_codigo))

            if len(por_id) >= self.ALVO_JOGOS_BASE:
                break
            cursor_fim = cursor_inicio - timedelta(days=1)

        motivos = sorted({self._motivo_seguro(exc) for exc in falhas})
        diagnostico = {
            "blocos": blocos_total,
            "blocos_ok": blocos_ok,
            "blocos_falha": len(falhas),
            "jogos": len(por_id),
            "motivos": motivos,
        }
        return por_id, diagnostico, (falhas[0] if falhas else None)

    def _fetch_liga(self, liga_codigo, data_ref=None):
        if liga_codigo not in self.FORMA_MULTICOMPETICAO:
            return super()._fetch_liga(liga_codigo, data_ref)

        agora = data_ref or datetime.now(ZoneInfo("Europe/Lisbon"))
        if agora.tzinfo is None:
            agora = agora.replace(tzinfo=ZoneInfo("Europe/Lisbon"))
        fim = agora.date() - timedelta(days=1)
        dias_base = self.DIAS_BASE_POR_LIGA.get(
            liga_codigo, self.DIAS_BASE_COMPETICAO
        )
        inicio = fim - timedelta(days=dias_base)
        chave = ("base_alargada_14d", liga_codigo, inicio.isoformat(), fim.isoformat())

        with self._lock:
            cached = self._cache.get(chave)
            if cached and monotonic() - cached[0] < self.cache_segundos:
                self.diagnostico_base[liga_codigo] = {
                    "fonte": "cache",
                    "jogos": len(cached[1]),
                }
                return cached[1]

        por_id, diag, primeiro_erro = self._recolher_base_tolerante(
            liga_codigo, inicio, fim
        )
        diag["fonte"] = "blocos_14d"
        self.diagnostico_base[liga_codigo] = diag

        # Se houve falhas e, mesmo percorrendo a janela, não conseguimos o
        # mínimo estatístico, mantém o estado técnico de indisponível.
        if len(por_id) < self.MIN_JOGOS_BASE and primeiro_erro is not None:
            raise primeiro_erro

        resultados = sorted(
            por_id.values(), key=lambda x: x["timestamp"], reverse=True
        )
        with self._lock:
            self._cache[chave] = (monotonic(), resultados)
        return resultados
