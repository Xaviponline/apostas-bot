"""Estatísticas reais e probabilidades para o motor premium.

Usa apenas resultados concluídos da ESPN. Não inventa jogos, resultados ou odds.
O modelo inicial usa médias da liga + desempenho casa/fora com shrinkage e uma
matriz de Poisson. As probabilidades são estimativas do modelo, não garantias.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from math import exp, factorial
from threading import Lock
from time import monotonic
from zoneinfo import ZoneInfo
import re
import requests


class EstatisticasESPN:
    BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

    # Whitelist de códigos ESPN validados para o V1. Se uma competição não
    # estiver aqui, o motor não tenta adivinhar o código.
    LIGAS = {
        # Inglaterra
        "english premier league": "eng.1",
        "premier league": "eng.1",
        "english league championship": "eng.2",
        "efl championship": "eng.2",
        "english league one": "eng.3",
        "efl league one": "eng.3",
        "english league two": "eng.4",
        "efl league two": "eng.4",

        # Espanha
        "spanish laliga": "esp.1",
        "laliga": "esp.1",
        "spanish laliga 2": "esp.2",
        "spanish segunda division": "esp.2",
        "laliga 2": "esp.2",

        # Itália
        "italian serie a": "ita.1",
        "serie a": "ita.1",
        "italian serie b": "ita.2",

        # Alemanha
        "german bundesliga": "ger.1",
        "bundesliga": "ger.1",
        "german 2. bundesliga": "ger.2",
        "2. bundesliga": "ger.2",

        # França
        "french ligue 1": "fra.1",
        "ligue 1": "fra.1",
        "french ligue 2": "fra.2",
        "ligue 2": "fra.2",

        # Portugal
        "portuguese primeira liga": "por.1",
        "primeira liga": "por.1",

        # Países Baixos / Bélgica / Turquia
        "dutch eredivisie": "ned.1",
        "eredivisie": "ned.1",
        "dutch keuken kampioen divisie": "ned.2",
        "keuken kampioen divisie": "ned.2",
        "belgian pro league": "bel.1",
        "turkish super lig": "tur.1",
        "super lig": "tur.1",

        # Escócia / Áustria / Dinamarca / Grécia / Suíça
        "scottish premiership": "sco.1",
        "scottish championship": "sco.2",
        "austrian bundesliga": "aut.1",
        "danish superliga": "den.1",
        "greek super league": "gre.1",
        "swiss super league": "sui.1",

        # Escandinávia
        "swedish allsvenskan": "swe.1",
        "allsvenskan": "swe.1",
        "norwegian eliteserien": "nor.1",
        "eliteserien": "nor.1",

        # América
        "major league soccer": "usa.1",
        "mls": "usa.1",
        "brasileiro serie a": "bra.1",
        "brazilian serie a": "bra.1",
        "brasileiro serie b": "bra.2",
        "brazilian serie b": "bra.2",
        "argentine liga profesional": "arg.1",

        # UEFA
        "uefa champions league": "uefa.champions",
        "champions league": "uefa.champions",
        "uefa europa league": "uefa.europa",
        "europa league": "uefa.europa",
        "uefa conference league": "uefa.europa.conf",
        "conference league": "uefa.europa.conf",
        "uefa nations league": "uefa.nations",
        "nations league": "uefa.nations",
    }

    # Ordem importante: slugs mais específicos, como LaLiga 2, têm de vir
    # antes dos seus prefixos de primeira divisão.
    SLUGS = (
        ("spanish-laliga-2", "esp.2"),
        ("english-league-championship", "eng.2"),
        ("english-league-one", "eng.3"),
        ("english-league-two", "eng.4"),
        ("italian-serie-b", "ita.2"),
        ("german-2-bundesliga", "ger.2"),
        ("scottish-premiership", "sco.1"),
        ("scottish-championship", "sco.2"),
        ("austrian-bundesliga", "aut.1"),
        ("danish-superliga", "den.1"),
        ("greek-super-league", "gre.1"),
        ("swiss-super-league", "sui.1"),
        ("major-league-soccer", "usa.1"),
        ("english-premier-league", "eng.1"),
        ("spanish-laliga", "esp.1"),
        ("italian-serie-a", "ita.1"),
        ("german-bundesliga", "ger.1"),
        ("french-ligue-1", "fra.1"),
        ("french-ligue-2", "fra.2"),
        ("portuguese-primeira-liga", "por.1"),
        ("dutch-eredivisie", "ned.1"),
        ("dutch-keuken-kampioen-divisie", "ned.2"),
        ("belgian-pro-league", "bel.1"),
        ("turkish-super-lig", "tur.1"),
        ("swedish-allsvenskan", "swe.1"),
        ("norwegian-eliteserien", "nor.1"),
        ("brazilian-serie-a", "bra.1"),
        ("brazilian-serie-b", "bra.2"),
        ("argentine-liga-profesional", "arg.1"),
        ("uefa-champions-league", "uefa.champions"),
        ("uefa-europa-league", "uefa.europa"),
        ("uefa-conference-league", "uefa.europa.conf"),
        ("uefa-nations-league", "uefa.nations"),
    )

    def __init__(self, session=None, dias_historico=70, cache_segundos=1200):
        self.session = session or requests.Session()
        self.dias_historico = max(30, min(int(dias_historico), 180))
        self.cache_segundos = max(60, int(cache_segundos))
        self._cache = {}
        self._lock = Lock()
        self.ultimo_erros = {}

    @staticmethod
    def resolver_liga(jogo):
        slug = str(jogo.get("season_slug") or "").lower().strip()
        for trecho, codigo in EstatisticasESPN.SLUGS:
            if trecho in slug:
                return codigo
        nome = re.sub(r"\s+", " ", str(jogo.get("liga") or "").lower()).strip()
        return EstatisticasESPN.LIGAS.get(nome)

    @staticmethod
    def _numero_score(valor):
        if isinstance(valor, (int, float)):
            return int(valor)
        if isinstance(valor, str):
            m = re.match(r"^\s*(\d+)\s*$", valor)
            if m:
                return int(m.group(1))
        return None

    @staticmethod
    def _timestamp(valor):
        if not isinstance(valor, str) or not valor:
            return None
        try:
            dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            return None

    @staticmethod
    def _normalizar_resultado(evento, liga_codigo):
        try:
            status = ((evento.get("status") or {}).get("type") or {})
            if str(status.get("state") or "").lower() != "post" and not status.get("completed"):
                return None
            detalhe = " ".join(
                str(status.get(k) or "") for k in ("name", "description", "detail", "shortDetail")
            ).lower()
            # Evita misturar resultados decididos por penáltis no modelo de golos regulamentares.
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
            casa_team, fora_team = casa.get("team") or {}, fora.get("team") or {}
            gc = EstatisticasESPN._numero_score(casa.get("score"))
            gf = EstatisticasESPN._numero_score(fora.get("score"))
            if gc is None or gf is None:
                return None
            ts = EstatisticasESPN._timestamp(evento.get("date") or comp.get("date"))
            if ts is None:
                return None
            return {
                "id": int(evento["id"]),
                "liga_codigo": liga_codigo,
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

        url = f"{self.BASE}/{liga_codigo}/scoreboard"
        r = self.session.get(
            url,
            params={
                "dates": f"{inicio.strftime('%Y%m%d')}-{fim.strftime('%Y%m%d')}",
                "limit": 500,
            },
            timeout=(5, 25),
        )
        r.raise_for_status()
        dados = r.json()
        eventos = dados.get("events") if isinstance(dados, dict) else None
        if not isinstance(eventos, list):
            raise ValueError("Histórico ESPN inválido.")

        resultados = []
        for evento in eventos:
            item = self._normalizar_resultado(evento, liga_codigo)
            if item is not None:
                resultados.append(item)
        resultados.sort(key=lambda x: x["timestamp"], reverse=True)

        with self._lock:
            self._cache[chave] = (monotonic(), resultados)
        return resultados

    def carregar_historicos(self, jogos, data_ref=None):
        codigos = []
        vistos = set()
        for jogo in jogos:
            codigo = self.resolver_liga(jogo)
            if codigo and codigo not in vistos:
                vistos.add(codigo)
                codigos.append(codigo)
        if not codigos:
            return {}

        saida = {}
        self.ultimo_erros = {}
        with ThreadPoolExecutor(max_workers=min(6, len(codigos))) as executor:
            futuros = {executor.submit(self._fetch_liga, c, data_ref): c for c in codigos}
            for futuro in as_completed(futuros):
                codigo = futuros[futuro]
                try:
                    saida[codigo] = futuro.result()
                except (requests.RequestException, RuntimeError, ValueError, TypeError):
                    self.ultimo_erros[codigo] = "indisponível"
        return saida

    @staticmethod
    def _ultimos_time(partidas, team_id, local=None, limite=8):
        encontrados = []
        for p in partidas:
            if team_id not in (p["casa_id"], p["fora_id"]):
                continue
            if local == "casa" and p["casa_id"] != team_id:
                continue
            if local == "fora" and p["fora_id"] != team_id:
                continue
            if p["casa_id"] == team_id:
                gf, ga = p["golos_casa"], p["golos_fora"]
                venue = "casa"
            else:
                gf, ga = p["golos_fora"], p["golos_casa"]
                venue = "fora"
            encontrados.append({"gf": gf, "ga": ga, "local": venue, "timestamp": p["timestamp"]})
            if len(encontrados) >= limite:
                break
        return encontrados

    @staticmethod
    def _media(valores):
        return sum(valores) / len(valores) if valores else 0.0

    @staticmethod
    def _ppg(amostra):
        if not amostra:
            return 0.0
        pontos = sum(3 if x["gf"] > x["ga"] else 1 if x["gf"] == x["ga"] else 0 for x in amostra)
        return pontos / len(amostra)

    @staticmethod
    def _shrink(total_golos, n, baseline, pseudo=3.0):
        return (float(total_golos) + pseudo * baseline) / (float(n) + pseudo)

    @staticmethod
    def _poisson(k, lamb):
        return exp(-lamb) * (lamb ** k) / factorial(k)

    @classmethod
    def _probabilidades(cls, lambda_casa, lambda_fora):
        max_golos = 10
        pc = [cls._poisson(i, lambda_casa) for i in range(max_golos + 1)]
        pf = [cls._poisson(i, lambda_fora) for i in range(max_golos + 1)]
        total_massa = sum(pc) * sum(pf)
        if total_massa <= 0:
            return None

        casa = empate = fora = over15 = over25 = over35 = btts = 0.0
        for i, pi in enumerate(pc):
            for j, pj in enumerate(pf):
                p = (pi * pj) / total_massa
                if i > j:
                    casa += p
                elif i == j:
                    empate += p
                else:
                    fora += p
                if i + j >= 2:
                    over15 += p
                if i + j >= 3:
                    over25 += p
                if i + j >= 4:
                    over35 += p
                if i > 0 and j > 0:
                    btts += p
        return {
            "Vitória Casa": casa,
            "Vitória Fora": fora,
            "Empate": empate,
            "1X (Casa ou Empate)": casa + empate,
            "X2 (Empate ou Fora)": fora + empate,
            "Over 1.5 Golos": over15,
            "Over 2.5 Golos": over25,
            "Over 3.5 Golos": over35,
            "Under 2.5 Golos": 1.0 - over25,
            "Under 3.5 Golos": 1.0 - over35,
            "Ambas Marcam": btts,
        }

    def analisar_jogo(self, jogo, partidas):
        codigo = self.resolver_liga(jogo)
        casa_id, fora_id = jogo.get("casa_id"), jogo.get("fora_id")
        if not codigo or not isinstance(casa_id, int) or not isinstance(fora_id, int):
            return None
        if len(partidas) < 10:
            return None

        casa_all = self._ultimos_time(partidas, casa_id, limite=8)
        fora_all = self._ultimos_time(partidas, fora_id, limite=8)
        if len(casa_all) < 4 or len(fora_all) < 4:
            return None
        casa_home = self._ultimos_time(partidas, casa_id, local="casa", limite=6)
        fora_away = self._ultimos_time(partidas, fora_id, local="fora", limite=6)

        # Se ainda houver poucos jogos no contexto casa/fora, usa a forma geral.
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
        qualidade = round(100 * (0.40 * qualidade_amostra + 0.35 * qualidade_local + 0.25 * qualidade_liga))

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
        }
