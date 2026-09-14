"""Fonte opcional de odds Betano via Odds-API.io.

A Betano não expõe uma API pública; esta integração usa um agregador externo.
A chave é lida apenas de ODDS_API_IO_KEY e nunca deve ser guardada no GitHub.
"""
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests


class OddsBetano:
    BASE_URL = "https://api.odds-api.io/v3"

    def __init__(self, api_key=None, session=None):
        self.api_key = (api_key or os.getenv("ODDS_API_IO_KEY", "")).strip()
        self.session = session or requests.Session()
        self.estado = "configurada" if self.api_key else "não configurada"

    @property
    def configurada(self):
        return bool(self.api_key)

    def _get(self, path, params):
        if not self.api_key:
            raise ValueError("ODDS_API_IO_KEY não configurada.")
        params = dict(params)
        params["apiKey"] = self.api_key
        r = self.session.get(
            f"{self.BASE_URL}{path}",
            params=params,
            headers={"Accept": "application/json"},
            timeout=(5, 20),
        )
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _janela_hoje_utc():
        tz = ZoneInfo("Europe/Lisbon")
        inicio_local = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        fim_local = inicio_local + timedelta(days=1)
        return (
            inicio_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            fim_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    def eventos_hoje(self):
        if not self.api_key:
            self.estado = "não configurada"
            return []
        inicio, fim = self._janela_hoje_utc()
        try:
            dados = self._get(
                "/events",
                {
                    "sport": "football",
                    "bookmaker": "Betano",
                    "status": "pending",
                    "from": inicio,
                    "to": fim,
                },
            )
            if not isinstance(dados, list):
                raise ValueError("Resposta de eventos inválida.")
            eventos = []
            for e in dados:
                try:
                    eventos.append(
                        {
                            "id": int(e["id"]),
                            "casa": str(e["home"]).strip(),
                            "fora": str(e["away"]).strip(),
                            "data": str(e["date"]).strip(),
                            "liga": str((e.get("league") or {}).get("name") or "Competição").strip(),
                            "status": str(e.get("status") or "pending"),
                        }
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            self.estado = "operacional"
            return eventos
        except (requests.RequestException, ValueError, TypeError):
            self.estado = "indisponível"
            return []

    def odds_evento(self, event_id):
        if not self.api_key:
            self.estado = "não configurada"
            return None
        try:
            dados = self._get(
                "/odds",
                {"eventId": str(int(event_id)), "bookmakers": "Betano"},
            )
            if not isinstance(dados, dict):
                raise ValueError("Resposta de odds inválida.")
            mercados = (dados.get("bookmakers") or {}).get("Betano")
            if not isinstance(mercados, list):
                return None
            return {
                "id": dados.get("id"),
                "casa": dados.get("home"),
                "fora": dados.get("away"),
                "liga": (dados.get("league") or {}).get("name"),
                "mercados": mercados,
            }
        except (requests.RequestException, ValueError, TypeError):
            self.estado = "indisponível"
            return None

    @staticmethod
    def formatar_eventos(eventos, limite=20):
        if not eventos:
            return "Sem eventos Betano disponíveis para hoje ou fonte não configurada."
        linhas = ["💶 EVENTOS BETANO — HOJE", ""]
        for e in eventos[:limite]:
            linhas.append(f"• ID {e['id']} — {e['casa']} vs {e['fora']} — {e['liga']}")
        if len(eventos) > limite:
            linhas.append(f"… e mais {len(eventos)-limite} eventos.")
        linhas.extend(["", "Usa /odds ID para consultar as odds desse evento."])
        return "\n".join(linhas)

    @staticmethod
    def formatar_odds(dados):
        if not dados:
            return "Não foi possível obter odds Betano para esse evento."
        linhas = [
            f"💶 BETANO — {dados.get('casa')} vs {dados.get('fora')}",
            f"🏆 {dados.get('liga') or 'Competição'}",
            "",
        ]
        for mercado in dados.get("mercados", []):
            nome = str(mercado.get("name") or "Mercado")
            atualizado = str(mercado.get("updatedAt") or "")
            linhas.append(f"• {nome}" + (f" (atualizado {atualizado})" if atualizado else ""))
            for odd in (mercado.get("odds") or [])[:12]:
                if isinstance(odd, dict):
                    partes = [f"{k}={v}" for k, v in odd.items()]
                    linhas.append("  " + " | ".join(partes))
        linhas.extend(["", "Fonte externa: Odds-API.io. Confirma sempre na Betano antes de apostar."])
        return "\n".join(linhas)
