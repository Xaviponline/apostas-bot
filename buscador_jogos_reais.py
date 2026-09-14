"""Conector de leitura para jogos reais do SofaScore.

Nunca inventa jogos nem odds. Em produção usa curl_cffi para imitar um navegador
real ao nível TLS/HTTP2, porque o SofaScore pode responder de forma diferente a
clientes HTTP de datacenter. Se a fonte falhar, devolve uma lista vazia.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os
import requests

try:
    from curl_cffi import requests as browser_requests
except ImportError:  # Mantém compatibilidade local; em produção está em requirements.txt.
    browser_requests = None


class BuscadorJogosReais:
    BASE_URL = "https://api.sofascore.com/api/v1"
    SITE_URL = "https://www.sofascore.com/"

    def __init__(self, session=None, enabled=None):
        self._session_injetada = session is not None
        if session is not None:
            self.session = session
            self.browser_mode = False
        elif browser_requests is not None:
            self.session = browser_requests.Session()
            self.browser_mode = True
        else:
            self.session = requests.Session()
            self.browser_mode = False

        self.enabled = (
            bool(session)
            if enabled is None and session is not None
            else (os.getenv("ENABLE_SOFASCORE", "0") == "1" if enabled is None else bool(enabled))
        )
        self.estado = "por validar" if self.enabled else "desativado"
        self.ultimo_total = 0
        self.ultimo_http_status = None
        self._aquecida = False

    @staticmethod
    def _headers_api():
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            "Origin": "https://www.sofascore.com",
            "Referer": "https://www.sofascore.com/",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _aquecer_sessao(self):
        """Obtém cookies de navegação antes da API; falha silenciosamente."""
        if self._aquecida or not self.browser_mode:
            return
        self._aquecida = True
        try:
            self.session.get(
                self.SITE_URL,
                impersonate="chrome",
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
                },
                timeout=15,
            )
        except Exception:
            # O pedido à API ainda pode funcionar sem o warm-up.
            pass

    def _get(self, path):
        url = f"{self.BASE_URL}{path}"
        self.ultimo_http_status = None
        try:
            if self.browser_mode:
                self._aquecer_sessao()
                resposta = self.session.get(
                    url,
                    impersonate="chrome",
                    headers=self._headers_api(),
                    timeout=20,
                )
            else:
                # Sessões injetadas são usadas nos testes; requests normal é fallback.
                resposta = self.session.get(
                    url,
                    headers={
                        **self._headers_api(),
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/146.0 Safari/537.36"
                        ),
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
            # Não expor HTML de challenge, cookies ou detalhes internos nos logs/Telegram.
            raise ValueError("Fonte SofaScore indisponível.") from None

    @staticmethod
    def _hora_lisboa(timestamp):
        if type(timestamp) not in (int, float):
            return "--:--"
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(
            ZoneInfo("Europe/Lisbon")
        )
        return dt.strftime("%H:%M")

    @staticmethod
    def _normalizar_evento(evento):
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
                "horario": BuscadorJogosReais._hora_lisboa(evento.get("startTimestamp")),
                "timestamp": evento.get("startTimestamp"),
                "status": str(status.get("type") or "unknown"),
                "prioridade": int(torneio.get("priority") or 0),
            }
        except (KeyError, TypeError, ValueError):
            return None

    def buscar_todos_jogos_hoje(self, data_iso=None):
        if not self.enabled:
            self.estado = "desativado"
            self.ultimo_total = 0
            return []
        data_iso = data_iso or datetime.now(
            ZoneInfo("Europe/Lisbon")
        ).strftime("%Y-%m-%d")
        try:
            # Primeiro tenta a lista completa usada pelo site ao selecionar "Show All".
            try:
                dados = self._get(f"/sport/football/scheduled-events/{data_iso}/inverse")
            except ValueError:
                dados = self._get(f"/sport/football/scheduled-events/{data_iso}")

            eventos = dados.get("events")
            if not isinstance(eventos, list):
                raise ValueError("Lista de eventos ausente.")
            jogos = []
            ids = set()
            for evento in eventos:
                jogo = self._normalizar_evento(evento)
                if jogo is None or jogo["id"] in ids:
                    continue
                ids.add(jogo["id"])
                jogos.append(jogo)
            jogos.sort(
                key=lambda j: (
                    j["timestamp"] if isinstance(j["timestamp"], (int, float)) else 10**15,
                    -j["prioridade"],
                    j["liga"].casefold(),
                    j["casa"].casefold(),
                )
            )
            self.estado = "operacional"
            self.ultimo_total = len(jogos)
            return jogos
        except (ValueError, TypeError):
            self.estado = "indisponível"
            self.ultimo_total = 0
            return []

    def obter_forma_time(self, team_id):
        """Reservado para a fase estatística. Nunca devolve dados inventados."""
        if type(team_id) is not int or team_id <= 0:
            return None
        return None

    @staticmethod
    def formatar_jogos(jogos, limite=40):
        if not jogos:
            return (
                "⚠️ Não consegui obter jogos reais do SofaScore neste momento. "
                "Não foram usados jogos de substituição."
            )
        visiveis = jogos[:limite]
        linhas = [
            "⚽ JOGOS REAIS — SOFASCORE",
            f"Encontrados: {len(jogos)} | A mostrar: {len(visiveis)}",
            "",
        ]
        liga_anterior = None
        for jogo in visiveis:
            liga = jogo["liga"]
            if liga != liga_anterior:
                pais = f" — {jogo['pais']}" if jogo.get("pais") else ""
                linhas.append(f"🏆 {liga}{pais}")
                liga_anterior = liga
            estado = jogo.get("status")
            sufixo = "" if estado in ("notstarted", "scheduled", "unknown") else f" [{estado}]"
            linhas.append(
                f"• {jogo['horario']}  {jogo['casa']} vs {jogo['fora']}{sufixo}"
            )
        if len(jogos) > limite:
            linhas.extend(["", f"… e mais {len(jogos) - limite} jogos."])
        linhas.extend(
            [
                "",
                "Fonte: SofaScore. Sem odds Betano nesta listagem.",
                "Se a fonte falhar, o bot não inventa jogos.",
            ]
        )
        return "\n".join(linhas)
