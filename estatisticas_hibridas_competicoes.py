"""Histórico híbrido para taças/UEFA quando a ESPN bloqueia a rota histórica.

A descoberta dos jogos do dia continua na camada existente. Para competições
cujo endpoint histórico ESPN foi confirmado a devolver 400/403, esta camada
usa SofaScore apenas para obter a base de golos da própria competição.
O modelo, os filtros e a forma recente das equipas não são alterados.
"""
from datetime import datetime
import re
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
        "uefa.nations",
    }
    # IDs públicos e estáveis das provas no SofaScore. Evita depender da agenda
    # diária, que em produção devolveu HTTP 404 mesmo com as provas existentes.
    SOFA_TOURNAMENT_IDS = {
        "arg.copa": 1024,
        "eng.league_cup": 21,
        "uefa.europa": 679,
        "uefa.nations": 10783,
    }
    SOFA_ANO_CALENDARIO = {"arg.copa"}
    SOFA_WWW_BASE = "https://www.sofascore.com/api/v1"
    MAX_PAGINAS_SOFA = 8

    def __init__(self, *args, sofa_client=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._sofa_client = sofa_client

    @staticmethod
    def _motivo_seguro_sofa(exc):
        texto = re.sub(r"\s+", " ", str(exc or "")).strip()
        if not texto:
            return "falha sem detalhe"
        return texto[:140]

    def _sofa(self):
        if self._sofa_client is None:
            self._sofa_client = BuscadorJogosReais(enabled=True)
        return self._sofa_client

    def _sofa_get_www(self, cliente, caminho, status_api=None):
        sessao = getattr(cliente, "sofa_session", None)
        if sessao is None:
            detalhe = f"API HTTP {status_api}" if status_api is not None else "API indisponível"
            raise ValueError(f"{detalhe}; sem sessão WWW")

        url = f"{self.SOFA_WWW_BASE}{caminho}"
        status_www = None
        try:
            browser_mode = bool(getattr(cliente, "browser_mode", False))
            headers_fn = getattr(cliente, "_headers_sofa", None)
            headers = headers_fn() if callable(headers_fn) else {
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.sofascore.com/",
            }
            if browser_mode:
                aquecer = getattr(cliente, "_aquecer_sofa", None)
                if callable(aquecer):
                    aquecer()
                resposta = sessao.get(
                    url,
                    impersonate="chrome",
                    headers=headers,
                    timeout=20,
                )
            else:
                resposta = sessao.get(
                    url,
                    headers={
                        **headers,
                        "User-Agent": "Mozilla/5.0 Chrome/146.0 Safari/537.36",
                    },
                    timeout=20,
                )
            status_www = getattr(resposta, "status_code", None)
            cliente.sofa_http_status = status_www
            cliente.ultimo_http_status = status_www
            resposta.raise_for_status()
            dados = resposta.json()
            if not isinstance(dados, dict):
                raise ValueError("resposta WWW não JSON")
            return dados
        except Exception:
            parte_api = f"API HTTP {status_api}" if status_api is not None else "API falhou"
            parte_www = f"WWW HTTP {status_www}" if status_www is not None else "WWW falhou"
            raise ValueError(f"{parte_api}; {parte_www}") from None

    def _sofa_get(self, caminho):
        cliente = self._sofa()
        metodo = getattr(cliente, "_get_sofa", None)
        if not callable(metodo):
            raise ValueError("Cliente SofaScore inválido.")
        try:
            return metodo(caminho)
        except Exception:
            status_api = getattr(cliente, "sofa_http_status", None)
            return self._sofa_get_www(cliente, caminho, status_api=status_api)

    @staticmethod
    def _data_ref(data_ref=None):
        agora = data_ref or datetime.now(ZoneInfo("Europe/Lisbon"))
        if agora.tzinfo is None:
            agora = agora.replace(tzinfo=ZoneInfo("Europe/Lisbon"))
        return agora

    @classmethod
    def _ano_alvo_sofa(cls, liga_codigo, agora):
        if liga_codigo in cls.SOFA_ANO_CALENDARIO:
            return str(agora.year)
        inicio = agora.year if agora.month >= 7 else agora.year - 1
        return f"{inicio % 100:02d}/{(inicio + 1) % 100:02d}"

    def _descobrir_competicao_sofa(self, liga_codigo, data_ref=None):
        try:
            unique_id = int(self.SOFA_TOURNAMENT_IDS[liga_codigo])
        except (KeyError, TypeError, ValueError):
            raise ValueError("competição não mapeada") from None

        agora = self._data_ref(data_ref)
        alvo = self._ano_alvo_sofa(liga_codigo, agora)
        try:
            dados = self._sofa_get(f"/unique-tournament/{unique_id}/seasons")
        except (requests.RequestException, ValueError, TypeError, RuntimeError) as exc:
            raise ValueError(
                f"épocas torneio {unique_id}: {self._motivo_seguro_sofa(exc)}"
            ) from None

        temporadas = dados.get("seasons") if isinstance(dados, dict) else None
        if not isinstance(temporadas, list):
            raise ValueError(f"épocas torneio {unique_id}: lista ausente")

        candidatos = []
        for temporada in temporadas:
            if not isinstance(temporada, dict):
                continue
            ano = str(temporada.get("year") or "").strip()
            nome = str(temporada.get("name") or "").strip()
            if ano != alvo and alvo not in nome:
                continue
            try:
                candidatos.append(int(temporada["id"]))
            except (KeyError, TypeError, ValueError):
                continue

        candidatos = sorted(set(candidatos))
        if not candidatos:
            raise ValueError(f"época {alvo} não encontrada para torneio {unique_id}")
        if len(candidatos) != 1:
            raise ValueError(f"época {alvo} ambígua para torneio {unique_id}")
        return unique_id, candidatos[0]

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
            try:
                dados = self._sofa_get(
                    f"/unique-tournament/{unique_id}/season/{season_id}/events/last/{pagina}"
                )
            except (requests.RequestException, ValueError, TypeError, RuntimeError) as exc:
                raise ValueError(
                    f"histórico página {pagina}: {self._motivo_seguro_sofa(exc)}"
                ) from None
            eventos = dados.get("events") if isinstance(dados, dict) else None
            if not isinstance(eventos, list):
                raise ValueError(f"histórico página {pagina}: lista ausente")
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
            "torneio_id": unique_id,
            "temporada_id": season_id,
        }
        if len(resultados) < self.MIN_JOGOS_BASE:
            raise ValueError(f"base insuficiente: {len(resultados)}/{self.MIN_JOGOS_BASE}")

        with self._lock:
            self._cache[chave] = (monotonic(), resultados)
        return resultados

    def _fetch_liga(self, liga_codigo, data_ref=None):
        if liga_codigo in self.ESPN_HISTORICO_BLOQUEADO:
            try:
                return self._fetch_base_sofa(liga_codigo, data_ref)
            except (requests.RequestException, ValueError, TypeError, RuntimeError) as exc:
                self.diagnostico_base[liga_codigo] = {
                    "fonte": "sofascore_indisponivel",
                    "jogos": 0,
                    "motivo": self._motivo_seguro_sofa(exc),
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
