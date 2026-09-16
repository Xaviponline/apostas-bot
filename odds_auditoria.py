"""Liga previsões V1 a odds reais sem alterar a seleção do modelo.

A camada é deliberadamente conservadora: associa primeiro por nomes normalizados
exatos. Só usa um fallback controlado quando existe um único evento compatível e
os nomes são extensões inequívocas ou equivalências conhecidas entre fornecedores.
Se não houver correspondência segura, não guarda qualquer odd.
"""
import logging
import re
import unicodedata
from copy import deepcopy


class AuditoriaOdds:
    TOKENS_CLUBE = {
        "fc", "cf", "afc", "ac", "sc", "ca", "cd", "ud", "rcd",
        "sl", "ss", "fk", "sk", "bk", "aif",
    }

    ALIASES_EQUIPA = {
        "athletic club": "athletic bilbao",
        "athletic bilbao": "athletic bilbao",
    }

    def __init__(self, fonte_odds):
        self.fonte = fonte_odds

    @classmethod
    def _normalizar(cls, texto):
        texto = unicodedata.normalize("NFKD", str(texto or ""))
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        texto = texto.casefold()
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

        m = re.match(r"^(Over|Under) ([0-9]+(?:\.[0-9]+)?) Golos$", mercado_modelo)
        if m:
            lado = m.group(1).casefold()
            linha_alvo = float(m.group(2))
            escolha = cls._normalizar(
                " ".join([str(odd.get("seleção") or ""), str(odd.get("ref") or "")])
            )
            if lado not in escolha:
                return False

            linha_mercado = cls._linha_numero(mercado.get("handicap"))
            if linha_mercado is not None:
                return abs(linha_mercado - linha_alvo) < 1e-9

            linha_texto = cls._normalizar(m.group(2))
            nome_mercado = cls._normalizar(mercado.get("name"))
            return linha_texto in escolha or linha_texto in nome_mercado
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
            if cls._nome_equipa_compativel(casa, evento.get("casa")) and cls._nome_equipa_compativel(
                fora, evento.get("fora")
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
        return cls._nome_equipa_compativel(jogo.get("casa"), casa_payload) and cls._nome_equipa_compativel(
            jogo.get("fora"), fora_payload
        )

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

    def enriquecer(self, selecoes):
        """Devolve cópias das seleções; nunca filtra nem reordena o V1."""
        saida = deepcopy(list(selecoes or []))
        if not saida or not self.fonte or not getattr(self.fonte, "configurada", False):
            return saida

        eventos = self.fonte.eventos_hoje()
        indice = {}
        for evento in eventos or []:
            if not isinstance(evento, dict):
                continue
            chave = self._chave_jogo(evento.get("casa"), evento.get("fora"))
            if not all(chave):
                continue
            indice.setdefault(chave, []).append(evento)

        cache_odds = {}
        for selecao in saida:
            jogo = selecao.get("jogo") or {}
            candidatos = self._candidatos_evento(
                eventos,
                jogo.get("casa"),
                jogo.get("fora"),
                indice_exato=indice,
            )
            if not candidatos:
                self._registar_diagnostico(selecao, "evento_nao_encontrado")
                continue
            if len(candidatos) != 1:
                self._registar_diagnostico(selecao, "evento_ambiguo")
                continue

            evento = candidatos[0]
            event_id = evento.get("id")
            if event_id is None:
                self._registar_diagnostico(selecao, "evento_sem_id")
                continue
            if event_id not in cache_odds:
                cache_odds[event_id] = self.fonte.odds_evento(event_id)
            dados = cache_odds[event_id]

            if dados is None:
                motivo = self._motivo_fonte(event_id) or "odds_evento_indisponiveis"
                self._registar_diagnostico(selecao, motivo)
                continue

            if not self._payload_evento_compativel(dados, jogo, event_id):
                self._registar_diagnostico(selecao, "odds_payload_evento_divergente")
                continue

            extraida, motivo = self._extrair_odd_diagnostico(
                dados, str(selecao.get("mercado") or "")
            )
            if extraida is None:
                self._registar_diagnostico(selecao, motivo or "odd_nao_extraida")
                continue

            odd_real, atualizada_em = extraida
            try:
                prob = float(selecao["probabilidade"])
            except (KeyError, TypeError, ValueError):
                self._registar_diagnostico(selecao, "probabilidade_invalida")
                continue
            selecao["odd_real"] = round(odd_real, 4)
            selecao["ev_real"] = round((prob * odd_real) - 1.0, 6)
            selecao["odds_fonte"] = str((dados or {}).get("fonte") or self.fonte.nome_fonte)
            selecao["odds_event_id"] = str(event_id)
            selecao["odds_atualizada_em"] = atualizada_em
        return saida
