"""Alertas Telegram OWNER pré-jogo, APENAS leitura de snapshots V1.2.

Disparo: entre T-60m e T-45m (polling até ~30 s). Sem consulta OddsPapi,
alteração de odds/probabilidades ou impacto nos gates comerciais/shadow.
Uma vez por evento+mercado+kickoff, persistente em disco.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import tempfile


TZ_PT = ZoneInfo("Europe/Lisbon")
ANTECEDE_SEG = 60 * 60
MARGEM_ATRASO_SEG = 15 * 60
MAX_CARTOES_MENSAGEM = 4
VERSAO_ESTADO = 1


def _numero(valor):
    if isinstance(valor, bool):
        return None
    try:
        n = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if isfinite(n) else None


def _odd(valor):
    n = _numero(valor)
    return n if n is not None and 1.0 < n < 1000.0 else None


def _rank(valor):
    if isinstance(valor, bool):
        return None
    try:
        i = int(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return i if 1 <= i <= 5 else None


def _hora(ts):
    return datetime.fromtimestamp(float(ts), TZ_PT).strftime("%H:%M")


def _virgula(n, casas=1):
    return f"{n:.{casas}f}".replace(".", ",")


def _chave(p):
    """Identidade de previsão (não do rank, que pode repetir em reanálises)."""
    return "|".join([
        str(p["data_jogo"]),
        str(p["event_id"]),
        str(p["mercado"]),
        str(int(float(p["timestamp_jogo"]))),
    ])


def _card(p):
    ts = float(p["timestamp_jogo"])
    rank = int(p["ranking_modelo"])
    prob = float(p["probabilidade"])
    minima = _odd(p.get("odd_minima"))
    justa = _odd(p.get("odd_justa"))
    qualidade = _numero(p.get("qualidade"))
    odd_atual = _odd(p.get("odd_mercado_atual"))
    odd_reg = _odd(p.get("odd_valor_confirmado"))
    if odd_reg is None:
        odd_reg = _odd(p.get("odd_real"))
    estado = str(p.get("valor_estado") or "")
    linhas = [
        f"🏅 RANKING #{rank}  ·  ⏰ {_hora(ts)}",
        f"⚽ {p.get('casa') or '?'} vs {p.get('fora') or '?'}",
        f"🏆 {p.get('liga') or 'Competição'}",
        f"🎯 {p.get('mercado') or 'Mercado'}",
        f"📈 Modelo {_virgula(prob * 100)}% · Confiança {str(p.get('confianca_modelo') or 'N/D')}",
        ("💶 Odd registada " + (_virgula(odd_reg, 2) if odd_reg else "—")
         + " | Mín. " + (_virgula(minima, 2) if minima else "—")),
        ("⚖️ Odd justa " + (_virgula(justa, 2) if justa else "—")
         + " | Dados " + (f"{int(qualidade)}/100" if qualidade is not None and 0 <= qualidade <= 100 else "N/D")),
    ]

    # EV é apenas do MODELO, que ainda não tem calibração comprovada.
    if odd_reg is not None and minima is not None and odd_reg >= minima:
        ev = odd_reg * prob - 1
        desvio = odd_reg / minima - 1
        if ev >= 0.25 or desvio >= 0.25:
            linhas.append(
                f"🔴 RISCO MUITO ELEVADO — odd/EV invulgar ({_virgula(ev * 100)}% EV do modelo); confirmar jogo/mercado"
            )
        elif estado == "expirado" or (
            estado == "sem_valor" and odd_atual is not None and minima is not None and odd_atual < minima
        ):
            linhas.append("🔴 RISCO DE PREÇO — VALUE histórico expirado; não confirmado agora")
        elif estado == "confirmado":
            linhas.append("🟠 RISCO NÃO VALIDADO — VALUE registado, mas odds não são em direto")
        else:
            linhas.append("🟠 RISCO NÃO VALIDADO — odd histórica acima do mínimo; confirmar cotação")
    elif odd_reg is None:
        linhas.append("🔴 RISCO DE PREÇO — sem odd registada; VALUE não confirmado")
    else:
        linhas.append("🔴 RISCO DE PREÇO — odd registada inferior à mínima; sem VALUE")
    linhas.append("ℹ️ Probabilidade do modelo pode estar sobrestimada; não representa garantia.")
    return "\n".join(linhas)


class AlertasPreJogo:
    def __init__(self, path):
        self.path = Path(path) if path is not None else None

    def _ler(self):
        if self.path is None:
            raise RuntimeError("Marcador persistente não configurado")
        if not self.path.exists():
            return {"versao": VERSAO_ESTADO, "avisados": {}}
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
            if (not isinstance(dados, dict)
                or dados.get("versao") != VERSAO_ESTADO
                or not isinstance(dados.get("avisados"), dict)):
                raise ValueError("Marcador inválido")
            return dados
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError("Marcador de alertas indisponível; não sobrescrever") from exc

    def _guardar(self, dados):
        if self.path is None:
            raise RuntimeError("Marcador persistente não configurado")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".alertas_prejogo_", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _elegiveis(previsoes, agora):
        if agora.tzinfo is None:
            raise ValueError("Data aware necessária")
        ts = agora.timestamp()
        dia = agora.astimezone(TZ_PT).date().isoformat()
        vistos = set()
        items = []
        for p in previsoes or []:
            if not isinstance(p, dict) or p.get("modelo_versao") != "V1.2":
                continue
            if p.get("data_jogo") != dia or p.get("estado") != "pendente":
                continue
            rank = _rank(p.get("ranking_modelo"))
            inicio = _numero(p.get("timestamp_jogo"))
            prob = _numero(p.get("probabilidade"))
            if rank is None or inicio is None or prob is None or not 0 < prob < 1:
                continue
            if not p.get("event_id") or not p.get("mercado"):
                continue
            # A seleção também tem de existir antes do início; não gerar
            # alertas para snapshots com timestamps anómalos/retroativos.
            if not ANTECEDE_SEG - MARGEM_ATRASO_SEG <= inicio - ts <= ANTECEDE_SEG:
                continue
            chave = _chave(p)
            if chave in vistos:
                continue
            vistos.add(chave)
            items.append((inicio, rank, chave, p))
        items.sort(key=lambda x: (x[0], x[1], x[2]))
        return items

    def avisar(self, previsoes, enviar, agora=None):
        """Envia alertas com erro propagado; marca só após envio confirmado."""
        dt = agora or datetime.now(timezone.utc)
        estado = self._ler()  # falha fechada se não houver ficheiro fiável
        pendentes = [
            item for item in self._elegiveis(previsoes, dt)
            if item[2] not in estado["avisados"]
        ]
        enviados = 0
        for pos in range(0, len(pendentes), MAX_CARTOES_MENSAGEM):
            lote = pendentes[pos:pos + MAX_CARTOES_MENSAGEM]
            if not lote:
                continue
            primeiro = _hora(lote[0][0])
            header = [
                "🔔 ALERTA PRÉ-JOGO — ~1 HORA ANTES",
                f"⏰ Próximos jogos a partir das {primeiro} (Portugal)",
                f"🏅 {len(lote)} seleção(ões) Top 5 congeladas",
                "━━━━━━━━━━━━━━━━━━━━",
            ]
            mensagem = "\n\n".join(["\n".join(header)] + [_card(p) for _, _, _, p in lote])
            mensagem += "\n\n🔒 Alerta informativo: cotação histórica, sem novas consultas nem garantia de acerto."
            enviar(mensagem)
            for _, _, chave, _ in lote:
                estado["avisados"][chave] = dt.astimezone(timezone.utc).isoformat()
            # evitar crescimento ilimitado preservando registos recentes
            datas = sorted({k[:10] for k in estado["avisados"]})
            if len(datas) > 45:
                minimo = datas[-45]
                estado["avisados"] = {k: v for k, v in estado["avisados"].items() if k[:10] >= minimo}
            self._guardar(estado)
            enviados += len(lote)
        return enviados

    def relatorio(self, previsoes, agora=None):
        dt = agora or datetime.now(timezone.utc)
        estado = self._ler()
        candidatos = self._elegiveis(previsoes, dt)
        ja_enviados = set(estado["avisados"])
        pendentes = [item for item in candidatos if item[2] not in ja_enviados]
        dia = dt.astimezone(TZ_PT).date().isoformat()
        total_hoje = sum(1 for k in ja_enviados if k.startswith(dia + "|"))
        linhas = [
            "🔔 ALERTAS PRÉ-JOGO — ESTADO OWNER",
            "🕘 Envio entre 60 e 45 minutos antes de cada jogo, Portugal",
            "🎯 Apenas Top 5 V1.2, futuros e pendentes",
            f"✅ Alertas já enviados hoje: {total_hoje}",
            f"📨 Seleções na janela de envio ainda não avisadas: {len(pendentes)}",
            "🔒 Sem chamadas OddsPapi nem alterações às previsões.",
        ]
        if pendentes:
            linhas.append("")
            for _, _, _, p in pendentes[:3]:
                linhas.append(f"• {_hora(p['timestamp_jogo'])} — #{p['ranking_modelo']} {p.get('casa') or '?'} vs {p.get('fora') or '?'}")
        return "\n".join(linhas)
