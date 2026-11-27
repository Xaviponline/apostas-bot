"""Balanços de jogos liquidado ESPN para o OWNER, sem novas consultas.

Só avisa previsões do Top20 V1.2 cuja análise foi realmente publicada
ao OWNER e que a rotina existente marcou como liquidadas.
Não altera V1.3, estados da previsão, odds, ou calendário de liquidação.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo

from alertas_prejogo import _chave, _numero, _odd, _rank
from previsoes_premium import RegistoPrevisoes

TZ_PT = ZoneInfo("Europe/Lisbon")
VERSAO_ESTADO = 1
MAX_POR_LOTE = 2
INTERVALO_LOTE_SEG = 60
MAX_ATRASO_DIAS = 7


def _fmt(numero, casas=1):
    return f"{numero:.{casas}f}".replace(".", ",")


def _placar_validado(p):
    """Aceita só o placar binário coerente com a liquidação já persistida."""
    if p.get("estado") not in {"ganhou", "perdeu"}:
        return None
    y = p.get("resultado_binario")
    if type(y) is not int or y not in (0, 1):
        return None
    if (p["estado"] == "ganhou") != (y == 1):
        return None
    gc, gf = p.get("golos_casa"), p.get("golos_fora")
    if (type(gc) is not int or type(gf) is not int
            or not 0 <= gc <= 30 or not 0 <= gf <= 30):
        return None
    if not p.get("liquidada_em"):
        return None
    mercado = str(p.get("mercado") or "")
    if RegistoPrevisoes._resultado_mercado(mercado, gc, gf) != y:
        return None
    prob = _numero(p.get("probabilidade"))
    if prob is None or not 0 < prob < 1:
        return None
    return gc, gf, y


def _cartao_resultado(p):
    resultado = _placar_validado(p)
    if resultado is None:
        raise ValueError("Não existe resultado liquidado coerente")
    gc, gf, y = resultado
    prob = float(p["probabilidade"])
    ts = _numero(p.get("timestamp_jogo"))
    if ts is None:
        raise ValueError("Jogo sem horário")
    data_hora = datetime.fromtimestamp(ts, TZ_PT).strftime("%d/%m · %H:%M")
    preco = _odd(p.get("odd_valor_confirmado"))
    if preco is None:
        preco = _odd(p.get("odd_real"))
    linhas = [
        "🏁 RESULTADO DA PREVISÃO · OWNER",
        f"⚽ {p.get('casa') or '?'} {gc}–{gf} {p.get('fora') or '?'}",
        f"🏆 {p.get('liga') or 'Competição'} · {data_hora}",
        f"🏅 Ranking #{p['ranking_modelo']}",
        "",
        f"🎯 Mercado: {p.get('mercado') or 'N/D'}",
        "✅ PREVISÃO ACERTADA" if y else "❌ PREVISÃO FALHADA",
        f"📊 Probabilidade estimada antes do jogo: {_fmt(prob*100)}%",
    ]
    if preco is not None:
        linhas.append(f"💶 Odd registada antes do jogo: {_fmt(preco, 2)}")
    else:
        linhas.append("💶 Sem odd pré-jogo registada")
    linhas.extend([
        "📚 Resultado incluído na avaliação histórica do modelo.",
        "ℹ️ É uma previsão estatística, não uma aposta executada nem prova de lucro.",
    ])
    return "\n".join(linhas)


class ResultadosPublicadosOwner:
    """Consulta os snapshots liquidados e o registo das análises publicadas."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None

    def _ler(self):
        if self.path is None:
            raise RuntimeError("Estado persistente dos resultados não configurado")
        if self.path.is_symlink():
            raise RuntimeError("Estado inseguro")
        if not self.path.exists():
            return {"versao": VERSAO_ESTADO, "enviados": {}, "ultimo_lote_em": None}
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            if (not isinstance(d, dict) or d.get("versao") != VERSAO_ESTADO
                    or not isinstance(d.get("enviados"), dict)
                    or not (d.get("ultimo_lote_em") is None
                            or isinstance(d.get("ultimo_lote_em"), str))):
                raise ValueError("Estado inválido")
            return d
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError("Estado de resultados corrompido, não sobrescrever") from exc

    def _guardar(self, d):
        if self.path is None or self.path.is_symlink():
            raise RuntimeError("Sem volume seguro para os resultados")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".resultados_owner_", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(d, file, ensure_ascii=False, sort_keys=True)
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _agora(agora):
        dt = agora or datetime.now(timezone.utc)
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("Hora sem fuso")
        return dt.astimezone(TZ_PT)

    @staticmethod
    def _itens_publicados(previsoes, publicados, agora):
        if not isinstance(publicados, dict):
            raise RuntimeError("Publicações do OWNER inválidas")
        inicio = (agora.date() - timedelta(days=MAX_ATRASO_DIAS)).isoformat()
        candidatos = []
        vistos = set()
        for p in previsoes or []:
            if (not isinstance(p, dict) or p.get("modelo_versao") != "V1.2"
                    or _rank(p.get("ranking_modelo")) is None
                    or not isinstance(p.get("data_jogo"), str)
                    or p["data_jogo"] < inicio or p["data_jogo"] > agora.date().isoformat()
                    or p.get("event_id") is None or not p.get("mercado")):
                continue
            ts = _numero(p.get("timestamp_jogo"))
            if ts is None or ts > agora.timestamp():
                continue
            chave = _chave(p)
            if chave not in publicados or chave in vistos:
                continue
            vistos.add(chave)
            if _placar_validado(p) is not None:
                candidatos.append((ts, int(p["ranking_modelo"]), chave, p))
        return sorted(candidatos, key=lambda x: (x[0], x[1], x[2]))

    def avisar(self, previsoes, publicador, enviar, agora=None):
        """Sem APIs; notificar apenas previsão já publicada e liquidada."""
        dt = self._agora(agora)
        # Falha fechada se o marcador de publicações está indisponível.
        publicado = publicador._ler().get("publicadas")
        estado = self._ler()
        if estado["ultimo_lote_em"]:
            try:
                anterior = datetime.fromisoformat(estado["ultimo_lote_em"])
                if anterior.tzinfo is None or anterior.utcoffset() is None:
                    raise ValueError("Timestamp inválido")
                if 0 <= (dt - anterior).total_seconds() < INTERVALO_LOTE_SEG:
                    return 0
            except (TypeError, ValueError) as exc:
                raise RuntimeError("Marcador temporal de resultados inválido") from exc

        elegiveis = [
            (ts, rank, chave, p)
            for ts, rank, chave, p in self._itens_publicados(previsoes, publicado, dt)
            if chave not in estado["enviados"]
        ]
        if not elegiveis:
            return 0
        # Cada notificação é uma mensagem única para evitar confirmação parcial.
        enviados = 0
        for _, _, chave, p in elegiveis[:MAX_POR_LOTE]:
            mensagem = _cartao_resultado(p)
            if len(mensagem.encode("utf-16-le")) // 2 > 3900:
                raise ValueError("Mensagem demasiado longa")
            enviar(mensagem)
            stamp = dt.astimezone(timezone.utc).isoformat()
            estado["enviados"][chave] = stamp
            estado["ultimo_lote_em"] = stamp
            dias = sorted({ch[:10] for ch in estado["enviados"]})
            if len(dias) > 45:
                cutoff = dias[-45]
                estado["enviados"] = {
                    k: v for k, v in estado["enviados"].items() if k[:10] >= cutoff
                }
            self._guardar(estado)
            enviados += 1
        return enviados

    def relatorio(self, previsoes, publicador, agora=None):
        dt = self._agora(agora)
        publicadas = publicador._ler().get("publicadas")
        estado = self._ler()
        hoje = dt.date().isoformat()
        n_publicadas = sum(ch.startswith(hoje + "|") for ch in publicadas)
        n_enviadas = sum(ch.startswith(hoje + "|") for ch in estado["enviados"])
        liquidadas = self._itens_publicados(previsoes, publicadas, dt)
        faltam = sum(ch not in estado["enviados"] for _, _, ch, _ in liquidadas)
        return "\n".join([
            "🏁 RESULTADOS DAS ANÁLISES — OWNER",
            f"📨 Análises publicadas hoje: {n_publicadas}/20",
            f"✅ Balanços enviados de jogos de hoje: {n_enviadas}",
            f"⏳ Resultados liquidados ainda por notificar (últimos 7 dias): {faltam}",
            "📚 As notificações são enviadas após a liquidação ESPN existente.",
            "🔒 Sem novas APIs; V1.3 e previsões originais intactas.",
        ])
