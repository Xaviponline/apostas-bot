"""Carregamento resiliente de histórico ESPN sem alterar o modelo V1.

Tenta primeiro a mesma janela longa usada pela V1. Se a ESPN rejeitar essa
consulta, repete a recolha em blocos menores e, por fim, por datas individuais.
Nunca aceita um histórico parcial: se qualquer consulta necessária falhar, a
competição continua marcada como indisponível.

Para taças e provas europeias de clubes, a média/base continua a vir da própria
competição, mas a forma recente das equipas pode ser completada com jogos
officiais de todas as competições. Isto evita rejeitar equipas que tenham poucos
jogos recentes dentro da taça sem baixar os filtros do V1.
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
    TRABALHADORES_FORMAS = 6
    # Novas leituras do calendário: apenas estas duas provas neste PR.
    FORMA_ESQUEMA_CORRIGIDO = frozenset({"uefa.champions", "por.taca.portugal"})

    # Competições em que a forma apenas dentro da própria prova costuma ser
    # curta (taças nacionais e UEFA). A base estatística da competição não é
    # substituída; apenas a forma recente de cada equipa usa jogos oficiais de
    # todas as competições quando disponível.
    FORMA_MULTICOMPETICAO = {
        "uefa.champions",
        "uefa.europa",
        "uefa.europa.conf",
        "uefa.nations",
        "eng.fa",
        "eng.league_cup",
        "esp.copa_del_rey",
        "ger.dfb_pokal",
        "ita.coppa_italia",
        "fra.coupe_de_france",
        "por.taca.portugal",
        "ned.cup",
        "sco.tennents",
        "sco.cis",
        "bra.copa_do_brazil",
        "arg.copa",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache_forma_global = {}
        self._cache_forma_global_legado = {}
        self._formas_globais = {}
        self._formas_globais_legado = {}
        self.ultimo_erros_forma = {}

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

    @staticmethod
    def _evento_oficial(evento):
        """Exclui amigáveis/preseason do calendário global da equipa."""
        if not isinstance(evento, dict):
            return False
        season = evento.get("season") or {}
        league = evento.get("league") or {}
        competicoes = evento.get("competitions") or []
        comp = competicoes[0] if competicoes and isinstance(competicoes[0], dict) else {}
        comp_league = comp.get("league") or {}
        textos = [
            evento.get("name"),
            season.get("name") if isinstance(season, dict) else None,
            season.get("slug") if isinstance(season, dict) else None,
            league.get("name") if isinstance(league, dict) else None,
            league.get("slug") if isinstance(league, dict) else None,
            comp_league.get("name") if isinstance(comp_league, dict) else None,
            comp_league.get("slug") if isinstance(comp_league, dict) else None,
        ]
        texto = " ".join(str(x or "") for x in textos).lower()
        proibidos = ("friendly", "friendlies", "preseason", "pre-season", "testimonial")
        return not any(palavra in texto for palavra in proibidos)

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

    @staticmethod
    def _adaptar_evento_forma_equipa(evento):
        """Adapta o esquema ESPN /teams/{id}/schedule ao normalizador existente.

        A rota devolve status em competitions[0].status e score como objeto
        {value: 2.0, displayValue: "2"}. Não supõe jogos finalizados e rejeita
        golos não inteiros, em falta ou contraditórios. Não altera o payload
        original nem modifica regras de qualidade/probabilidades.
        """
        if not isinstance(evento, dict):
            return None
        competicoes = evento.get("competitions") or []
        if not isinstance(competicoes, list) or not competicoes:
            return None
        comp = competicoes[0]
        if not isinstance(comp, dict):
            return None
        rivais = comp.get("competitors")
        if not isinstance(rivais, list) or len(rivais) < 2:
            return None

        adaptados = []
        for rival in rivais:
            if not isinstance(rival, dict):
                return None
            score = rival.get("score")
            if isinstance(score, dict):
                valor = score.get("value")
                if type(valor) not in (int, float):
                    return None
                numerico = float(valor)
                if not (0 <= numerico <= 100 and numerico.is_integer()):
                    return None
                exibicao = score.get("displayValue")
                if exibicao is not None:
                    verificacao = EstatisticasESPN._numero_score(exibicao)
                    if verificacao is None or verificacao != int(numerico):
                        return None
                score = int(numerico)
            adaptados.append({**rival, "score": score})

        status = evento.get("status")
        if not isinstance(status, dict) or not isinstance(status.get("type"), dict):
            status = comp.get("status")
        if not isinstance(status, dict) or not isinstance(status.get("type"), dict):
            return None
        return {
            **evento,
            "status": status,
            "competitions": [{**comp, "competitors": adaptados}, *competicoes[1:]],
        }

    def _fetch_forma_global(self, team_id, data_ref=None):
        """Últimos resultados oficiais da equipa em todas as competições ESPN."""
        agora = data_ref or datetime.now(ZoneInfo("Europe/Lisbon"))
        if agora.tzinfo is None:
            agora = agora.replace(tzinfo=ZoneInfo("Europe/Lisbon"))
        chave = (int(team_id), agora.date().isoformat())

        with self._lock:
            cached = self._cache_forma_global.get(chave)
            if cached and monotonic() - cached[0] < self.cache_segundos:
                return cached[1]

        url = f"{self.BASE}/all/teams/{int(team_id)}/schedule"
        resposta = self.session.get(url, timeout=(5, 25))
        resposta.raise_for_status()
        dados = resposta.json()
        eventos = dados.get("events") if isinstance(dados, dict) else None
        if not isinstance(eventos, list):
            raise ValueError("Calendário global ESPN inválido.")

        por_id = {}
        por_id_legado = {}
        for evento in eventos:
            if not self._evento_oficial(evento):
                continue

            # Primeiro o esquema aceite na main. Guardá-lo em separado impede
            # que este PR altere as outras taças/UEFA, mesmo quando partilham
            # equipas com a Champions ou com a Taça de Portugal.
            original = self._normalizar_resultado(evento, "all")
            if original is not None:
                if float(original["timestamp"]) < agora.timestamp():
                    por_id_legado[original["id"]] = original
                    por_id[original["id"]] = original
                continue

            adaptado = self._adaptar_evento_forma_equipa(evento)
            if adaptado is None:
                continue
            item = self._normalizar_resultado(adaptado, "all")
            if item is None:
                continue
            # Nunca usar um resultado posterior ao momento da análise.
            if float(item["timestamp"]) >= agora.timestamp():
                continue
            por_id[item["id"]] = item

        resultados = sorted(
            por_id.values(), key=lambda x: x["timestamp"], reverse=True
        )[:20]
        resultados_legado = sorted(
            por_id_legado.values(), key=lambda x: x["timestamp"], reverse=True
        )[:20]
        with self._lock:
            self._cache_forma_global[chave] = (monotonic(), resultados)
            self._cache_forma_global_legado[chave] = resultados_legado
        return resultados

    def _precarregar_formas_globais(self, jogos, data_ref=None):
        ids = set()
        for jogo in jogos or []:
            if not isinstance(jogo, dict):
                continue
            codigo = self.resolver_liga(jogo)
            if codigo not in self.FORMA_MULTICOMPETICAO:
                continue
            for campo in ("casa_id", "fora_id"):
                team_id = jogo.get(campo)
                if isinstance(team_id, int) and team_id > 0:
                    ids.add(team_id)

        self._formas_globais = {}
        self._formas_globais_legado = {}
        self.ultimo_erros_forma = {}
        if not ids:
            return

        referencia = data_ref or datetime.now(ZoneInfo("Europe/Lisbon"))
        if referencia.tzinfo is None:
            referencia = referencia.replace(tzinfo=ZoneInfo("Europe/Lisbon"))
        dia_chave = referencia.date().isoformat()

        with ThreadPoolExecutor(max_workers=min(self.TRABALHADORES_FORMAS, len(ids))) as executor:
            futuros = {
                executor.submit(self._fetch_forma_global, team_id, data_ref): team_id
                for team_id in ids
            }
            for futuro in as_completed(futuros):
                team_id = futuros[futuro]
                try:
                    self._formas_globais[team_id] = futuro.result()
                    chave = (int(team_id), dia_chave)
                    with self._lock:
                        legado = self._cache_forma_global_legado.get(chave)
                    # Subclasses antigas de testes podem substituir a consulta
                    # sem cache legado: preservar o contrato de então.
                    self._formas_globais_legado[team_id] = (
                        self._formas_globais[team_id] if legado is None else legado
                    )
                except (requests.RequestException, RuntimeError, ValueError, TypeError) as exc:
                    self.ultimo_erros_forma[team_id] = self._motivo_seguro(exc)

    def carregar_historicos(self, jogos, data_ref=None):
        """Mantém o contrato da V1 e prepara forma global só onde é necessária."""
        codigos = []
        vistos = set()
        for jogo in jogos:
            codigo = self.resolver_liga(jogo)
            if codigo and codigo not in vistos:
                vistos.add(codigo)
                codigos.append(codigo)
        if not codigos:
            self.ultimo_erros = {}
            self._formas_globais = {}
            self._formas_globais_legado = {}
            self.ultimo_erros_forma = {}
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

        self._precarregar_formas_globais(jogos, data_ref)
        return saida

    def analisar_jogo(self, jogo, partidas):
        codigo = self.resolver_liga(jogo)
        if codigo not in self.FORMA_MULTICOMPETICAO:
            return super().analisar_jogo(jogo, partidas)

        casa_id, fora_id = jogo.get("casa_id"), jogo.get("fora_id")
        if not codigo or not isinstance(casa_id, int) or not isinstance(fora_id, int):
            return None

        # A base de golos continua a exigir uma amostra real da competição.
        if len(partidas) < 10:
            return None

        # Para todas as outras taças, manter exatamente a forma que a main
        # conseguiria normalizar. A recuperação dos esquemas aninhados só
        # beneficia as duas provas explícitas da auditoria.
        formas = (
            self._formas_globais
            if codigo in self.FORMA_ESQUEMA_CORRIGIDO
            else (self._formas_globais_legado or self._formas_globais)
        )
        partidas_casa = formas.get(casa_id) or []
        partidas_fora = formas.get(fora_id) or []
        casa_all = self._ultimos_time(partidas_casa, casa_id, limite=8)
        fora_all = self._ultimos_time(partidas_fora, fora_id, limite=8)
        if len(casa_all) < 4 or len(fora_all) < 4:
            return None

        casa_home = self._ultimos_time(partidas_casa, casa_id, local="casa", limite=6)
        fora_away = self._ultimos_time(partidas_fora, fora_id, local="fora", limite=6)
        amostra_casa = casa_home if len(casa_home) >= 3 else casa_all
        amostra_fora = fora_away if len(fora_away) >= 3 else fora_all

        liga_home = self._media([p["golos_casa"] for p in partidas])
        liga_away = self._media([p["golos_fora"] for p in partidas])
        if liga_home < 0.3 or liga_away < 0.2:
            return None

        casa_gf = self._shrink(sum(x["gf"] for x in amostra_casa), len(amostra_casa), liga_home)
        casa_ga = self._shrink(sum(x["ga"] for x in amostra_casa), len(amostra_casa), liga_away)
        fora_gf = self._shrink(sum(x["gf"] for x in amostra_fora), len(amostra_fora), liga_away)
        fora_ga = self._shrink(sum(x["ga"] for x in amostra_fora), len(amostra_fora), liga_home)

        lambda_casa = casa_gf * fora_ga / liga_home
        lambda_fora = fora_gf * casa_ga / liga_away
        lambda_casa = min(3.8, max(0.20, lambda_casa))
        lambda_fora = min(3.8, max(0.20, lambda_fora))
        probs = self._probabilidades(lambda_casa, lambda_fora)
        if not probs:
            return None

        qualidade_amostra = min(1.0, min(len(casa_all), len(fora_all)) / 8.0)
        qualidade_local = min(1.0, min(len(casa_home), len(fora_away)) / 5.0)
        qualidade_liga = min(1.0, len(partidas) / 35.0)
        qualidade = round(
            100 * (0.40 * qualidade_amostra + 0.35 * qualidade_local + 0.25 * qualidade_liga)
        )

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
        }
