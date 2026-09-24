"""Fontes opcionais de odds Betano.

Fonte preferida: OddsPapi (Betano PT), por suportar plano gratuito.
Fallback legado: Odds-API.io.
As chaves são lidas apenas de variáveis de ambiente e nunca devem ser guardadas no GitHub.
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from time import monotonic, sleep
from zoneinfo import ZoneInfo
import requests


class OddsPapiQuotaEsgotada(RuntimeError):
    pass


class OddsPapiRateLimit(RuntimeError):
    pass


class OddsBetano:
    PAPI_BASE_URL = "https://api.oddspapi.io/v4"
    LEGACY_BASE_URL = "https://api.odds-api.io/v3"
    # A documentação/medições do OddsPapi mostram rate limit por endpoint.
    # Para /odds, ~1 pedido/segundo evita rajadas de 429.
    PAPI_ODDS_INTERVALO = 1.05
    PAPI_FIXTURES_INTERVALO = 1.05
    PAPI_BATCH_INTERVALO = 1.05
    PAPI_ACCOUNT_INTERVALO = 1.05
    PAPI_EVENTOS_CACHE_SEG = 3 * 60 * 60
    PAPI_MAX_TENTATIVAS_429 = 3

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
        self.ultimo_erro_evento = {}
        self.ultimo_diagnostico_eventos = ""
        self._papi_proximo_pedido = {}
        self._eventos_cache = None
        self._eventos_cache_expira = 0.0

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

    def diagnostico_evento(self, event_id):
        """Devolve apenas um motivo técnico seguro; nunca inclui chave ou payload."""
        return str(self.ultimo_erro_evento.get(str(event_id)) or "")

    @staticmethod
    def _motivo_excecao(exc):
        if isinstance(exc, OddsPapiQuotaEsgotada):
            return "odds_quota_esgotada"
        if isinstance(exc, OddsPapiRateLimit):
            return "odds_rate_limit_429"
        if isinstance(exc, requests.Timeout):
            return "odds_timeout"
        if isinstance(exc, requests.ConnectionError):
            return "odds_ligacao_indisponivel"
        if isinstance(exc, requests.HTTPError):
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
            return f"odds_http_{status}" if status else "odds_http_erro"
        if isinstance(exc, requests.RequestException):
            return "odds_rede_indisponivel"
        if isinstance(exc, (ValueError, TypeError)):
            return "odds_resposta_invalida"
        return "odds_erro_tecnico"

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

    @staticmethod
    def _retry_429_segundos(response, tentativa):
        """Extrai retry seguro do 429, sem depender do texto do erro."""
        espera = 1.05 * (tentativa + 1)
        try:
            headers = getattr(response, "headers", {}) or {}
            retry_after = headers.get("Retry-After")
            if retry_after is not None:
                espera = max(espera, float(retry_after))
        except (TypeError, ValueError):
            pass

        try:
            corpo = response.json()
        except (TypeError, ValueError, AttributeError):
            corpo = {}
        if isinstance(corpo, dict):
            erro = corpo.get("error") if isinstance(corpo.get("error"), dict) else {}
            retry_ms = erro.get("retryMs") or corpo.get("retryMs")
            try:
                if retry_ms is not None:
                    espera = max(espera, float(retry_ms) / 1000.0)
            except (TypeError, ValueError):
                pass
        return min(max(espera, 0.05), 10.0)

    @staticmethod
    def _codigo_429(response):
        try:
            corpo = response.json()
        except (TypeError, ValueError, AttributeError):
            return ""
        if not isinstance(corpo, dict):
            return ""
        erro = corpo.get("error") if isinstance(corpo.get("error"), dict) else {}
        return str(erro.get("code") or corpo.get("code") or "").strip().upper()

    def _intervalo_papi(self, path):
        if path == "/odds":
            return self.PAPI_ODDS_INTERVALO
        if path == "/fixtures":
            return self.PAPI_FIXTURES_INTERVALO
        if path == "/odds-by-tournaments":
            return self.PAPI_BATCH_INTERVALO
        if path == "/account":
            return self.PAPI_ACCOUNT_INTERVALO
        return 0.0

    def _esperar_cooldown_papi(self, path):
        agora = monotonic()
        pronto = float(self._papi_proximo_pedido.get(path) or 0.0)
        if pronto > agora:
            sleep(pronto - agora)

    def _marcar_cooldown_papi(self, path, segundos=None):
        intervalo_base = self._intervalo_papi(path)
        if intervalo_base <= 0 and segundos is None:
            return
        intervalo = intervalo_base if segundos is None else float(segundos)
        self._papi_proximo_pedido[path] = monotonic() + max(intervalo, 0.0)

    def _get_papi(self, path, params):
        if not self.papi_key:
            raise ValueError("ODDS_PAPI_KEY não configurada.")
        params = dict(params)
        params["apiKey"] = self.papi_key
        tentativas = self.PAPI_MAX_TENTATIVAS_429 if path in {"/odds", "/fixtures", "/odds-by-tournaments", "/account"} else 1

        ultimo = None
        for tentativa in range(tentativas):
            self._esperar_cooldown_papi(path)
            r = self.session.get(
                f"{self.PAPI_BASE_URL}{path}",
                params=params,
                headers={"Accept": "application/json"},
                timeout=(5, 25),
            )
            ultimo = r
            self._marcar_cooldown_papi(path)

            if getattr(r, "status_code", None) != 429:
                r.raise_for_status()
                return r.json()

            # REQUEST_LIMIT_EXCEEDED é cota do plano, não cooldown. Não vale
            # esperar e repetir porque o resultado continuará 429.
            if self._codigo_429(r) == "REQUEST_LIMIT_EXCEEDED":
                raise OddsPapiQuotaEsgotada()

            if tentativa + 1 >= tentativas:
                raise OddsPapiRateLimit()

            espera = self._retry_429_segundos(r, tentativa)
            self._marcar_cooldown_papi(path, espera)

        if ultimo is not None:
            ultimo.raise_for_status()
        raise RuntimeError("Falha inesperada na fonte OddsPapi.")

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

    @staticmethod
    def _fixture_ainda_futuro(fixture):
        try:
            valor = str((fixture or {}).get("startTime") or "").strip()
            if not valor:
                return False
            dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp() > datetime.now(timezone.utc).timestamp()
        except (TypeError, ValueError):
            return False

    def _eventos_papi(self):
        inicio, fim = self._janela_hoje_utc()
        # A descoberta dos jogos não deve depender de a Betano ter o mercado
        # aberto exatamente neste instante. Primeiro listamos todos os fixtures
        # pré-jogo e só depois consultamos /odds para a casa configurada.
        params = {
            "sportId": 10,
            "from": inicio,
            "to": fim,
            "statusId": 0,
            "language": "en",
        }
        dados = self._get_papi("/fixtures", params)
        if not isinstance(dados, list):
            raise ValueError("Resposta de fixtures OddsPapi inválida.")

        total_status0 = len(dados)
        usou_fallback = False
        if not dados:
            # O estado dos fixtures mudou de semântica entre versões/documentação
            # da fonte. Sem resultados com statusId=0, repetimos sem esse filtro
            # e fazemos a proteção pré-jogo pelo startTime no nosso lado.
            params_sem_status = dict(params)
            params_sem_status.pop("statusId", None)
            dados = self._get_papi("/fixtures", params_sem_status)
            if not isinstance(dados, list):
                raise ValueError("Resposta de fixtures OddsPapi inválida.")
            usou_fallback = True

        candidatos = dados
        if usou_fallback:
            candidatos = [e for e in dados if self._fixture_ainda_futuro(e)]

        eventos = []
        for e in candidatos:
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

        self.ultimo_diagnostico_eventos = (
            f"status0={total_status0}; fallback={int(usou_fallback)}; "
            f"sem_status={len(dados) if usou_fallback else '-'}; futuros={len(eventos)}"
        )
        logging.info("ODDS_DISCOVERY | %s", self.ultimo_diagnostico_eventos)
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

        if self.provider == "oddspapi":
            agora = monotonic()
            if self._eventos_cache is not None and agora < self._eventos_cache_expira:
                logging.info("ODDS_DISCOVERY | cache=%s", len(self._eventos_cache))
                return list(self._eventos_cache)

        try:
            eventos = self._eventos_papi() if self.provider == "oddspapi" else self._eventos_legacy()
            self.estado = "operacional"
            if self.provider == "oddspapi":
                self._eventos_cache = list(eventos)
                self._eventos_cache_expira = monotonic() + self.PAPI_EVENTOS_CACHE_SEG
            return eventos
        except (requests.RequestException, ValueError, TypeError, RuntimeError) as exc:
            self.estado = "indisponível"
            if self.provider == "oddspapi":
                self.ultimo_diagnostico_eventos = self._motivo_excecao(exc)
                logging.info("ODDS_DISCOVERY | %s", self.ultimo_diagnostico_eventos)
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

    def _normalizar_odds_papi(self, dados):
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
        except (requests.RequestException, ValueError, TypeError, RuntimeError):
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
        return self._normalizar_odds_papi(dados)

    def odds_eventos_em_lote(self, eventos):
        """Obtém odds de vários fixtures OddsPapi em uma chamada por conjunto de torneios."""
        if self.provider != "oddspapi":
            return {}

        eventos = [e for e in (eventos or []) if isinstance(e, dict)]
        ids_evento = {
            str(e.get("id"))
            for e in eventos
            if e.get("id") not in (None, "")
        }
        torneios = sorted(
            {
                int(e.get("tournament_id"))
                for e in eventos
                if e.get("tournament_id") not in (None, "")
            }
        )
        if not ids_evento or not torneios:
            return {}

        try:
            dados = self._get_papi(
                "/odds-by-tournaments",
                {
                    "tournamentIds": ",".join(str(t) for t in torneios),
                    "bookmakers": self.papi_bookmaker,
                    "oddsFormat": "decimal",
                    "language": "en",
                    "verbosity": 3,
                },
            )
            if isinstance(dados, list):
                itens = dados
            elif isinstance(dados, dict) and isinstance(dados.get("fixtures"), list):
                itens = dados.get("fixtures") or []
            elif isinstance(dados, dict) and dados.get("fixtureId") is not None:
                itens = [dados]
            else:
                raise ValueError("Resposta OddsPapi em lote inválida.")

            saida = {}
            for item in itens:
                if not isinstance(item, dict):
                    continue
                fixture_id = str(item.get("fixtureId") or "")
                if fixture_id not in ids_evento:
                    continue
                saida[fixture_id] = self._normalizar_odds_papi(item)

            for fixture_id in ids_evento:
                if fixture_id not in saida:
                    self.ultimo_erro_evento[fixture_id] = "betano_sem_odds_no_evento"
                    saida[fixture_id] = None

            logging.info(
                "ODDS_BATCH | torneios=%s | fixtures=%s | respostas=%s",
                len(torneios),
                len(ids_evento),
                sum(1 for v in saida.values() if v is not None),
            )
            return saida
        except (requests.RequestException, ValueError, TypeError, RuntimeError) as exc:
            motivo = self._motivo_excecao(exc)
            for fixture_id in ids_evento:
                self.ultimo_erro_evento[fixture_id] = motivo
            logging.info("ODDS_BATCH | falha=%s | fixtures=%s", motivo, len(ids_evento))
            return {fixture_id: None for fixture_id in ids_evento}

    def status_conta(self):
        """Resumo seguro da quota OddsPapi; nunca devolve a api_key."""
        if self.provider != "oddspapi" or not self.papi_key:
            return None
        dados = self._get_papi("/account", {})
        if not isinstance(dados, dict):
            raise ValueError("Resposta de conta OddsPapi inválida.")

        subs = [s for s in (dados.get("subscriptions") or []) if isinstance(s, dict)]
        atual_id = str(dados.get("current_subscription_id") or "")
        atual = next(
            (s for s in subs if str(s.get("subscription_id") or "") == atual_id),
            None,
        )
        if atual is None:
            atual = next((s for s in subs if s.get("is_active") is True), None)
        if atual is None and subs:
            atual = subs[0]
        if not isinstance(atual, dict):
            return None

        try:
            usados = int(atual.get("request_count") or 0)
            limite = int(atual.get("request_limit") or 0)
        except (TypeError, ValueError):
            usados = limite = 0

        restante = max(limite - usados, 0) if limite > 0 else None
        if restante == 0 and limite > 0:
            self.ultimo_diagnostico_eventos = "odds_quota_esgotada"
        elif restante is not None and restante > 0:
            self.ultimo_diagnostico_eventos = ""

        return {
            "request_count": usados,
            "request_limit": limite,
            "remaining": restante,
            "is_active": bool(atual.get("is_active", False)),
            "valid_from": atual.get("valid_from"),
            "valid_until": atual.get("valid_until"),
            "auto_renew": bool(atual.get("auto_renew", False)),
            "last_request": atual.get("last_request"),
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
        chave = str(event_id)
        self.ultimo_erro_evento.pop(chave, None)
        if not self.configurada:
            self.estado = "não configurada"
            self.ultimo_erro_evento[chave] = "odds_fonte_nao_configurada"
            return None
        try:
            dados = (
                self._odds_evento_papi(event_id)
                if self.provider == "oddspapi"
                else self._odds_evento_legacy(event_id)
            )
            self.estado = "operacional" if dados else "sem odds"
            if dados is None:
                self.ultimo_erro_evento[chave] = "odds_evento_sem_resposta"
            return dados
        except (requests.RequestException, ValueError, TypeError, RuntimeError) as exc:
            self.estado = "indisponível"
            self.ultimo_erro_evento[chave] = self._motivo_excecao(exc)
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