"""Histórico híbrido para taças/UEFA quando a ESPN bloqueia a rota histórica.

A descoberta dos jogos do dia continua na camada existente. Para competições
cujo endpoint histórico ESPN foi confirmado a devolver 400/403, esta camada
usa SofaScore apenas para obter a base de golos da própria competição.
O modelo, os filtros e a forma recente das equipas não são alterados.
"""
from datetime import datetime
import re
import unicodedata
from time import monotonic
from zoneinfo import ZoneInfo

import requests

from buscador_jogos_reais import BuscadorJogosReais
from estatisticas_espn_competicoes import EstatisticasESPNCompeticoes


class EstatisticasHibridasCompeticoes(EstatisticasESPNCompeticoes):
    ESPN_HISTORICO_BLOQUEADO = {
        "arg.copa",
        "eng.league_cup",
        "uefa.europa",
    }
    SOFA_ALIASES = {
        "arg.copa": {"copa argentina"},
        "eng.league_cup": {"efl cup", "carabao cup", "english league cup", "league cup"},
        "uefa.europa": {"uefa europa league", "europa league"},
    }
    MAX_PAGINAS_SOFA = 8

    def __init__(self, *args, sofa_client=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._sofa_client = sofa_client

    @staticmethod
    def _nome_sofa(valor):
        texto = unicodedata.normalize("NFKD", str(valor or ""))
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        texto = re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()
        return re.sub(r"\s+", " ", texto)

    def _sofa(self):
        if self._sofa_client is None:
            self._sofa_client = BuscadorJogosReais(enabled=True)
        return self._sofa_client

    def _sofa_get(self, caminho):
        cliente = self._sofa()
        metodo = getattr(cliente, "_get_sofa", None)
        if not callable(metodo):
            raise ValueError("Cliente SofaScore inválido.")
        return metodo(caminho)

    @staticmethod
    def _data_ref(data_ref=None):
        agora = data_ref or datetime.now(ZoneInfo("Europe/Lisbon"))
        if agora.tzinfo is None:
            agora = agora.replace(tzinfo=ZoneInfo("Europe/Lisbon"))
        return agora

    def _eventos_sofa_do_dia(self, data_iso):
        ultimo_erro = None
        for sufixo in ("/inverse", ""):
            try:
                dados = self._sofa_get(
                    f"/sport/football/scheduled-events/{data_iso}{sufixo}"
                )
                eventos = dados.get("events") if isinstance(dados, dict) else None
                if isinstance(eventos, list):
                    return eventos
                ultimo_erro = ValueError("Lista SofaScore ausente.")
            except (requests.RequestException, ValueError, TypeError, RuntimeError) as exc:
                ultimo_erro = exc
        if ultimo_erro is not None:
            raise ultimo_erro
        raise ValueError("SofaScore indisponível.")

    def _descobrir_competicao_sofa(self, liga_codigo, data_ref=None):
        aliases = {
            self._nome_sofa(nome)
            for nome in self.SOFA_ALIASES.get(liga_codigo, set())
        }
        if not aliases:
            raise ValueError("Competição SofaScore não mapeada.")

        agora = self._data_ref(data_ref)
        eventos = self._eventos_sofa_do_dia(agora.date().isoformat())
        pares = set()
        for evento in eventos:
            if not isinstance(evento, dict):
                continue
            torneio = evento.get("tournament") or {}
            unico = torneio.get("uniqueTournament") or {}
            nomes = {
                self._nome_sofa(unico.get("name")),
                self._nome_sofa(torneio.get("name")),
            }
            if not (nomes & aliases):
                continue
            temporada = evento.get("season") or {}
            try:
                unique_id = int(unico["id"])
                season_id = int(temporada["id"])
            except (KeyError, TypeError, ValueError):
                continue
            pares.add((unique_id, season_id))

        if len(pares) != 1:
            raise ValueError("Competição SofaScore ambígua ou ausente.")
        return next(iter(pares))

    @staticmethod
    def _score_sofa(score):
        if not isinstance(score, dict):
            return None
        valor = score.get("normaltime")
        if isinstance(valor, (int, float)):
            return int(valor)

        chaves_extra = {
            "extra1", "extra2", "overtime", "penalties", "period3", "period4"
        }
        if any(chave in score for chave in chaves_extra):
            return None
        valor = score.get("current")
        if isinstance(valor, (int, float)):
            return int(valor)
        return None

    def _normalizar_resultado_sofa(self, evento, liga_codigo, antes_de_ts):
        try:
            if not isinstance(evento, dict):
                return None
            status = evento.get("status") or {}
            tipo = str(status.get("type") or "").lower()
            codigo_status = status.get("code")
            if codigo_status != 100 and tipo not in {
                "finished", "afterextra", "afterpenalties", "ended"
            }:
                return None

            ts = float(evento["startTimestamp"])
            if ts >= float(antes_de_ts):
                return None

            casa = evento.get("homeTeam") or {}
            fora = evento.get("awayTeam") or {}
            gc = self._score_sofa(evento.get("homeScore") or {})
            gf = self._score_sofa(evento.get("awayScore") or {})
            if gc is None or gf is None:
                return None

            return {
                "id": int(evento["id"]),
                "liga_codigo": liga_codigo,
                "timestamp": ts,
                "casa_id": int(casa["id"]),
                "fora_id": int(fora["id"]),
                "casa": str(casa.get("name") or "").strip(),
                "fora": str(fora.get("name") or "").strip(),
                "golos_casa": gc,
                "golos_fora": gf,
            }
        except (KeyError, TypeError, ValueError):
            return None

    def _fetch_base_sofa(self, liga_codigo, data_ref=None):
        agora = self._data_ref(data_ref)
        chave = ("base_sofascore", liga_codigo, agora.date().isoformat())
        with self._lock:
            cached = self._cache.get(chave)
            if cached and monotonic() - cached[0] < self.cache_segundos:
                self.diagnostico_base[liga_codigo] = {
                    "fonte": "cache_sofascore",
                    "jogos": len(cached[1]),
                }
                return cached[1]

        unique_id, season_id = self._descobrir_competicao_sofa(liga_codigo, agora)
        por_id = {}
        paginas = 0
        for pagina in range(self.MAX_PAGINAS_SOFA):
            dados = self._sofa_get(
                f"/unique-tournament/{unique_id}/season/{season_id}/events/last/{pagina}"
            )
            eventos = dados.get("events") if isinstance(dados, dict) else None
            if not isinstance(eventos, list):
                raise ValueError("Histórico SofaScore inválido.")
            paginas += 1
            for evento in eventos:
                item = self._normalizar_resultado_sofa(
                    evento, liga_codigo, agora.timestamp()
                )
                if item is not None:
                    por_id[item["id"]] = item

            if len(por_id) >= self.ALVO_JOGOS_BASE:
                break
            if not bool(dados.get("hasNextPage")):
                break

        resultados = sorted(
            por_id.values(), key=lambda x: x["timestamp"], reverse=True
        )
        self.diagnostico_base[liga_codigo] = {
            "fonte": "sofascore",
            "jogos": len(resultados),
            "paginas": paginas,
        }
        if len(resultados) < self.MIN_JOGOS_BASE:
            raise ValueError("Base SofaScore insuficiente.")

        with self._lock:
            self._cache[chave] = (monotonic(), resultados)
        return resultados

    def _fetch_liga(self, liga_codigo, data_ref=None):
        if liga_codigo in self.ESPN_HISTORICO_BLOQUEADO:
            try:
                return self._fetch_base_sofa(liga_codigo, data_ref)
            except (requests.RequestException, ValueError, TypeError, RuntimeError):
                self.diagnostico_base[liga_codigo] = {
                    "fonte": "sofascore_indisponivel",
                    "jogos": 0,
                }
                raise

        try:
            historico = super()._fetch_liga(liga_codigo, data_ref)
        except (requests.RequestException, ValueError, TypeError, RuntimeError):
            if liga_codigo not in self.FORMA_MULTICOMPETICAO:
                raise
            return self._fetch_base_sofa(liga_codigo, data_ref)

        if liga_codigo in self.FORMA_MULTICOMPETICAO and len(historico) < self.MIN_JOGOS_BASE:
            return self._fetch_base_sofa(liga_codigo, data_ref)
        return historico
