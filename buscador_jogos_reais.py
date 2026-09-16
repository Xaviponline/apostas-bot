"""Conector de leitura para jogos reais.

Fonte principal: ESPN scoreboard público, sem chave API.
Fallback: endpoints de ligas ESPN e, por último, SofaScore quando acessível.
Nunca inventa jogos nem odds; se todas as fontes falharem devolve lista vazia.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os
import re
import requests

from nomes_ligas import nome_liga_pt

try:
    from curl_cffi import requests as browser_requests
except ImportError:
    browser_requests = None


class BuscadorJogosReais:
    ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
    ESPN_LEAGUES = (
        "eng.1",
        "esp.1",
        "ita.1",
        "ger.1",
        "fra.1",
        "por.1",
        "ned.1",
        "bel.1",
        "uefa.champions",
        "uefa.europa",
        "uefa.europa.conf",
        "uefa.nations",
        "fifa.world",
        "usa.1",
        "bra.1",
        "arg.1",
    )
    ESPN_SLUG_NOMES = (
        ("english-premier-league", "English Premier League"),
        ("spanish-laliga", "Spanish LaLiga"),
        ("italian-serie-a", "Italian Serie A"),
        ("german-bundesliga", "German Bundesliga"),
        ("french-ligue-1", "French Ligue 1"),
        ("french-ligue-2", "French Ligue 2"),
        ("portuguese-primeira-liga", "Portuguese Primeira Liga"),
        ("dutch-eredivisie", "Eredivisie"),
        ("dutch-keuken-kampioen-divisie", "Keuken Kampioen Divisie"),
        ("belgian-pro-league", "Belgian Pro League"),
        ("turkish-super-lig", "Turkish Super Lig"),
        ("swedish-allsvenskan", "Allsvenskan"),
        ("norwegian-eliteserien", "Eliteserien"),
        ("brazilian-serie-a", "Brasileiro Serie A"),
        ("brazilian-serie-b", "Brasileiro Serie B"),
        ("argentine-liga-profesional", "Argentine Liga Profesional"),
        ("uefa-champions-league", "UEFA Champions League"),
        ("uefa-europa-league", "UEFA Europa League"),
        ("uefa-conference-league", "UEFA Conference League"),
        ("uefa-nations-league", "UEFA Nations League"),
        ("fifa-world-cup", "FIFA World Cup"),
    )
    SOFA_BASE_URL = "https://api.sofascore.com/api/v1"
    SOFA_SITE_URL = "https://www.sofascore.com/"

    def __init__(self, session=None, enabled=None):
        self._session_injetada = session is not None
        self.espn_session = session or requests.Session()

        if session is not None:
            self.sofa_session = session
            self.browser_mode = False
        elif browser_requests is not None:
            self.sofa_session = browser_requests.Session()
            self.browser_mode = True
        else:
            self.sofa_session = requests.Session()
            self.browser_mode = False

        if enabled is None:
            env_enabled = os.getenv("ENABLE_REAL_GAMES", os.getenv("ENABLE_SOFASCORE", "0"))
            self.enabled = bool(session) if session is not None else env_enabled == "1"
        else:
            self.enabled = bool(enabled)

        self.estado = "por validar" if self.enabled else "desativado"
        self.ultimo_total = 0
        self.ultimo_http_status = None
        self.espn_http_status = None
        self.sofa_http_status = None
        self.fonte = None
        self._sofa_aquecida = False
        self._espn_respondeu = False

    @staticmethod
    def _hora_lisboa_timestamp(timestamp):
        if type(timestamp) not in (int, float):
            return "--:--"
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(
            ZoneInfo("Europe/Lisbon")
        )
        return dt.strftime("%H:%M")

    @staticmethod
    def _iso_para_timestamp(valor):
        if not isinstance(valor, str) or not valor.strip():
            return None
        try:
            dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            return None

    @staticmethod
    def _season_slug_espn(evento):
        season = evento.get("season") or {}
        if not isinstance(season, dict):
            return ""
        slug = season.get("slug")
        return str(slug or "").strip().lower()

    @classmethod
    def _nome_liga_por_slug(cls, slug):
        slug = str(slug or "").strip().lower()
        if not slug:
            return None
        for trecho, nome in cls.ESPN_SLUG_NOMES:
            if trecho in slug:
                return nome
        return None

    @classmethod
    def _nome_liga_espn(cls, evento, competicao):
        candidatos_liga = [
            (evento.get("league") or {}).get("name")
            if isinstance(evento.get("league"), dict)
            else None,
            (competicao.get("league") or {}).get("name")
            if isinstance(competicao.get("league"), dict)
            else None,
        ]
        for valor in candidatos_liga:
            if isinstance(valor, str) and valor.strip():
                return valor.strip()

        # O season.name da rota global ESPN pode ser apenas a fase da prova
        # ("League Phase", "Group Stage", etc.). O slug preserva normalmente
        # a identidade da competição e é também usado pelo motor V1.
        slug = cls._season_slug_espn(evento)
        nome_slug = cls._nome_liga_por_slug(slug)
        if nome_slug:
            return nome_slug

        season = evento.get("season") or {}
        nome_season = season.get("name") if isinstance(season, dict) else None
        if isinstance(nome_season, str) and nome_season.strip():
            return nome_season.strip()

        if slug:
            slug_limpo = re.sub(r"^\d{4}(?:-\d{2,4})?-", "", slug)
            nome = slug_limpo.replace("-", " ").strip().title()
            return nome or "Competição"
        return "Competição"

    @staticmethod
    def _normalizar_evento_espn(evento):
        try:
            competicoes = evento.get("competitions") or []
            if not competicoes:
                return None
            competicao = competicoes[0]
            concorrentes = competicao.get("competitors") or []
            if len(concorrentes) < 2:
                return None

            casa = next((c for c in concorrentes if c.get("homeAway") == "home"), concorrentes[0])
            fora = next((c for c in concorrentes if c.get("homeAway") == "away"), concorrentes[1])
            casa_team = casa.get("team") or {}
            fora_team = fora.get("team") or {}
            casa_nome = str(casa_team.get("displayName") or casa_team.get("name") or "").strip()
            fora_nome = str(fora_team.get("displayName") or fora_team.get("name") or "").strip()
            if not casa_nome or not fora_nome:
                return None

            data_iso = evento.get("date") or competicao.get("date")
            timestamp = BuscadorJogosReais._iso_para_timestamp(data_iso)
            status_obj = evento.get("status") or {}
            status_type = status_obj.get("type") or {}
            state = str(status_type.get("state") or "unknown").lower()
            mapa_estado = {"pre": "notstarted", "in": "live", "post": "finished"}
            estado = mapa_estado.get(state, state or "unknown")

            def _id(team):
                try:
                    return int(team.get("id"))
                except (TypeError, ValueError):
                    return None

            return {
                "id": int(evento["id"]),
                "casa": casa_nome,
                "fora": fora_nome,
                "casa_id": _id(casa_team),
                "fora_id": _id(fora_team),
                "liga": BuscadorJogosReais._nome_liga_espn(evento, competicao),
                "season_slug": BuscadorJogosReais._season_slug_espn(evento),
                "pais": "",
                "horario": BuscadorJogosReais._hora_lisboa_timestamp(timestamp),
                "timestamp": timestamp,
                "status": estado,
                "prioridade": 0,
                "fonte": "ESPN",
            }
        except (KeyError, TypeError, ValueError):
            return None

    def _get_espn(self, league, data_compacta):
        """Pedido ESPN sem User-Agent customizado: usa o identificador normal do requests."""
        url = f"{self.ESPN_BASE}/{league}/scoreboard"
        resposta = self.espn_session.get(
            url,
            params={"dates": data_compacta},
            timeout=20,
        )
        self.espn_http_status = getattr(resposta, "status_code", None)
        self.ultimo_http_status = self.espn_http_status
        resposta.raise_for_status()
        dados = resposta.json()
        if not isinstance(dados, dict):
            raise ValueError("Resposta ESPN inválida.")
        eventos = dados.get("events")
        if not isinstance(eventos, list):
            raise ValueError("Lista ESPN ausente.")
        self._espn_respondeu = True
        return eventos

    def _normalizar_lista_espn(self, eventos, ids=None):
        ids = ids if ids is not None else set()
        jogos = []
        for evento in eventos:
            jogo = self._normalizar_evento_espn(evento)
            if jogo is None or jogo["id"] in ids:
                continue
            ids.add(jogo["id"])
            jogos.append(jogo)
        return jogos

    def _buscar_espn(self, data_iso):
        data_compacta = data_iso.replace("-", "")
        self.espn_http_status = None
        self._espn_respondeu = False

        ids = set()
        jogos = []
        erro_global = None

        try:
            eventos = self._get_espn("all", data_compacta)
            jogos.extend(self._normalizar_lista_espn(eventos, ids))
            if jogos:
                return jogos
        except (requests.RequestException, RuntimeError, ValueError, TypeError) as exc:
            erro_global = exc

        # Se /all falhar ou vier vazio, tenta ligas principais individualmente.
        respostas_validas = 0
        for league in self.ESPN_LEAGUES:
            try:
                eventos = self._get_espn(league, data_compacta)
                respostas_validas += 1
                jogos.extend(self._normalizar_lista_espn(eventos, ids))
            except (requests.RequestException, RuntimeError, ValueError, TypeError):
                continue

        if jogos:
            return jogos
        if respostas_validas > 0:
            self._espn_respondeu = True
            return []
        if erro_global is not None:
            raise ValueError("Fonte ESPN indisponível.") from None
        return []

    @staticmethod
    def _headers_sofa():
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            "Origin": "https://www.sofascore.com",
            "Referer": "https://www.sofascore.com/",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _aquecer_sofa(self):
        if self._sofa_aquecida or not self.browser_mode:
            return
        self._sofa_aquecida = True
        try:
            self.sofa_session.get(
                self.SOFA_SITE_URL,
                impersonate="chrome",
                headers={"Accept": "text/html,application/xhtml+xml,*/*"},
                timeout=15,
            )
        except Exception:
            pass

    def _get_sofa(self, path):
        url = f"{self.SOFA_BASE_URL}{path}"
        try:
            if self.browser_mode:
                self._aquecer_sofa()
                resposta = self.sofa_session.get(
                    url,
                    impersonate="chrome",
                    headers=self._headers_sofa(),
                    timeout=20,
                )
            else:
                resposta = self.sofa_session.get(
                    url,
                    headers={
                        **self._headers_sofa(),
                        "User-Agent": "Mozilla/5.0 Chrome/146.0 Safari/537.36",
                    },
                    timeout=20,
                )
            self.sofa_http_status = getattr(resposta, "status_code", None)
            self.ultimo_http_status = self.sofa_http_status
            resposta.raise_for_status()
            dados = resposta.json()
            if not isinstance(dados, dict):
                raise ValueError("Resposta SofaScore inválida.")
            return dados
        except Exception:
            raise ValueError("Fonte SofaScore indisponível.") from None

    @staticmethod
    def _normalizar_evento_sofa(evento):
        try:
            casa = evento["homeTeam"]
            fora = evento["awayTeam"]
            torneio = evento.get("tournament") or {}
            unico = torneio.get("uniqueTournament") or {}
            categoria = torneio.get("category") or {}
            status = evento.get("status") or {}
            return {
                "id": int(evento["id"]),
                "casa": str(casa["name"]).strip(),
                "fora": str(fora["name"]).strip(),
                "casa_id": int(casa["id"]),
                "fora_id": int(fora["id"]),
                "liga": str(unico.get("name") or torneio.get("name") or "Competição").strip(),
                "pais": str(categoria.get("name") or "").strip(),
                "horario": BuscadorJogosReais._hora_lisboa_timestamp(evento.get("startTimestamp")),
                "timestamp": evento.get("startTimestamp"),
                "status": str(status.get("type") or "unknown"),
                "prioridade": int(torneio.get("priority") or 0),
                "fonte": "SofaScore",
            }
        except (KeyError, TypeError, ValueError):
            return None

    def _buscar_sofa(self, data_iso):
        self.sofa_http_status = None
        try:
            dados = self._get_sofa(f"/sport/football/scheduled-events/{data_iso}/inverse")
        except ValueError:
            dados = self._get_sofa(f"/sport/football/scheduled-events/{data_iso}")
        eventos = dados.get("events")
        if not isinstance(eventos, list):
            raise ValueError("Lista SofaScore ausente.")

        jogos = []
        ids = set()
        for evento in eventos:
            jogo = self._normalizar_evento_sofa(evento)
            if jogo is None or jogo["id"] in ids:
                continue
            ids.add(jogo["id"])
            jogos.append(jogo)
        return jogos

    @staticmethod
    def _ordenar(jogos):
        jogos.sort(
            key=lambda j: (
                j["timestamp"] if isinstance(j.get("timestamp"), (int, float)) else 10**15,
                -int(j.get("prioridade") or 0),
                str(j.get("liga") or "").casefold(),
                str(j.get("casa") or "").casefold(),
            )
        )
        return jogos

    def buscar_todos_jogos_hoje(self, data_iso=None):
        if not self.enabled:
            self.estado = "desativado"
            self.ultimo_total = 0
            return []

        data_iso = data_iso or datetime.now(ZoneInfo("Europe/Lisbon")).strftime("%Y-%m-%d")
        self._espn_respondeu = False
        self.espn_http_status = None
        self.sofa_http_status = None

        try:
            jogos = self._ordenar(self._buscar_espn(data_iso))
            if jogos:
                self.estado = "operacional"
                self.fonte = "ESPN"
                self.ultimo_total = len(jogos)
                return jogos
        except (requests.RequestException, RuntimeError, ValueError, TypeError):
            pass

        try:
            jogos = self._ordenar(self._buscar_sofa(data_iso))
            if jogos:
                self.estado = "operacional"
                self.fonte = "SofaScore"
                self.ultimo_total = len(jogos)
                return jogos
        except (ValueError, TypeError):
            pass

        if self._espn_respondeu:
            self.estado = "operacional"
            self.fonte = "ESPN"
            self.ultimo_total = 0
            return []

        self.estado = "indisponível"
        self.fonte = None
        self.ultimo_total = 0
        return []

    def obter_forma_time(self, team_id):
        if type(team_id) is not int or team_id <= 0:
            return None
        return None

    def formatar_jogos(self, jogos, limite=40):
        if not jogos:
            if self.estado == "operacional":
                return "ℹ️ A ESPN respondeu corretamente, mas não encontrei jogos de futebol para hoje."
            diagnostico = []
            if self.espn_http_status is not None:
                diagnostico.append(f"ESPN HTTP {self.espn_http_status}")
            if self.sofa_http_status is not None:
                diagnostico.append(f"SofaScore HTTP {self.sofa_http_status}")
            extra = f" Diagnóstico: {'; '.join(diagnostico)}." if diagnostico else ""
            return (
                "⚠️ Não consegui obter jogos reais das fontes disponíveis neste momento. "
                "Não foram usados jogos de substituição." + extra
            )

        visiveis = jogos[:limite]
        fonte = str(visiveis[0].get("fonte") or self.fonte or "dados reais")
        linhas = [
            f"⚽ JOGOS REAIS — {fonte.upper()}",
            f"Encontrados: {len(jogos)} | A mostrar: {len(visiveis)}",
            "",
        ]
        liga_anterior = None
        for jogo in visiveis:
            liga = nome_liga_pt(jogo.get("liga") or "Competição")
            if liga != liga_anterior:
                pais = f" — {jogo['pais']}" if jogo.get("pais") else ""
                linhas.append(f"🏆 {liga}{pais}")
                liga_anterior = liga
            estado = jogo.get("status")
            sufixo = "" if estado in ("notstarted", "scheduled", "pre", "unknown") else f" [{estado}]"
            linhas.append(f"• {jogo['horario']}  {jogo['casa']} vs {jogo['fora']}{sufixo}")

        if len(jogos) > limite:
            linhas.extend(["", f"… e mais {len(jogos) - limite} jogos."])
        linhas.extend(
            [
                "",
                f"Fonte: {fonte}. Sem odds nesta listagem.",
                "Se as fontes falharem, o bot não inventa jogos.",
            ]
        )
        return "\n".join(linhas)
