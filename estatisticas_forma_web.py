"""Forma recente multicompetição via calendários públicos da ESPN.

Para resultados já concluídos, a rota site.api com parâmetros de resultados é
mais fiável do que a rota web usada sobretudo para fixtures. Esta camada altera
a recolha da forma recente usada em taças/UEFA e trata explicitamente provas em
campo neutro quando a designação casa/fora do feed não representa vantagem real.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from time import monotonic
from zoneinfo import ZoneInfo

import requests

from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes


class EstatisticasFormaWeb(EstatisticasHibridasCompeticoes):
    ESPN_WEB_BASE = "https://site.web.api.espn.com/apis/site/v2/sports/soccer"
    COMPETICOES_NEUTRAS = {"arg.copa"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.diagnostico_forma_global = {}
        self._equipas_contexto_liga = {}

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

    @classmethod
    def _codigo_competicao_evento(cls, evento):
        if not isinstance(evento, dict):
            return None

        slugs = []
        nomes = []
        season = evento.get("season") or {}
        league = evento.get("league") or {}
        competicoes = evento.get("competitions") or []
        comp = competicoes[0] if competicoes and isinstance(competicoes[0], dict) else {}
        comp_league = comp.get("league") or {}

        for bloco in (season, league, comp_league):
            if not isinstance(bloco, dict):
                continue
            slug = str(bloco.get("slug") or "").strip()
            if slug:
                slugs.append(slug)
            for chave in ("name", "displayName", "shortName"):
                nome = str(bloco.get(chave) or "").strip()
                if nome:
                    nomes.append(nome)

        for slug in slugs:
            codigo = cls.resolver_liga({"season_slug": slug})
            if codigo:
                return codigo
        for nome in nomes:
            codigo = cls.resolver_liga({"liga": nome})
            if codigo:
                return codigo
        return None

    def _eventos_equipa_temporada(self, team_id, season):
        team_id = int(team_id)
        rota_site = f"{self.BASE}/all/teams/{team_id}/schedule"
        rota_web = f"{self.ESPN_WEB_BASE}/all/teams/{team_id}/schedule"
        pedidos = [
            (
                rota_site,
                {"season": int(season), "seasontype": 1, "type": 0, "level": 3},
            ),
            (rota_site, {"season": int(season)}),
            (rota_web, {"season": int(season)}),
        ]
        primeiro_erro = None
        for url, params in pedidos:
            try:
                resposta = self.session.get(url, params=params, timeout=(5, 25))
                resposta.raise_for_status()
                dados = resposta.json()
                eventos = dados.get("events") if isinstance(dados, dict) else None
                if not isinstance(eventos, list):
                    raise ValueError("Calendário histórico ESPN inválido.")
                return eventos
            except (requests.RequestException, RuntimeError, ValueError, TypeError) as exc:
                primeiro_erro = primeiro_erro or exc
        if primeiro_erro is not None:
            raise primeiro_erro
        raise ValueError("Calendário histórico ESPN indisponível.")

    def _fetch_base_nations_por_equipas(self, data_ref=None):
        liga_codigo = "uefa.nations"
        agora = data_ref or datetime.now(ZoneInfo("Europe/Lisbon"))
        if agora.tzinfo is None:
            agora = agora.replace(tzinfo=ZoneInfo("Europe/Lisbon"))

        equipas = sorted(self._equipas_contexto_liga.get(liga_codigo) or [])
        if len(equipas) < 2:
            raise ValueError("equipas da Liga das Nações indisponíveis")

        alvo = self._ano_alvo_sofa(liga_codigo, agora)
        try:
            inicio_curto = int(str(alvo).split("/", 1)[0])
        except (TypeError, ValueError):
            raise ValueError("época-alvo inválida") from None
        season = 2000 + inicio_curto

        chave = ("base_nations_equipas", season, tuple(equipas), agora.date().isoformat())
        with self._lock:
            cached = self._cache.get(chave)
            if cached and monotonic() - cached[0] < self.cache_segundos:
                self.diagnostico_base[liga_codigo] = {
                    "fonte": "cache_espn_equipas",
                    "jogos": len(cached[1]),
                    "equipas": len(equipas),
                    "temporada": season,
                }
                return cached[1]

        por_id = {}
        respostas_ok = 0
        primeiro_erro = None
        with ThreadPoolExecutor(max_workers=min(6, len(equipas))) as executor:
            futuros = {
                executor.submit(self._eventos_equipa_temporada, team_id, season): team_id
                for team_id in equipas
            }
            for futuro in as_completed(futuros):
                try:
                    eventos = futuro.result()
                    respostas_ok += 1
                except (requests.RequestException, RuntimeError, ValueError, TypeError) as exc:
                    primeiro_erro = primeiro_erro or exc
                    continue

                for evento in eventos:
                    if self._codigo_competicao_evento(evento) != liga_codigo:
                        continue
                    item = self._normalizar_resultado_forma(evento)
                    if item is None:
                        continue
                    if float(item["timestamp"]) >= agora.timestamp():
                        continue
                    item["liga_codigo"] = liga_codigo
                    por_id[item["id"]] = item

        resultados = sorted(
            por_id.values(), key=lambda x: x["timestamp"], reverse=True
        )
        if len(resultados) < self.MIN_JOGOS_BASE:
            if respostas_ok == 0 and primeiro_erro is not None:
                raise primeiro_erro
            raise ValueError(
                f"base ESPN por equipas insuficiente: {len(resultados)}/{self.MIN_JOGOS_BASE}"
            )

        self.diagnostico_base[liga_codigo] = {
            "fonte": "espn_team_schedules",
            "jogos": len(resultados),
            "equipas": len(equipas),
            "temporada": season,
        }
        with self._lock:
            self._cache[chave] = (monotonic(), resultados)
        return resultados

    def _fetch_liga(self, liga_codigo, data_ref=None):
        try:
            return super()._fetch_liga(liga_codigo, data_ref)
        except (requests.RequestException, RuntimeError, ValueError, TypeError) as erro_primario:
            if liga_codigo != "uefa.nations":
                raise

            try:
                return self._fetch_base_nations_por_equipas(data_ref)
            except (requests.RequestException, RuntimeError, ValueError, TypeError) as erro_fallback:
                self.diagnostico_base[liga_codigo] = {
                    "fonte": "sofa_e_espn_equipas_indisponiveis",
                    "jogos": 0,
                    "motivo": (
                        f"SofaScore: {self._motivo_seguro_sofa(erro_primario)}; "
                        f"ESPN equipas: {self._motivo_seguro_sofa(erro_fallback)}"
                    ),
                }
                raise erro_fallback

    def carregar_historicos(self, jogos, data_ref=None):
        contexto = {}
        for jogo in jogos or []:
            if not isinstance(jogo, dict):
                continue
            codigo = self.resolver_liga(jogo)
            if not codigo:
                continue
            ids = contexto.setdefault(codigo, set())
            for campo in ("casa_id", "fora_id"):
                team_id = jogo.get(campo)
                if isinstance(team_id, int) and team_id > 0:
                    ids.add(team_id)
        self._equipas_contexto_liga = contexto
        return super().carregar_historicos(jogos, data_ref)

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

    def _analisar_multicompeticao_neutra(self, jogo, partidas):
        """Modelo sem vantagem casa/fora para provas em estádio neutro.

        A etiqueta home/away do feed serve apenas para identificar a primeira e
        segunda equipa. A forma usa os últimos jogos oficiais gerais de cada
        equipa e a base de golos da prova é tornada simétrica.
        """
        codigo = self.resolver_liga(jogo)
        casa_id, fora_id = jogo.get("casa_id"), jogo.get("fora_id")
        if not codigo or not isinstance(casa_id, int) or not isinstance(fora_id, int):
            return None
        if len(partidas) < 10:
            return None

        partidas_casa = self._formas_globais.get(casa_id) or []
        partidas_fora = self._formas_globais.get(fora_id) or []
        casa_all = self._ultimos_time(partidas_casa, casa_id, limite=8)
        fora_all = self._ultimos_time(partidas_fora, fora_id, limite=8)
        if len(casa_all) < 4 or len(fora_all) < 4:
            return None

        liga_home = self._media([p["golos_casa"] for p in partidas])
        liga_away = self._media([p["golos_fora"] for p in partidas])
        baseline_neutro = (liga_home + liga_away) / 2.0
        if baseline_neutro < 0.25:
            return None

        casa_gf = self._shrink(
            sum(x["gf"] for x in casa_all), len(casa_all), baseline_neutro
        )
        casa_ga = self._shrink(
            sum(x["ga"] for x in casa_all), len(casa_all), baseline_neutro
        )
        fora_gf = self._shrink(
            sum(x["gf"] for x in fora_all), len(fora_all), baseline_neutro
        )
        fora_ga = self._shrink(
            sum(x["ga"] for x in fora_all), len(fora_all), baseline_neutro
        )

        lambda_casa = casa_gf * fora_ga / baseline_neutro
        lambda_fora = fora_gf * casa_ga / baseline_neutro
        lambda_casa = min(3.8, max(0.20, lambda_casa))
        lambda_fora = min(3.8, max(0.20, lambda_fora))
        probs = self._probabilidades(lambda_casa, lambda_fora)
        if not probs:
            return None

        qualidade_amostra = min(1.0, min(len(casa_all), len(fora_all)) / 8.0)
        qualidade_liga = min(1.0, len(partidas) / 35.0)
        qualidade = round(100 * (0.75 * qualidade_amostra + 0.25 * qualidade_liga))

        return {
            "jogo": jogo,
            "liga_codigo": codigo,
            "lambda_casa": lambda_casa,
            "lambda_fora": lambda_fora,
            "probabilidades": probs,
            "qualidade": qualidade,
            "amostra_casa": len(casa_all),
            "amostra_fora": len(fora_all),
            "amostra_liga": len(partidas),
            "ppg_casa": self._ppg(casa_all[:6]),
            "ppg_fora": self._ppg(fora_all[:6]),
            "forma_fonte": "multicompeticao",
            "contexto_partida": "neutro",
            "baseline_neutro": baseline_neutro,
            "liga_home_original": liga_home,
            "liga_away_original": liga_away,
            "gf_casa_ajustado": casa_gf,
            "ga_casa_ajustado": casa_ga,
            "gf_fora_ajustado": fora_gf,
            "ga_fora_ajustado": fora_ga,
        }

    def analisar_jogo(self, jogo, partidas):
        codigo = self.resolver_liga(jogo)
        if codigo in self.COMPETICOES_NEUTRAS:
            return self._analisar_multicompeticao_neutra(jogo, partidas)
        return super().analisar_jogo(jogo, partidas)
