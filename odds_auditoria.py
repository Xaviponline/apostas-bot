"""Liga previsões V1 a odds reais sem alterar a seleção do modelo.

A camada é deliberadamente conservadora: associa primeiro por nomes normalizados
exatos. Só usa um fallback controlado quando existe um único evento compatível e
os nomes são extensões inequívocas ou equivalências conhecidas entre fornecedores.
Se não houver correspondência segura, não guarda qualquer odd.
"""
import logging
import re
import unicodedata
from zoneinfo import ZoneInfo

from fixture_guard_shadow import categorias_incompativeis, juventude_confirmada_hoje
from odds_identidade_guard import (
    equipas_categoria_incompativel, verificar_hora_fixture, classificar_frescura,
)
from copy import deepcopy
from datetime import datetime, timezone


class AuditoriaOdds:
    TOKENS_CLUBE = {
        "fc", "cf", "afc", "ac", "sc", "ca", "cd", "ud", "rcd",
        "sl", "ss", "fk", "sk", "bk", "aif",
    }

    ALIASES_EQUIPA = {
        "athletic club": "athletic bilbao",
        "athletic bilbao": "athletic bilbao",
        "ferencvaros": "ferencvaros",
        "ferencvarosi": "ferencvaros",
        "ferencvarosi tc": "ferencvaros",
        "atletico goianiense": "atletico go",
        "atletico go": "atletico go",
        "america mineiro": "america mg",
        "america mg": "america mg",
        # Equivalências específicas, nunca aproximação fuzzy entre clubes.
        "heart of midlothian": "hearts",
        "hearts": "hearts",
        "union st gilloise": "union saint gilloise",
        "union saint gilloise": "union saint gilloise",
        "csu craiova": "cs universitatea craiova",
        "universitatea craiova": "cs universitatea craiova",
        "cs universitatea craiova": "cs universitatea craiova",
        "red star belgrade": "crvena zvezda",
        "crvena zvezda": "crvena zvezda",
    }

    # Só usamos a hora para desempatar candidatos que já passaram a validação
    # pelos nomes das duas equipas. Uma diferença maior continua ambígua.
    TOLERANCIA_HORA_EVENTO_SEG = 90 * 60

    def __init__(self, fonte_odds):
        self.fonte = fonte_odds

    @classmethod
    def _normalizar(cls, texto):
        texto = unicodedata.normalize("NFKD", str(texto or ""))
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        texto = texto.casefold()
        # Letras que NFKD não decompõe: preservar a transliteração da equipa.
        texto = texto.replace("æ", "ae").replace("œ", "oe").replace("ø", "o").replace("ł", "l")
        texto = re.sub(r"[^a-z0-9]+", " ", texto)
        tokens = [t for t in texto.split() if t not in cls.TOKENS_CLUBE]
        return " ".join(tokens).strip()

    @classmethod
    def _canon_equipa(cls, texto):
        nome = cls._normalizar(texto)
        return cls.ALIASES_EQUIPA.get(nome, nome)

    @classmethod
    def _nome_equipa_compativel(cls, a, b):
        """Compara nomes sem aceitar aproximações abertas."""
        a_n = cls._canon_equipa(a)
        b_n = cls._canon_equipa(b)
        if not a_n or not b_n:
            return False
        if a_n == b_n:
            return True

        ta, tb = set(a_n.split()), set(b_n.split())
        if not ta or not tb:
            return False
        return ta.issubset(tb) or tb.issubset(ta)

    @classmethod
    def _chave_jogo(cls, casa, fora):
        return cls._canon_equipa(casa), cls._canon_equipa(fora)

    @staticmethod
    def _timestamp_iso(valor):
        if not isinstance(valor, str) or not valor.strip():
            return None
        try:
            dt = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()

    @classmethod
    def _desempatar_evento_por_hora(cls, candidatos, timestamp_jogo):
        """Escolhe só um fixture quando a hora torna a correspondência inequívoca."""
        if len(candidatos or []) <= 1:
            return list(candidatos or [])
        try:
            alvo = float(timestamp_jogo)
        except (TypeError, ValueError):
            return list(candidatos)

        distancias = []
        for evento in candidatos:
            if not isinstance(evento, dict):
                continue
            ts = cls._timestamp_iso(evento.get("data"))
            if ts is None:
                continue
            distancias.append((abs(ts - alvo), evento))

        if not distancias:
            return list(candidatos)
        distancias.sort(key=lambda item: item[0])
        menor = distancias[0][0]
        if menor > cls.TOLERANCIA_HORA_EVENTO_SEG:
            return list(candidatos)

        melhores = [evento for distancia, evento in distancias if abs(distancia - menor) < 1.0]
        if len(melhores) == 1:
            return melhores
        return list(candidatos)

    @staticmethod
    def _odd_numero(valor):
        try:
            odd = float(valor)
        except (TypeError, ValueError):
            return None
        return odd if odd > 1.0 else None

    @staticmethod
    def _linha_numero(valor):
        if valor is None or isinstance(valor, bool):
            return None
        try:
            return float(valor)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _texto_item(cls, mercado, odd):
        return cls._normalizar(
            " ".join(
                [
                    str(mercado.get("name") or ""),
                    str(odd.get("seleção") or ""),
                    str(odd.get("ref") or ""),
                ]
            )
        )

    @classmethod
    def _periodo_compativel(cls, mercado):
        periodo = cls._normalizar(mercado.get("period"))
        if not periodo:
            return True
        return periodo.replace(" ", "") in {"fulltime", "ft", "match", "regulartime"}

    @classmethod
    def _mercado_compativel(cls, mercado_modelo, mercado):
        if not cls._periodo_compativel(mercado):
            return False
        if bool(mercado.get("playerProp", False)):
            return False

        nome = cls._normalizar(mercado.get("name"))
        if not nome:
            return False

        if mercado_modelo in {"Vitória Casa", "Vitória Fora"}:
            proibidos = ("corner", "handicap", "first half", "second half")
            if any(x in nome for x in proibidos):
                return False
            return any(x in nome for x in ("full time result", "match result", "1x2"))

        if mercado_modelo == "Ambas Marcam":
            proibidos = ("corner", "first half", "second half", "team 1", "team 2")
            if any(x in nome for x in proibidos):
                return False
            return any(x in nome for x in ("both teams to score", "both teams score", "btts"))

        if mercado_modelo.startswith(("Over ", "Under ")):
            proibidos = (
                "corner", "team 1", "team 2", "first half", "second half",
                "player", "card", "booking", "shot", "offside",
            )
            if any(x in nome for x in proibidos):
                return False
            return any(
                x in nome
                for x in (
                    "over under full time",
                    "total goals",
                    "goals over under",
                    "match goals",
                )
            )

        if mercado_modelo in {"1X (Casa ou Empate)", "X2 (Empate ou Fora)"}:
            proibidos = ("corner", "first half", "second half")
            if any(x in nome for x in proibidos):
                return False
            return "double chance" in nome
        return False

    @classmethod
    def _item_compativel(cls, mercado_modelo, mercado, odd, casa, fora):
        texto = cls._texto_item(mercado, odd)
        selecao = cls._normalizar(odd.get("seleção"))
        ref = cls._normalizar(odd.get("ref"))
        casa_n = cls._canon_equipa(casa)
        fora_n = cls._canon_equipa(fora)

        if mercado_modelo == "Vitória Casa":
            return selecao in {"1", "home", casa_n} or ref in {"1", "home", casa_n}
        if mercado_modelo == "Vitória Fora":
            return selecao in {"2", "away", fora_n} or ref in {"2", "away", fora_n}
        if mercado_modelo == "Ambas Marcam":
            return selecao in {"yes", "sim"} or ref in {"yes", "sim"}
        if mercado_modelo in {"1X (Casa ou Empate)", "X2 (Empate ou Fora)"}:
            alvo = "1x" if mercado_modelo.startswith("1X") else "x2"
            compactado = texto.replace(" ", "")
            return alvo in compactado

        m = re.fullmatch(r"(Over|Under) ([0-9]+(?:\.[0-9]+)?) Golos", mercado_modelo)
        if m:
            # Exigir handicap e lado consistentes com a linha da seleção.
            # Nunca aceitar Under 12.5 como Under 2.5 por substring.
            from odds_linha_validacao import validar_linha_totais
            valido, _motivo = validar_linha_totais(mercado_modelo, mercado, odd)
            return valido
        return False

    @staticmethod
    def _timestamp_odd(mercado, odd):
        return str(
            odd.get("bookmakerChangedAt")
            or odd.get("changedAt")
            or mercado.get("updatedAt")
            or ""
        )

    @classmethod
    def _contexto_mercados_passivo(cls, dados, mercado_modelo):
        """Conta mercados ja recebidos; zero pedidos extra e sem associar odds.

        Diferencia payload sem mercados, mercados com catalogo incompleto
        e mercados presentes mas nao compativeis. Apenas telemetria CLV.
        """
        if not isinstance(dados, dict) or not isinstance(dados.get("mercados"), list):
            return None
        mercados = [
            m for m in dados["mercados"] if isinstance(m, dict)
        ]
        sem_catalogo = sum(
            bool(re.fullmatch(r"market [0-9]+", str(m.get("name") or "").casefold()))
            for m in mercados
        )
        return {
            "total": min(len(mercados), 999),
            "compativeis": min(sum(
                cls._mercado_compativel(mercado_modelo, m)
                for m in mercados
            ), 999),
            "sem_catalogo": min(sem_catalogo, 999),
        }

    @classmethod
    def _extrair_odd_diagnostico(cls, dados, mercado_modelo):
        if not isinstance(dados, dict):
            return None, "odds_evento_indisponiveis"
        if dados.get("bookmaker_disponivel") is False:
            return None, "betano_sem_odds_no_evento"

        casa = dados.get("casa") or ""
        fora = dados.get("fora") or ""
        mercados_compativeis = []
        encontrados = []

        for mercado in dados.get("mercados") or []:
            if not isinstance(mercado, dict):
                continue
            if not cls._mercado_compativel(mercado_modelo, mercado):
                continue
            mercados_compativeis.append(mercado)
            for odd in mercado.get("odds") or []:
                if not isinstance(odd, dict):
                    continue
                valor = cls._odd_numero(odd.get("odd"))
                if valor is None:
                    continue
                if cls._item_compativel(mercado_modelo, mercado, odd, casa, fora):
                    encontrados.append((valor, cls._timestamp_odd(mercado, odd)))

        if not mercados_compativeis:
            return None, "mercado_nao_disponivel"
        if not encontrados:
            return None, "linha_ou_selecao_nao_disponivel"
        if len(encontrados) > 1:
            return None, "mercado_ambiguo"
        return encontrados[0], None

    @classmethod
    def _referencias_cotacao(cls, dados, mercado_modelo, valor, atualizado_em):
        """Recupera IDs apenas para a cotacao ja extraida; nao faz selecao nova."""
        encontrados = []
        if not isinstance(dados, dict):
            return {"association": "sem_payload"}
        for mercado in dados.get("mercados") or []:
            if not isinstance(mercado, dict) or not cls._mercado_compativel(mercado_modelo, mercado):
                continue
            for odd in mercado.get("odds") or []:
                if not isinstance(odd, dict):
                    continue
                cotacao = cls._odd_numero(odd.get("odd"))
                if cotacao is None or abs(cotacao - valor) > 0.000001:
                    continue
                if not cls._item_compativel(mercado_modelo, mercado, odd, dados.get("casa"), dados.get("fora")):
                    continue
                if cls._timestamp_odd(mercado, odd) != atualizado_em:
                    continue
                encontrados.append({
                    "market_id": mercado.get("id"),
                    "market_name": mercado.get("name"),
                    "period": mercado.get("period"),
                    "handicap": mercado.get("handicap"),
                    "market_updated_at": mercado.get("updatedAt"),
                    "selection_name": odd.get("seleção"),
                    "outcome_ref": odd.get("ref"),
                    "bookmakerChangedAt": odd.get("bookmakerChangedAt"),
                    "association": "unica",
                })
        return encontrados[0] if len(encontrados) == 1 else {
            "association": "referencia_ausente_ou_ambigua"
        }

    @classmethod
    def _extrair_odd(cls, dados, mercado_modelo):
        extraida, _ = cls._extrair_odd_diagnostico(dados, mercado_modelo)
        return extraida

    @classmethod
    def _candidatos_evento(cls, eventos, casa, fora, indice_exato=None):
        chave = cls._chave_jogo(casa, fora)
        if indice_exato is not None:
            exatos = indice_exato.get(chave) or []
            if exatos:
                return exatos

        candidatos = []
        for evento in eventos or []:
            if not isinstance(evento, dict):
                continue
            if (
                not equipas_categoria_incompativel(casa, evento.get("casa"))
                and not equipas_categoria_incompativel(fora, evento.get("fora"))
                and cls._nome_equipa_compativel(casa, evento.get("casa"))
                and cls._nome_equipa_compativel(fora, evento.get("fora"))
            ):
                candidatos.append(evento)
        return candidatos

    @classmethod
    def _payload_evento_compativel(cls, dados, jogo, event_id):
        """Confirma que /odds continua a descrever o fixture selecionado."""
        if not isinstance(dados, dict):
            return True
        payload_id = dados.get("id")
        if payload_id not in (None, "") and str(payload_id) != str(event_id):
            return False

        casa_payload = str(dados.get("casa") or "").strip()
        fora_payload = str(dados.get("fora") or "").strip()
        if not casa_payload or not fora_payload:
            return True
        return (
            not equipas_categoria_incompativel(jogo.get("casa"), casa_payload)
            and not equipas_categoria_incompativel(jogo.get("fora"), fora_payload)
            and cls._nome_equipa_compativel(jogo.get("casa"), casa_payload)
            and cls._nome_equipa_compativel(jogo.get("fora"), fora_payload)
        )

    @classmethod
    def _alertas_contexto(cls, jogo, evento, dados=None):
        """Confere horario e competicao para revisao manual (nao muda odds)."""
        alertas = []
        try:
            ts_modelo = float(jogo.get("timestamp"))
        except (TypeError, ValueError):
            ts_modelo = None
        ts_fonte = cls._timestamp_iso(evento.get("data"))
        if ts_modelo is not None and ts_fonte is not None:
            if abs(ts_modelo - ts_fonte) > cls.TOLERANCIA_HORA_EVENTO_SEG:
                alertas.append("horario_divergente")

        liga_modelo = cls._normalizar(jogo.get("liga"))
        liga_evento = cls._normalizar(
            (dados or {}).get("liga") or evento.get("liga")
        )
        # Nomes regionais podem diferir; so assinalar incompatibilidades
        # claras, nunca bloquear por uma simples variacao de designacao.
        ignorar = {"league", "liga", "football", "futebol", "english", "england"}
        tokens_modelo = set(liga_modelo.split()) - ignorar
        tokens_fonte = set(liga_evento.split()) - ignorar
        if categorias_incompativeis(jogo.get("liga"), (dados or {}).get("liga") or evento.get("liga")):
            alertas.append("categoria_juvenil_incompativel")
        if (
            len(tokens_modelo) >= 1 and len(tokens_fonte) >= 1
            and not (tokens_modelo & tokens_fonte)
            and liga_modelo != "competicao" and liga_evento != "competicao"
        ):
            alertas.append("competicao_divergente")
        return alertas

    @staticmethod
    def _registar_diagnostico(selecao, motivo):
        selecao["_odds_diag"] = motivo
        jogo = selecao.get("jogo") or {}
        logging.info(
            "ODDS_DIAG | %s vs %s | %s | %s",
            jogo.get("casa") or "?",
            jogo.get("fora") or "?",
            selecao.get("mercado") or "?",
            motivo,
        )

    def _motivo_fonte(self, event_id):
        diagnostico = getattr(self.fonte, "diagnostico_evento", None)
        if not callable(diagnostico):
            return ""
        try:
            return str(diagnostico(event_id) or "")
        except (TypeError, ValueError, RuntimeError):
            return ""

    def enriquecer(
        self,
        selecoes,
        fallback_individual_ausentes=False,
        max_fallback_individual=8,
    ):
        """Devolve cópias das seleções; nunca filtra nem reordena o V1.

        O fallback individual é opcional e destina-se à camada comercial.
        O fluxo normal do /analisa mantém o comportamento e consumo anteriores.
        """
        saida = deepcopy(list(selecoes or []))
        if not saida or not self.fonte or not getattr(self.fonte, "configurada", False):
            return saida

        eventos = list(self.fonte.eventos_hoje() or [])
        diagnostico_descoberta = ""
        if not eventos:
            diagnostico_descoberta = str(
                getattr(self.fonte, "ultimo_diagnostico_eventos", "") or ""
            ).strip()

        n_primarios = len(eventos)
        complemento_consultado = False

        # Só em auditoria/recuperação explícita (não no /analisa normal):
        # consultar no máximo uma lista complementar pré-jogo, quando faltam
        # correspondências. A fonte aplica cache/cooldown para poupar quota.
        if fallback_individual_ausentes:
            ausentes = any(
                not self._candidatos_evento(
                    eventos, (s.get("jogo") or {}).get("casa"),
                    (s.get("jogo") or {}).get("fora")
                )
                for s in saida
            )
            complementar = getattr(self.fonte, "eventos_complementares", None)
            if ausentes and callable(complementar):
                complemento_consultado = True
                try:
                    extras = complementar() or []
                except (RuntimeError, ValueError, TypeError, OSError):
                    extras = []
                ids_presentes = {
                    str(e.get("id")) for e in eventos
                    if isinstance(e, dict) and e.get("id") not in (None, "")
                }
                for evento in extras:
                    if not isinstance(evento, dict):
                        continue
                    event_id = evento.get("id")
                    if event_id in (None, "") or str(event_id) in ids_presentes:
                        continue
                    eventos.append({**evento, "_origem_descoberta_complementar": True})
                    ids_presentes.add(str(event_id))

        indice = {}
        for evento in eventos or []:
            if not isinstance(evento, dict):
                continue
            chave = self._chave_jogo(evento.get("casa"), evento.get("fora"))
            if not all(chave):
                continue
            indice.setdefault(chave, []).append(evento)

        resolvidas = []
        eventos_resolvidos = {}
        # Apenas telemetria em memória: não acrescenta campos aos snapshots.
        origem_fixture_por_selecao = {}
        cotacoes_encontradas = set()
        for selecao in saida:
            jogo = selecao.get("jogo") or {}
            candidatos = self._candidatos_evento(
                eventos,
                jogo.get("casa"),
                jogo.get("fora"),
                indice_exato=indice,
            )
            if not candidatos:
                from odds_pistas_descoberta import recolher_pistas
                selecao["_odds_descoberta"] = recolher_pistas(
                    jogo, eventos, n_primarios, complemento_consultado,
                    self._nome_equipa_compativel,
                    normalizar=self._normalizar,
                    timestamp_fn=self._timestamp_iso,
                )
                self._registar_diagnostico(
                    selecao,
                    diagnostico_descoberta or "evento_nao_encontrado",
                )
                continue
            if len(candidatos) != 1:
                candidatos = self._desempatar_evento_por_hora(
                    candidatos, jogo.get("timestamp")
                )
            if len(candidatos) != 1:
                self._registar_diagnostico(selecao, "evento_ambiguo")
                continue

            evento = candidatos[0]
            # As fontes produtivas identificadas devem provar data e hora
            # antes de qualquer captura comercial. Diagnosticos antigos em
            # fontes de testes/legadas sem provider mantêm a sua semantica.
            if getattr(self.fonte, "provider", None) in ("oddspapi", "odds-api.io"):
                hora_ok, motivo_hora = verificar_hora_fixture(
                    jogo.get("timestamp"), evento.get("data"), exigir_hora=True,
                )
                if not hora_ok:
                    selecao.setdefault("_odds_alertas", []).append(
                        "horario_divergente" if motivo_hora == "horario_fixture_incompativel"
                        else "horario_nao_comprovado"
                    )
                    self._registar_diagnostico(selecao, motivo_hora)
                    continue
            try:
                ts = float(jogo.get("timestamp"))
                dia_pt = datetime.fromtimestamp(ts, timezone.utc).astimezone(
                    ZoneInfo("Europe/Lisbon")
                ).date().isoformat()
            except (TypeError, ValueError, OverflowError, OSError):
                dia_pt = ""
            if juventude_confirmada_hoje({
                "data_jogo": dia_pt, "casa": jogo.get("casa"),
                "fora": jogo.get("fora"), "liga": jogo.get("liga"),
            }):
                self._registar_diagnostico(selecao, "fixture_u19_confirmado_tff")
                continue
            # Metadados de contexto observados no fixture já associado.
            # Diagnóstico passivo: sem influenciar matches, odds ou snapshots.
            selecao["_odds_evento_contexto"] = {
                "liga_fixture": str(evento.get("liga") or ""),
                "inicio_fixture": str(evento.get("data") or ""),
                "liga_odds": "",
            }
            alertas_contexto = self._alertas_contexto(jogo, evento)
            if evento.get("_origem_descoberta_complementar"):
                # Novo fixture: exige validação temporal real; nunca associar
                # apenas nomes sem confirmar a hora da previsão congelada.
                ts_fonte = self._timestamp_iso(evento.get("data"))
                try:
                    ts_modelo = float(jogo.get("timestamp"))
                except (TypeError, ValueError):
                    ts_modelo = None
                if (
                    ts_fonte is None or ts_modelo is None
                    or abs(ts_modelo - ts_fonte) > self.TOLERANCIA_HORA_EVENTO_SEG
                ):
                    self._registar_diagnostico(selecao, "horario_recuperacao_nao_validado")
                    continue
            if alertas_contexto:
                selecao["_odds_alertas"] = alertas_contexto
                logging.warning(
                    "ODDS_VERIFICACAO | %s vs %s | %s",
                    jogo.get("casa") or "?",
                    jogo.get("fora") or "?",
                    ",".join(alertas_contexto),
                )
            if "categoria_juvenil_incompativel" in alertas_contexto:
                self._registar_diagnostico(selecao, "liga_idade_incompativel")
                continue
            event_id = evento.get("id")
            if event_id is None:
                self._registar_diagnostico(selecao, "evento_sem_id")
                continue
            chave_evento = str(event_id)
            eventos_resolvidos[chave_evento] = evento
            origem_fixture_por_selecao[id(selecao)] = (
                'complementar' if evento.get('_origem_descoberta_complementar') else 'primaria'
            )
            resolvidas.append((selecao, jogo, event_id, chave_evento))

        cache_odds = {}
        lote = getattr(self.fonte, "odds_eventos_em_lote", None)
        if callable(lote) and eventos_resolvidos:
            try:
                resposta_lote = lote(list(eventos_resolvidos.values()))
                if isinstance(resposta_lote, dict):
                    cache_odds.update(
                        {str(k): v for k, v in resposta_lote.items()}
                    )
            except (RuntimeError, ValueError, TypeError):
                # Fonte antiga/fallback: mantém a consulta individual segura.
                pass

        fallback_restantes = max(int(max_fallback_individual or 0), 0)
        for selecao, jogo, event_id, chave_evento in resolvidas:
            if chave_evento in cache_odds:
                dados = cache_odds[chave_evento]
                if (
                    dados is None
                    and fallback_individual_ausentes
                    and fallback_restantes > 0
                ):
                    dados = self.fonte.odds_evento(event_id)
                    cache_odds[chave_evento] = dados
                    fallback_restantes -= 1
            else:
                dados = self.fonte.odds_evento(event_id)
                cache_odds[chave_evento] = dados

            if dados is None:
                motivo = self._motivo_fonte(event_id) or "odds_evento_indisponiveis"
                self._registar_diagnostico(selecao, motivo)
                continue

            if isinstance(dados, dict):
                contexto = selecao.get("_odds_evento_contexto")
                if isinstance(contexto, dict):
                    contexto["liga_odds"] = str(dados.get("liga") or "")
                adicionais = self._alertas_contexto(jogo, eventos_resolvidos[chave_evento], dados)
                selecao["_odds_alertas"] = sorted(set(
                    (selecao.get("_odds_alertas") or []) + adicionais
                ))
            if "categoria_juvenil_incompativel" in (selecao.get("_odds_alertas") or []):
                self._registar_diagnostico(selecao, "liga_idade_incompativel")
                continue
            if not self._payload_evento_compativel(dados, jogo, event_id):
                self._registar_diagnostico(selecao, "odds_payload_evento_divergente")
                continue

            extraida, motivo = self._extrair_odd_diagnostico(
                dados, str(selecao.get("mercado") or "")
            )
            if extraida is None:
                if motivo in {"mercado_nao_disponivel", "linha_ou_selecao_nao_disponivel"}:
                    mercado_modelo = str(selecao.get("mercado") or "")
                    contexto_mercados = self._contexto_mercados_passivo(
                        dados, mercado_modelo
                    )
                    if contexto_mercados is not None:
                        # Apenas na selecao transitoria; nunca no snapshot.
                        selecao["_odds_contexto_mercados"] = contexto_mercados
                    if motivo == "linha_ou_selecao_nao_disponivel":
                        from odds_linha_diagnostico_shadow import resumo_linha_shadow
                        contexto_linha = resumo_linha_shadow(
                            dados.get("mercados"), mercado_modelo,
                            self._mercado_compativel, self._odd_numero,
                        )
                        if contexto_linha is not None:
                            # Apenas para rastreio; não altera a decisão de odds.
                            selecao["_odds_contexto_linha"] = contexto_linha
                self._registar_diagnostico(selecao, motivo or "odd_nao_extraida")
                continue

            odd_real, atualizada_em = extraida
            # Medir frescura antes da congelação. Inicialmente só SHADOW:
            # bloquear sem dados de campo poderia alterar a coorte V1.3
            # enquanto o protocolo de 50 entradas está em curso.
            alerta_frescura = classificar_frescura(
                atualizada_em, datetime.now(timezone.utc),
            )
            if alerta_frescura:
                selecao.setdefault("_odds_alertas", []).append(alerta_frescura)
                logging.info(
                    "ODDS_FRESCURA | %s vs %s | %s",
                    jogo.get("casa") or "?", jogo.get("fora") or "?",
                    alerta_frescura,
                )
            try:
                prob = float(selecao["probabilidade"])
            except (KeyError, TypeError, ValueError):
                self._registar_diagnostico(selecao, "probabilidade_invalida")
                continue
            selecao["odd_real"] = round(odd_real, 4)
            cotacoes_encontradas.add(id(selecao))
            selecao["ev_real"] = round((prob * odd_real) - 1.0, 6)
            selecao["odds_fonte"] = str((dados or {}).get("fonte") or self.fonte.nome_fonte)
            selecao["odds_event_id"] = str(event_id)
            selecao["odds_atualizada_em"] = atualizada_em
            # Metadados separados do snapshot; nem o modelo nem a decisao de
            # associacao/odd original mudam com esta instrumentacao.
            selecao["_rastreio_odds"] = self._referencias_cotacao(
                dados, str(selecao.get("mercado") or ""), odd_real, atualizada_em
            )

        # Registo agregado sem nomes de clubes nem odds: compara a cobertura
        # normal com a recuperação na mesma ronda, sem consultar a API de novo.
        primary = sum(v == 'primaria' for v in origem_fixture_por_selecao.values())
        recovered = sum(v == 'complementar' for v in origem_fixture_por_selecao.values())
        primary_quoted = sum(
            origem_fixture_por_selecao.get(k) == 'primaria' for k in cotacoes_encontradas
        )
        recovered_quoted = sum(
            origem_fixture_por_selecao.get(k) == 'complementar' for k in cotacoes_encontradas
        )
        logging.info(
            'ODDS_COBERTURA | modo=%s | selecoes=%s | fixtures_primarios=%s | '
            'fixtures_complementares=%s | odds_primarias=%s | odds_complementares=%s | '
            'sem_fixture_validado=%s | sem_cotacao=%s',
            'recuperacao' if fallback_individual_ausentes else 'normal',
            len(saida), primary, recovered, primary_quoted, recovered_quoted,
            len(saida) - primary - recovered, len(saida) - len(cotacoes_encontradas),
        )
        return saida

