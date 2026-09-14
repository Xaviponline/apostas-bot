"""Conector de leitura para jogos reais do SofaScore.

Não inventa jogos nem odds. Se a fonte falhar, devolve uma lista vazia e guarda
apenas um estado genérico para diagnóstico (sem URLs/tokens em logs).
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests


class BuscadorJogosReais:
    BASE_URL = "https://api.sofascore.com/api/v1"

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.estado = "por validar"
        self.ultimo_total = 0

    def _get(self, path):
        resposta = self.session.get(
            f"{self.BASE_URL}{path}",
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0 Safari/537.36"
                ),
                "Origin": "https://www.sofascore.com",
                "Referer": "https://www.sofascore.com/",
            },
            timeout=(5, 20),
        )
        resposta.raise_for_status()
        dados = resposta.json()
        if not isinstance(dados, dict):
            raise ValueError("Resposta SofaScore inválida.")
        return dados

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
        data_iso = data_iso or datetime.now(
            ZoneInfo("Europe/Lisbon")
        ).strftime("%Y-%m-%d")
        try:
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
        except (requests.RequestException, ValueError, TypeError):
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
