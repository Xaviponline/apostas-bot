"""Carregamento resiliente de histórico ESPN sem alterar o modelo V1.

Tenta primeiro a mesma janela longa usada pela V1. Se a ESPN rejeitar essa
consulta, repete a recolha em blocos menores e, por fim, por datas individuais.
Nunca aceita um histórico parcial: se qualquer consulta necessária falhar, a
competição continua marcada como indisponível.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from time import monotonic
from zoneinfo import ZoneInfo

import requests

from estatisticas_espn import EstatisticasESPN


class EstatisticasESPNResiliente(EstatisticasESPN):
    DIAS_POR_BLOCO = 14
    TRABALHADORES_DIARIOS = 4

    def _consultar_intervalo(self, liga_codigo, inicio, fim):
        url = f"{self.BASE}/{liga_codigo}/scoreboard"
        resposta = self.session.get(
            url,
            params={
                "dates": f"{inicio.strftime('%Y%m%d')}-{fim.strftime('%Y%m%d')}",
                "limit": 500,
            },
            timeout=(5, 25),
        )
        resposta.raise_for_status()
        dados = resposta.json()
        eventos = dados.get("events") if isinstance(dados, dict) else None
        if not isinstance(eventos, list):
            raise ValueError("Histórico ESPN inválido.")
        return eventos

    def _consultar_dia(self, liga_codigo, data):
        """Consulta ESPN com o formato diário, sem hífen/range no parâmetro dates."""
        url = f"{self.BASE}/{liga_codigo}/scoreboard"
        resposta = self.session.get(
            url,
            params={"dates": data.strftime("%Y%m%d"), "limit": 500},
            timeout=(5, 25),
        )
        resposta.raise_for_status()
        dados = resposta.json()
        eventos = dados.get("events") if isinstance(dados, dict) else None
        if not isinstance(eventos, list):
            raise ValueError("Histórico ESPN diário inválido.")
        return eventos

    def _normalizar_eventos(self, eventos, liga_codigo):
        resultados = {}
        for evento in eventos:
            item = self._normalizar_resultado(evento, liga_codigo)
            if item is not None:
                resultados[item["id"]] = item
        return resultados

    @staticmethod
    def _motivo_seguro(exc):
        """Resume a falha sem expor URL, headers, tokens ou payloads."""
        if isinstance(exc, requests.HTTPError):
            status = getattr(getattr(exc, "response", None), "status_code", None)
            return f"HTTP {status}" if status is not None else "erro HTTP"
        if isinstance(exc, requests.Timeout):
            return "timeout"
        if isinstance(exc, requests.ConnectionError):
            return "erro de ligação"
        if isinstance(exc, ValueError):
            return "resposta inválida"
        if isinstance(exc, TypeError):
            return "dados inválidos"
        if isinstance(exc, RuntimeError):
            return "erro de execução"
        return "erro desconhecido"

    def _recolher_por_blocos(self, liga_codigo, inicio, fim):
        por_id = {}
        cursor = inicio
        while cursor <= fim:
            bloco_fim = min(cursor + timedelta(days=self.DIAS_POR_BLOCO - 1), fim)
            eventos = self._consultar_intervalo(liga_codigo, cursor, bloco_fim)
            por_id.update(self._normalizar_eventos(eventos, liga_codigo))
            cursor = bloco_fim + timedelta(days=1)
        return por_id

    def _recolher_por_dias(self, liga_codigo, inicio, fim):
        """Último fallback: datas singulares em paralelo, sem aceitar dias em falta."""
        datas = []
        cursor = inicio
        while cursor <= fim:
            datas.append(cursor)
            cursor += timedelta(days=1)

        por_id = {}
        primeiro_erro = None
        with ThreadPoolExecutor(
            max_workers=min(self.TRABALHADORES_DIARIOS, max(1, len(datas)))
        ) as executor:
            futuros = {
                executor.submit(self._consultar_dia, liga_codigo, data): data
                for data in datas
            }
            for futuro in as_completed(futuros):
                try:
                    eventos = futuro.result()
                except (requests.RequestException, RuntimeError, ValueError, TypeError) as exc:
                    primeiro_erro = primeiro_erro or exc
                    continue
                por_id.update(self._normalizar_eventos(eventos, liga_codigo))

        if primeiro_erro is not None:
            raise primeiro_erro
        return por_id

    def _fetch_liga(self, liga_codigo, data_ref=None):
        agora = data_ref or datetime.now(ZoneInfo("Europe/Lisbon"))
        if agora.tzinfo is None:
            agora = agora.replace(tzinfo=ZoneInfo("Europe/Lisbon"))
        fim = agora.date() - timedelta(days=1)
        inicio = fim - timedelta(days=self.dias_historico)
        chave = (liga_codigo, inicio.isoformat(), fim.isoformat())

        with self._lock:
            cached = self._cache.get(chave)
            if cached and monotonic() - cached[0] < self.cache_segundos:
                return cached[1]

        try:
            eventos = self._consultar_intervalo(liga_codigo, inicio, fim)
            por_id = self._normalizar_eventos(eventos, liga_codigo)
        except (requests.RequestException, RuntimeError, ValueError, TypeError):
            try:
                por_id = self._recolher_por_blocos(liga_codigo, inicio, fim)
            except (requests.RequestException, RuntimeError, ValueError, TypeError):
                por_id = self._recolher_por_dias(liga_codigo, inicio, fim)

        resultados = sorted(
            por_id.values(), key=lambda x: x["timestamp"], reverse=True
        )
        with self._lock:
            self._cache[chave] = (monotonic(), resultados)
        return resultados

    def carregar_historicos(self, jogos, data_ref=None):
        """Mantém o contrato da V1 e regista apenas um motivo técnico seguro."""
        codigos = []
        vistos = set()
        for jogo in jogos:
            codigo = self.resolver_liga(jogo)
            if codigo and codigo not in vistos:
                vistos.add(codigo)
                codigos.append(codigo)
        if not codigos:
            self.ultimo_erros = {}
            return {}

        saida = {}
        self.ultimo_erros = {}
        with ThreadPoolExecutor(max_workers=min(6, len(codigos))) as executor:
            futuros = {executor.submit(self._fetch_liga, c, data_ref): c for c in codigos}
            for futuro in as_completed(futuros):
                codigo = futuros[futuro]
                try:
                    saida[codigo] = futuro.result()
                except (requests.RequestException, RuntimeError, ValueError, TypeError) as exc:
                    self.ultimo_erros[codigo] = self._motivo_seguro(exc)
        return saida
