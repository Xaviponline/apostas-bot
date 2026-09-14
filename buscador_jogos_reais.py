"""Conector de leitura para jogos reais.

Fonte principal: ESPN scoreboard público, sem chave API.
Fallback: SofaScore, quando acessível.
Nunca inventa jogos nem odds; se ambas as fontes falharem devolve lista vazia.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os
import re
import requests

try:
    from curl_cffi import requests as browser_requests
except ImportError:
    browser_requests = None


class BuscadorJogosReais:
    ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
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
    def _nome_liga_espn(evento, competicao):
        candidatos = [
            (evento.get("league") or {}).get("name") if isinstance(evento.get("league"), dict) else None,
            (competicao.get("league") or {}).get("name") if isinstance(competicao.get("league"), dict) else None,
            (evento.get("season") or {}).get("name") if isinstance(evento.get("season"), dict) else None,
        ]
        for valor in candidatos:
            if isinstance(valor, str) and valor.strip():
                return valor.strip()

        season = evento.get("season") or {}
        slug = season.get("slug") if isinstance(season, dict) else None
        if isinstance(slug, str) and slug.strip():
            slug = re.sub(r"^\d{4}(?:-\d{2,4})?-", "", slug.strip())
            nome = slug.replace("-", " ").strip().title()
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
            mapa_estado = {
                "pre": "notstarted",
                "in": "live",
                "post": "finished",
            }
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
                "pais": "",
                "horario": BuscadorJogosReais._hora_lisboa_timestamp(timestamp),
                "timestamp": timestamp,
                "status": estado,
                "prioridade": 0,
                "fonte": "ESPN",
            }
        except (KeyError, TypeError, ValueError):
            return None

    def _buscar_espn(self, data_iso):
        data_compacta = data_iso.replace("-", "")
        self.ultimo_http_status = None
        resposta = self.espn_session.get(
            self.ESPN_URL,
            params={"dates": data_compacta},
            headers={
                "Accept": "application/json",
                "User-Agent": "apostas-bot/1.0",
            },
            timeout=20,
        )
        self.ultimo_http_status = getattr(resposta, "status_code", None)
        resposta.raise_for_status()
        dados = resposta.json()
        if not isinstance(dados, dict):
            raise ValueError("Resposta ESPN inválida.")
        eventos = dados.get("events")
        if not isinstance(eventos, list):
            raise ValueError("Lista ESPN ausente.")

        self._espn_respondeu = True
        jogos = []
        ids = set()
        for evento in eventos:
            jogo = self._normalizar_evento_espn(evento)
            if jogo is None or jogo["id"] in ids:
                continue
            ids.add(jogo["id"])
            jogos.append(jogo)
        return jogos

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
        self.ultimo_http_status = None
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
            self.ultimo_http_status = getattr(resposta, "status_code", None)
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

        try:
            jogos = self._ordenar(self._buscar_espn(data_iso))
            if jogos:
                self.estado = "operacional"
                self.fonte = "ESPN"
                self.ultimo_total = len(jogos)
                return jogos
        except (requests.RequestException, ValueError, TypeError):
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
        """Reservado para a fase estatística. Nunca devolve dados inventados."""
        if type(team_id) is not int or team_id <= 0:
            return None
        return None

    def formatar_jogos(self, jogos, limite=40):
        if not jogos:
            if self.estado == "operacional":
                return "ℹ️ A fonte respondeu corretamente, mas não encontrei jogos de futebol para hoje."
            return (
                "⚠️ Não consegui obter jogos reais das fontes disponíveis neste momento. "
                "Não foram usados jogos de substituição."
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
            liga = jogo.get("liga") or "Competição"
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
                f"Fonte: {fonte}. Sem odds Betano nesta listagem.",
                "Se as fontes falharem, o bot não inventa jogos.",
            ]
        )
        return "\n".join(linhas)
