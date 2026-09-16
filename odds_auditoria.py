"""Liga previsões V1 a odds reais sem alterar a seleção do modelo.

A camada é deliberadamente conservadora: só associa um evento quando casa e fora
coincidem de forma não ambígua e só aceita mercados que consegue reconhecer com
segurança. Se não houver correspondência inequívoca, não guarda qualquer odd.
"""
import re
import unicodedata
from copy import deepcopy


class AuditoriaOdds:
    def __init__(self, fonte_odds):
        self.fonte = fonte_odds

    @staticmethod
    def _normalizar(texto):
        texto = unicodedata.normalize("NFKD", str(texto or ""))
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        texto = texto.casefold()
        texto = re.sub(r"[^a-z0-9]+", " ", texto)
        tokens = [t for t in texto.split() if t not in {"fc", "cf", "afc"}]
        return " ".join(tokens).strip()

    @classmethod
    def _chave_jogo(cls, casa, fora):
        return cls._normalizar(casa), cls._normalizar(fora)

    @staticmethod
    def _odd_numero(valor):
        try:
            odd = float(valor)
        except (TypeError, ValueError):
            return None
        return odd if odd > 1.0 else None

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
    def _mercado_compativel(cls, mercado_modelo, nome_mercado):
        nome = cls._normalizar(nome_mercado)
        if mercado_modelo in {"Vitória Casa", "Vitória Fora"}:
            return any(x in nome for x in ("full time result", "match result", "1x2"))
        if mercado_modelo == "Ambas Marcam":
            return any(x in nome for x in ("both teams to score", "both teams score", "btts"))
        if mercado_modelo.startswith(("Over ", "Under ")):
            return any(x in nome for x in ("total goals", "goals over under", "over under", "match goals"))
        if mercado_modelo in {"1X (Casa ou Empate)", "X2 (Empate ou Fora)"}:
            return "double chance" in nome
        return False

    @classmethod
    def _item_compativel(cls, mercado_modelo, mercado, odd, casa, fora):
        texto = cls._texto_item(mercado, odd)
        selecao = cls._normalizar(odd.get("seleção"))
        ref = cls._normalizar(odd.get("ref"))
        casa_n = cls._normalizar(casa)
        fora_n = cls._normalizar(fora)

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
            linha = m.group(2)
            return lado in texto and linha in texto
        return False

    @classmethod
    def _extrair_odd(cls, dados, mercado_modelo):
        if not isinstance(dados, dict):
            return None
        casa = dados.get("casa") or ""
        fora = dados.get("fora") or ""
        encontrados = []
        for mercado in dados.get("mercados") or []:
            if not isinstance(mercado, dict):
                continue
            if not cls._mercado_compativel(mercado_modelo, mercado.get("name")):
                continue
            for odd in mercado.get("odds") or []:
                if not isinstance(odd, dict):
                    continue
                valor = cls._odd_numero(odd.get("odd"))
                if valor is None:
                    continue
                if cls._item_compativel(mercado_modelo, mercado, odd, casa, fora):
                    encontrados.append((valor, str(mercado.get("updatedAt") or "")))
        if len(encontrados) != 1:
            return None
        return encontrados[0]

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
            chave = self._chave_jogo(jogo.get("casa"), jogo.get("fora"))
            candidatos = indice.get(chave) or []
            if len(candidatos) != 1:
                continue
            evento = candidatos[0]
            event_id = evento.get("id")
            if event_id is None:
                continue
            if event_id not in cache_odds:
                cache_odds[event_id] = self.fonte.odds_evento(event_id)
            dados = cache_odds[event_id]
            extraida = self._extrair_odd(dados, str(selecao.get("mercado") or ""))
            if extraida is None:
                continue
            odd_real, atualizada_em = extraida
            try:
                prob = float(selecao["probabilidade"])
            except (KeyError, TypeError, ValueError):
                continue
            selecao["odd_real"] = round(odd_real, 4)
            selecao["ev_real"] = round((prob * odd_real) - 1.0, 6)
            selecao["odds_fonte"] = str((dados or {}).get("fonte") or self.fonte.nome_fonte)
            selecao["odds_event_id"] = str(event_id)
            selecao["odds_atualizada_em"] = atualizada_em
        return saida
