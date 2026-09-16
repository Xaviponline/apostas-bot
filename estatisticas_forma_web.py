"""Forma recente multicompetição via calendários públicos da ESPN.

Para resultados já concluídos, a rota site.api com parâmetros de resultados é
mais fiável do que a rota web usada sobretudo para fixtures. Esta camada altera
apenas a recolha da forma recente usada em taças/UEFA; a base da competição, o
modelo V1 e os filtros permanecem iguais.
"""
from datetime import datetime
from time import monotonic
from zoneinfo import ZoneInfo

import requests

from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes


class EstatisticasFormaWeb(EstatisticasHibridasCompeticoes):
    ESPN_WEB_BASE = "https://site.web.api.espn.com/apis/site/v2/sports/soccer"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.diagnostico_forma_global = {}

    @classmethod
    def _numero_score_forma(cls, valor):
        numero = cls._numero_score(valor)
        if numero is not None:
            return numero
        if isinstance(valor, dict):
            for chave in ("value", "displayValue", "current", "score"):
                numero = cls._numero_score(valor.get(chave))
                if numero is not None:
                    return numero
        return None

    @staticmethod
    def _status_forma(evento):
        """Lê o estado final nos dois formatos usados pelos calendários ESPN."""
        if not isinstance(evento, dict):
            return {}

        candidatos = []
        status_evento = evento.get("status") or {}
        if isinstance(status_evento, dict):
            candidatos.append(status_evento.get("type") or status_evento)

        competicoes = evento.get("competitions") or []
        if competicoes and isinstance(competicoes[0], dict):
            status_comp = competicoes[0].get("status") or {}
            if isinstance(status_comp, dict):
                candidatos.append(status_comp.get("type") or status_comp)

        for status in candidatos:
            if not isinstance(status, dict):
                continue
            estado = str(status.get("state") or "").lower().strip()
            if estado or status.get("completed") is not None or status.get("name"):
                return status
        return {}

    @classmethod
    def _concluido_forma(cls, evento):
        status = cls._status_forma(evento)
        estado = str(status.get("state") or "").lower().strip()
        if estado == "post" or status.get("completed") is True:
            return True
        nome = " ".join(
            str(status.get(k) or "")
            for k in ("name", "description", "detail", "shortDetail")
        ).lower()
        return "status_final" in nome or nome.strip() in {"final", "ft", "full time"}

    @classmethod
    def _normalizar_resultado_forma(cls, evento):
        # Primeiro tenta o formato já suportado pelo V1.
        item = cls._normalizar_resultado(evento, "all")
        if item is not None:
            return item

        # Alguns calendários de equipa colocam o status em competitions[0]
        # e/ou devolvem o score como objeto em vez de string/número.
        try:
            if not isinstance(evento, dict) or not cls._concluido_forma(evento):
                return None
            status = cls._status_forma(evento)
            detalhe = " ".join(
                str(status.get(k) or "")
                for k in ("name", "description", "detail", "shortDetail")
            ).lower()
            if "pen" in detalhe:
                return None

            competicoes = evento.get("competitions") or []
            if not competicoes:
                return None
            comp = competicoes[0]
            concorrentes = comp.get("competitors") or []
            if len(concorrentes) < 2:
                return None
            casa = next((c for c in concorrentes if c.get("homeAway") == "home"), None)
            fora = next((c for c in concorrentes if c.get("homeAway") == "away"), None)
            if casa is None or fora is None:
                return None

            casa_team = casa.get("team") or {}
            fora_team = fora.get("team") or {}
            gc = cls._numero_score_forma(casa.get("score"))
            gf = cls._numero_score_forma(fora.get("score"))
            if gc is None or gf is None:
                return None
            ts = cls._timestamp(evento.get("date") or comp.get("date"))
            if ts is None:
                return None

            return {
                "id": int(evento["id"]),
                "liga_codigo": "all",
                "timestamp": ts,
                "casa_id": int(casa_team["id"]),
                "fora_id": int(fora_team["id"]),
                "casa": str(casa_team.get("displayName") or casa_team.get("name") or "").strip(),
                "fora": str(fora_team.get("displayName") or fora_team.get("name") or "").strip(),
                "golos_casa": gc,
                "golos_fora": gf,
            }
        except (KeyError, TypeError, ValueError):
            return None

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

        rota_site = f"{self.BASE}/all/teams/{team_id}/schedule"
        rota_web = f"{self.ESPN_WEB_BASE}/all/teams/{team_id}/schedule"
        pedidos = [
            (rota_site, {"seasontype": 1, "type": 0, "level": 3}, "site_resultados"),
            (rota_site, None, "site_sem_parametros"),
            (rota_web, None, "web_sem_parametros"),
            (rota_web, {"fixture": "false"}, "web_fixture_false"),
        ]

        por_id = {}
        primeiro_erro = None
        resposta_valida = False
        tentativas = []
        for url, params, nome_rota in pedidos:
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
                tentativas.append({"rota": nome_rota, "erro": self._motivo_seguro(exc)})
                continue

            oficiais = 0
            concluidos = 0
            normalizados = 0
            for evento in eventos:
                if not self._evento_oficial(evento):
                    continue
                oficiais += 1
                if self._concluido_forma(evento):
                    concluidos += 1
                item = self._normalizar_resultado_forma(evento)
                if item is None:
                    continue
                if float(item["timestamp"]) >= agora.timestamp():
                    continue
                normalizados += 1
                por_id[item["id"]] = item

            tentativas.append({
                "rota": nome_rota,
                "eventos": len(eventos),
                "oficiais": oficiais,
                "concluidos": concluidos,
                "normalizados": normalizados,
            })
            if len(por_id) >= 8:
                break

        if not resposta_valida and primeiro_erro is not None:
            self.diagnostico_forma_global[team_id] = {"tentativas": tentativas, "jogos": 0}
            raise primeiro_erro

        resultados = sorted(
            por_id.values(), key=lambda x: x["timestamp"], reverse=True
        )[:20]
        self.diagnostico_forma_global[team_id] = {
            "tentativas": tentativas,
            "jogos": len(resultados),
        }
        with self._lock:
            self._cache_forma_global[chave] = (monotonic(), resultados)
        return resultados
