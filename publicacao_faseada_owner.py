"""Publicações de análises OWNER faseadas a T-150m (somente leitura).

Não envia uma vitrine de 20 jogos às 09h. Publica TODAS as primeiras 20
previsões do dia ao OWNER, com ou sem VALUE, individualmente e por ordem
de início. A seleção comercial é futura; a V1.3 permanece intacta.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo

from alertas_prejogo import AlertasPreJogo

PT = ZoneInfo("Europe/Lisbon")
ANTECEDENCIA_ALVO = 150 * 60  # 2h30
ANTECEDENCIA_MIN = 90 * 60  # margem de recuperação quando muitos jogos coincidem
MAX_ANALISES_DIA = 20
MAX_POR_LOTE = 1  # um jogo por mensagem
INTERVALO_LOTES_SEG = 60  # notificação faseada, sem rajadas
VERSAO_ESTADO = 1


def _numero(valor):
    if isinstance(valor, bool):
        return None
    try:
        v = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return v if isfinite(v) else None


def _odd(valor):
    n = _numero(valor)
    return n if n is not None and 1 < n < 1000 else None


def _fmt(numero, casas=1):
    return f"{numero:.{casas}f}".replace(".", ",")


def _hora(ts):
    return datetime.fromtimestamp(float(ts), PT).strftime("%H:%M")


def _preco_guardado(p):
    preco = _odd(p.get("odd_valor_confirmado"))
    return preco if preco is not None else _odd(p.get("odd_real"))


def _analise(p):
    """Construir argumentos apenas a partir de snapshots pré-jogo existentes."""
    prob = _numero(p.get("probabilidade"))
    preco = _preco_guardado(p)
    minima = _odd(p.get("odd_minima"))
    if prob is None or not 0 < prob < 1:
        raise ValueError("Previsão sem probabilidade válida")
    ts = float(p["timestamp_jogo"])
    confianca = str(p.get("confianca_modelo") or "N/D")
    linhas = [
        f"💎 ANÁLISE PRÉ-JOGO · {_hora(ts)} (Portugal)",
        f"🏅 Ranking #{p['ranking_modelo']} · {p.get('liga') or 'Competição'}",
        f"⚽ {p.get('casa') or '?'} × {p.get('fora') or '?'}",
        "",
        f"🎯 MERCADO · {p.get('mercado') or 'N/D'}",
        f"📊 Probabilidade do modelo: {_fmt(prob*100)}% · Confiança {confianca}",
    ]
    qualidade = _numero(p.get("qualidade"))
    if qualidade is not None and 0 <= qualidade <= 100:
        linhas.append(f"📚 Qualidade dos dados: {int(qualidade)}/100")

    diag = p.get("diagnostico_modelo")
    if isinstance(diag, dict):
        casa = _numero(diag.get("lambda_casa"))
        fora = _numero(diag.get("lambda_fora"))
        if casa is not None and fora is not None and 0 < casa < 15 and 0 < fora < 15:
            linhas.append(f"⚽ Golos esperados pelo modelo: casa {_fmt(casa,2)} · fora {_fmt(fora,2)}")
        n_casa = _numero(diag.get("amostra_casa"))
        n_fora = _numero(diag.get("amostra_fora"))
        if (n_casa is not None and n_fora is not None
                and 0 < n_casa <= 2000 and 0 < n_fora <= 2000):
            linhas.append(f"📚 Amostra estatística: casa {int(n_casa)} · fora {int(n_fora)}")

    linhas.append("")
    minimo_txt = _fmt(minima, 2) if minima is not None else "N/D"
    preco_txt = _fmt(preco, 2) if preco is not None else "—"
    linhas.append(f"💶 Odd registada {preco_txt} · Odd mínima {minimo_txt}")

    estado = str(p.get("valor_estado") or "")
    atual = _odd(p.get("odd_mercado_atual"))
    if preco is None:
        linhas.append("⚪ SEM COTAÇÃO — VALUE por verificar")
    elif minima is None:
        linhas.append("⚪ MÍNIMO INDISPONÍVEL — VALUE por verificar")
    elif (estado == "expirado" or (estado == "sem_valor"
            and atual is not None and atual < minima)):
        linhas.append("🔴 VALUE EXPIRADO / PREÇO INFERIOR — não confirmado agora")
    elif preco < minima:
        linhas.append("🔴 SEM VALUE — preço registado abaixo da mínima")
    else:
        ev = preco * prob - 1
        distancia = preco / minima - 1
        if ev >= .25 or distancia >= .25:
            linhas.append("🔴 PREÇO INVULGAR — verificar identidade, mercado e odd")
        else:
            linhas.append("🟠 ACIMA DA MÍNIMA HISTÓRICA — confirmar preço disponível")
    linhas.extend([
        "ℹ️ Odds guardadas, não são cotações em direto.",
        "🔒 Previsão experimental, sem garantia de acerto ou lucro.",
    ])
    return "\n".join(linhas)


class PublicacaoFaseadaOwner:
    """Até 20 previsões originais/dia, sem filtro de odds, com estado persistente."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None

    def _ler(self):
        if self.path is None:
            raise RuntimeError("Publicação faseada sem estado persistente")
        if not self.path.exists():
            return {"versao": VERSAO_ESTADO, "publicadas": {}, "ultimo_lote_em": None}
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
            if (not isinstance(dados, dict)
                    or dados.get("versao") != VERSAO_ESTADO
                    or not isinstance(dados.get("publicadas"), dict)
                    or not (dados.get("ultimo_lote_em") is None
                            or isinstance(dados.get("ultimo_lote_em"), str))):
                raise ValueError("Marcador inválido")
            return dados
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError("Estado de publicação corrompido, não sobrescrever") from exc

    def _guardar(self, estado):
        if self.path is None:
            raise RuntimeError("Sem volume para publicar")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".publicacao_faseada_", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(estado, f, ensure_ascii=False, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _agora(agora):
        dt = agora or datetime.now(timezone.utc)
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("Instante sem fuso horário")
        return dt.astimezone(PT)

    @classmethod
    def _candidatas(cls, previsoes, agora):
        lista = []
        for inicio, rank, chave, p in AlertasPreJogo._selecoes_do_dia(previsoes, agora):
            restante = inicio - agora.timestamp()
            if (not ANTECEDENCIA_MIN <= restante <= ANTECEDENCIA_ALVO
                    or p.get("estado") != "pendente"):
                continue
            lista.append((rank, inicio, chave, p))
        return sorted(lista, key=lambda x: (x[1], x[0], x[2]))

    def avisar(self, previsoes, enviar, agora=None):
        """Publicar lote pequeno, marcar apenas após confirmação do Telegram."""
        dt = self._agora(agora)
        estado = self._ler()
        hoje = dt.date().isoformat()
        enviadas_hoje = sum(key.startswith(hoje + "|") for key in estado["publicadas"])
        if enviadas_hoje >= MAX_ANALISES_DIA:
            return 0
        if estado["ultimo_lote_em"]:
            try:
                ultimo = datetime.fromisoformat(estado["ultimo_lote_em"])
                if ultimo.tzinfo is None or ultimo.utcoffset() is None:
                    raise ValueError("Timestamp sem timezone")
                if 0 <= (dt - ultimo).total_seconds() < INTERVALO_LOTES_SEG:
                    return 0
            except (TypeError, ValueError) as exc:
                raise RuntimeError("Marcador temporal da publicação inválido") from exc

        elegiveis = [
            (rank, ini, chave, p)
            for rank, ini, chave, p in self._candidatas(previsoes, dt)
            if chave not in estado["publicadas"]
        ]
        if not elegiveis:
            return 0
        limite = min(MAX_POR_LOTE, MAX_ANALISES_DIA - enviadas_hoje)
        lote = elegiveis[:limite]
        mensagem = "\n\n━━━━━━━━━━━━━━━━━━━━\n\n".join(_analise(p) for _, _, _, p in lote)
        # Nunca delegar a uma função que divida o lote e aceite sucesso parcial.
        if len(mensagem.encode("utf-16-le")) // 2 > 3900:
            raise ValueError("Publicação excede limite Telegram; sem entrega nem marcador")
        enviar(mensagem)
        stamp = dt.astimezone(timezone.utc).isoformat()
        for _, _, chave, _ in lote:
            estado["publicadas"][chave] = stamp
        estado["ultimo_lote_em"] = stamp
        dias = sorted({ch[:10] for ch in estado["publicadas"]})
        if len(dias) > 45:
            inicio = dias[-45]
            estado["publicadas"] = {
                k: v for k, v in estado["publicadas"].items() if k[:10] >= inicio
            }
        self._guardar(estado)
        return len(lote)

    def relatorio(self, previsoes, agora=None):
        dt = self._agora(agora)
        estado = self._ler()
        hoje = dt.date().isoformat()
        enviados = sum(key.startswith(hoje + "|") for key in estado["publicadas"])
        janela = self._candidatas(previsoes, dt)
        faltam = sum(chave not in estado["publicadas"] for _, _, chave, _ in janela)
        return "\n".join([
            "📨 PUBLICAÇÕES FASEADAS — OWNER",
            "🕒 Envio a partir de 2h30 antes; até 1h30 para recuperar acumulações (Portugal)",
            f"✅ Publicadas hoje: {enviados}/{MAX_ANALISES_DIA}",
            f"⏳ Elegíveis agora, ainda não publicadas: {faltam}",
            "🎯 Todas as primeiras 20 previsões do dia, com ou sem VALUE, uma de cada vez.",
            "🔒 Odds históricas; zero novas APIs; V1.2/V1.3 intactas.",
        ])
