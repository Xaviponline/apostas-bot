"""Forma recente multicompetição via endpoint web atual da ESPN.

A ESPN passou o calendário global de equipas de futebol para site.web.api.espn.com.
Esta camada altera apenas a recolha da forma recente usada em taças/UEFA; a base
da competição, o modelo V1 e os filtros permanecem iguais.
"""
from datetime import datetime
from time import monotonic
from zoneinfo import ZoneInfo

import requests

from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes


class EstatisticasFormaWeb(EstatisticasHibridasCompeticoes):
    ESPN_WEB_BASE = "https://site.web.api.espn.com/apis/site/v2/sports/soccer"

    def _fetch_forma_global(self, team_id, data_ref=None):
        agora = data_ref or datetime.now(ZoneInfo("Europe/Lisbon"))
        if agora.tzinfo is None:
            agora = agora.replace(tzinfo=ZoneInfo("Europe/Lisbon"))
        team_id = int(team_id)
        chave = (team_id, agora.date().isoformat())

        with self._lock:
            cached = self._cache_forma_global.get(chave)
            if cached and monotonic() - cached[0] < self.cache_segundos:
                return cached[1]

        # O endpoint /all/teams/{id}/schedule foi movido para site.web.api.
        # Mantemos o host antigo apenas como último fallback de compatibilidade.
        pedidos = [
            (f"{self.ESPN_WEB_BASE}/all/teams/{team_id}/schedule", None),
            (f"{self.ESPN_WEB_BASE}/all/teams/{team_id}/schedule", {"fixture": "false"}),
            (f"{self.BASE}/all/teams/{team_id}/schedule", None),
        ]

        por_id = {}
        primeiro_erro = None
        resposta_valida = False
        for url, params in pedidos:
            try:
                resposta = self.session.get(url, params=params, timeout=(5, 25))
                resposta.raise_for_status()
                dados = resposta.json()
                eventos = dados.get("events") if isinstance(dados, dict) else None
                if not isinstance(eventos, list):
                    raise ValueError("Calendário global ESPN inválido.")
                resposta_valida = True
            except (requests.RequestException, RuntimeError, ValueError, TypeError) as exc:
                primeiro_erro = primeiro_erro or exc
                continue

            for evento in eventos:
                if not self._evento_oficial(evento):
                    continue
                item = self._normalizar_resultado(evento, "all")
                if item is None:
                    continue
                if float(item["timestamp"]) >= agora.timestamp():
                    continue
                por_id[item["id"]] = item

            if len(por_id) >= 8:
                break

        if not resposta_valida and primeiro_erro is not None:
            raise primeiro_erro

        resultados = sorted(
            por_id.values(), key=lambda x: x["timestamp"], reverse=True
        )[:20]
        with self._lock:
            self._cache_forma_global[chave] = (monotonic(), resultados)
        return resultados
