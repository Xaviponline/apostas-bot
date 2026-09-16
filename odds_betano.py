"""Fontes opcionais de odds Betano.

Fonte preferida: OddsPapi (Betano PT), por suportar plano gratuito.
Fallback legado: Odds-API.io.
As chaves são lidas apenas de variáveis de ambiente e nunca devem ser guardadas no GitHub.
"""
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests


class OddsBetano:
    PAPI_BASE_URL = "https://api.oddspapi.io/v4"
    LEGACY_BASE_URL = "https://api.odds-api.io/v3"

    def __init__(self, api_key=None, session=None, papi_key=None, provider=None):
        self.session = session or requests.Session()
        self.papi_key = (
            papi_key if papi_key is not None else os.getenv("ODDS_PAPI_KEY", "")
        ).strip()
        self.legacy_key = (
            api_key if api_key is not None else os.getenv("ODDS_API_IO_KEY", "")
        ).strip()
        self.papi_bookmaker = os.getenv("ODDS_PAPI_BOOKMAKER", "betano.pt").strip() or "betano.pt"
        self._catalogo_mercados = None

        if provider:
            self.provider = provider
        elif papi_key is not None:
            self.provider = "oddspapi" if self.papi_key else None
        elif api_key is not None:
            self.provider = "odds-api.io" if self.legacy_key else None
        elif self.papi_key:
            self.provider = "oddspapi"
        elif self.legacy_key:
            self.provider = "odds-api.io"
        else:
            self.provider = None

        self.api_key = self.papi_key if self.provider == "oddspapi" else self.legacy_key
        self.estado = "configurada" if self.configurada else "não configurada"

    @property
    def configurada(self):
        return bool(self.provider and self.api_key)

    @property
    def nome_fonte(self):
        if self.provider == "oddspapi":
            return "OddsPapi / Betano PT"
        if self.provider == "odds-api.io":
            return "Odds-API.io / Betano"
        return "não configurada"

    def _get_legacy(self, path, params):
        if not self.legacy_key:
            raise ValueError("ODDS_API_IO_KEY não configurada.")
        params = dict(params)
        params["apiKey"] = self.legacy_key
        r = self.session.get(
            f"{self.LEGACY_BASE_URL}{path}",
            params=params,
            headers={"Accept": "application/json"},
            timeout=(5, 20),
        )
        r.raise_for_status()
        return r.json()

    def _get_papi(self, path, params):
        if not self.papi_key:
            raise ValueError("ODDS_PAPI_KEY não configurada.")
        params = dict(params)
        params["apiKey"] = self.papi_key
        r = self.session.get(
            f"{self.PAPI_BASE_URL}{path}",
            params=params,
            headers={"Accept": "application/json"},
            timeout=(5, 25),
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

    @staticmethod
    def _numero_ou_none(valor):
        if valor is None or isinstance(valor, bool):
            return None
        try:
            return float(valor)
        except (TypeError, ValueError):
            return None

    def _eventos_papi(self):
        inicio, fim = self._janela_hoje_utc()
        # A descoberta dos jogos não deve depender de a Betano ter o mercado
        # aberto exatamente neste instante. Primeiro listamos todos os fixtures
        # pré-jogo e só depois consultamos /odds para a casa configurada.
        dados = self._get_papi(
            "/fixtures",
            {
                "sportId": 10,
                "from": inicio,
                "to": fim,
                "statusId": 0,
                "language": "en",
            },
        )
        if not isinstance(dados, list):
            raise ValueError("Resposta de fixtures OddsPapi inválida.")
        eventos = []
        for e in dados:
            try:
                eventos.append(
                    {
                        "id": str(e["fixtureId"]),
                        "casa": str(e["participant1Name"]).strip(),
                        "fora": str(e["participant2Name"]).strip(),
                        "data": str(e["startTime"]).strip(),
                        "liga": str(e.get("tournamentName") or "Competição").strip(),
                        "status": str(e.get("statusName") or "Pre-Game"),
                        "tournament_id": int(e["tournamentId"]),
                        "has_odds": bool(e.get("hasOdds", False)),
                        "participant1_id": e.get("participant1Id"),
                        "participant2_id": e.get("participant2Id"),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        return eventos

    def _eventos_legacy(self):
        inicio, fim = self._janela_hoje_utc()
        dados = self._get_legacy(
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
        return eventos

    def eventos_hoje(self):
        if not self.configurada:
            self.estado = "não configurada"
            return []
        try:
            eventos = self._eventos_papi() if self.provider == "oddspapi" else self._eventos_legacy()
            self.estado = "operacional"
            return eventos
        except (requests.RequestException, ValueError, TypeError):
            self.estado = "indisponível"
            return []

    def _catalogo_papi(self):
        if self._catalogo_mercados is not None:
            return self._catalogo_mercados
        dados = self._get_papi("/markets", {"language": "en"})
        if not isinstance(dados, list):
            self._catalogo_mercados = {}
            return self._catalogo_mercados
        catalogo = {}
        for mercado in dados:
            try:
                mid = str(mercado["marketId"])
                outcomes = {
                    str(o["outcomeId"]): str(o.get("outcomeName") or o["outcomeId"])
                    for o in (mercado.get("outcomes") or [])
                    if isinstance(o, dict) and "outcomeId" in o
                }
                catalogo[mid] = {
                    "name": str(mercado.get("marketName") or f"Market {mid}"),
                    "handicap": self._numero_ou_none(mercado.get("handicap")),
                    "period": str(mercado.get("period") or "").strip(),
                    "marketType": str(mercado.get("marketType") or "").strip(),
                    "playerProp": bool(mercado.get("playerProp", False)),
                    "outcomes": outcomes,
                }
            except (KeyError, TypeError, ValueError):
                continue
        self._catalogo_mercados = catalogo
        return catalogo

    def _odds_evento_papi(self, event_id):
        dados = self._get_papi(
            "/odds",
            {
                "fixtureId": str(event_id),
                "bookmakers": self.papi_bookmaker,
                "oddsFormat": "decimal",
                "language": "en",
                "verbosity": 3,
            },
        )
        if not isinstance(dados, dict):
            raise ValueError("Resposta OddsPapi inválida.")
        book = (dados.get("bookmakerOdds") or {}).get(self.papi_bookmaker)
        if not isinstance(book, dict):
            return {
                "id": dados.get("fixtureId"),
                "casa": dados.get("participant1Name"),
                "fora": dados.get("participant2Name"),
                "liga": dados.get("tournamentName"),
                "updatedAt": dados.get("updatedAt") or "",
                "mercados": [],
                "bookmaker_disponivel": False,
                "fonte": self.nome_fonte,
            }

        try:
            catalogo = self._catalogo_papi()
        except (requests.RequestException, ValueError, TypeError):
            catalogo = {}

        mercados_saida = []
        for market_id, mercado in (book.get("markets") or {}).items():
            if not isinstance(mercado, dict) or not mercado.get("marketActive", True):
                continue
            meta = catalogo.get(str(market_id), {})
            odds_saida = []
            timestamps = []
            for outcome_id, outcome in (mercado.get("outcomes") or {}).items():
                if not isinstance(outcome, dict):
                    continue
                nome_outcome = (meta.get("outcomes") or {}).get(str(outcome_id), str(outcome_id))
                for player in (outcome.get("players") or {}).values():
                    if not isinstance(player, dict) or not player.get("active", True):
                        continue
                    price = player.get("price")
                    if price is None:
                        continue
                    item = {"seleção": nome_outcome, "odd": price}
                    if player.get("playerName"):
                        item["jogador"] = player.get("playerName")
                    if player.get("bookmakerOutcomeId"):
                        item["ref"] = player.get("bookmakerOutcomeId")
                    if "mainLine" in player:
                        item["mainLine"] = bool(player.get("mainLine"))
                    changed_at = str(player.get("changedAt") or "").strip()
                    bookmaker_changed_at = str(player.get("bookmakerChangedAt") or "").strip()
                    if changed_at:
                        item["changedAt"] = changed_at
                        timestamps.append(changed_at)
                    if bookmaker_changed_at:
                        item["bookmakerChangedAt"] = bookmaker_changed_at
                        timestamps.append(bookmaker_changed_at)
                    odds_saida.append(item)
            if odds_saida:
                atualizado = max(timestamps) if timestamps else str(dados.get("updatedAt") or "")
                mercados_saida.append(
                    {
                        "id": str(market_id),
                        "name": meta.get("name") or f"Market {market_id}",
                        "handicap": meta.get("handicap"),
                        "period": meta.get("period") or "",
                        "marketType": meta.get("marketType") or "",
                        "playerProp": bool(meta.get("playerProp", False)),
                        "updatedAt": atualizado,
                        "odds": odds_saida,
                    }
                )

        return {
            "id": dados.get("fixtureId"),
            "casa": dados.get("participant1Name"),
            "fora": dados.get("participant2Name"),
            "liga": dados.get("tournamentName"),
            "updatedAt": dados.get("updatedAt") or "",
            "mercados": mercados_saida,
            "bookmaker_disponivel": True,
            "fonte": self.nome_fonte,
        }

    def _odds_evento_legacy(self, event_id):
        dados = self._get_legacy(
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
            "fonte": self.nome_fonte,
        }

    def odds_evento(self, event_id):
        if not self.configurada:
            self.estado = "não configurada"
            return None
        try:
            dados = (
                self._odds_evento_papi(event_id)
                if self.provider == "oddspapi"
                else self._odds_evento_legacy(event_id)
            )
            self.estado = "operacional" if dados else "sem odds"
            return dados
        except (requests.RequestException, ValueError, TypeError):
            self.estado = "indisponível"
            return None

    @staticmethod
    def formatar_eventos(eventos, limite=20):
        if not eventos:
            return "Sem eventos disponíveis para hoje ou fonte não configurada."
        linhas = ["💶 EVENTOS DA FONTE DE ODDS — HOJE", ""]
        for e in eventos[:limite]:
            linhas.append(f"• ID {e['id']} — {e['casa']} vs {e['fora']} — {e['liga']}")
        if len(eventos) > limite:
            linhas.append(f"… e mais {len(eventos)-limite} eventos.")
        linhas.extend(["", "Usa /odds ID para consultar as odds Betano desse evento."])
        return "\n".join(linhas)

    @staticmethod
    def _formatar_linha(valor):
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return str(valor)
        return f"{numero:g}"

    @staticmethod
    def formatar_odds(dados):
        if not dados:
            return "Não foi possível obter odds Betano para esse evento."
        linhas = [
            f"💶 BETANO — {dados.get('casa')} vs {dados.get('fora')}",
            f"🏆 {dados.get('liga') or 'Competição'}",
            "",
        ]
        if dados.get("bookmaker_disponivel") is False:
            linhas.append("Betano sem odds disponíveis neste momento para este evento.")
            return "\n".join(linhas)
        for mercado in dados.get("mercados", []):
            nome = str(mercado.get("name") or "Mercado")
            atualizado = str(mercado.get("updatedAt") or "")
            meta = []
            handicap = mercado.get("handicap")
            if handicap not in (None, 0, 0.0, "0", "0.0"):
                meta.append(f"linha {OddsBetano._formatar_linha(handicap)}")
            periodo = str(mercado.get("period") or "").strip()
            if periodo and periodo.casefold() != "fulltime":
                meta.append(periodo)
            sufixo = f" — {', '.join(meta)}" if meta else ""
            if atualizado:
                sufixo += f" (atualizado {atualizado})"
            linhas.append(f"• {nome}{sufixo}")
            for odd in (mercado.get("odds") or [])[:12]:
                if isinstance(odd, dict):
                    if any(k in odd for k in ("seleção", "odd", "jogador", "ref", "mainLine")):
                        chaves = ["seleção", "odd", "jogador", "ref", "mainLine"]
                        partes = []
                        for chave in chaves:
                            if chave not in odd:
                                continue
                            valor = odd[chave]
                            if chave == "mainLine":
                                valor = "sim" if valor else "não"
                                chave = "principal"
                            partes.append(f"{chave}={valor}")
                    else:
                        partes = [f"{k}={v}" for k, v in odd.items()]
                    linhas.append("  " + " | ".join(partes))
        linhas.extend(["", f"Fonte externa: {dados.get('fonte') or 'agregador de odds'}. Confirma sempre na Betano antes de apostar."])
        return "\n".join(linhas)