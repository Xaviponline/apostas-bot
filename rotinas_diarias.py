"""Liquidacao ESPN e resumo diario do OWNER; sem acesso a OddsPapi.

Executa apenas fora das janelas de odds/CLV e reutiliza exclusivamente a
rotina existente de liquidacao por resultado FINAL, sem alterar modelo,
probabilidade, snapshots ou odds iniciais. Marcador persistente e atomico.
"""
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import tempfile


TZ = ZoneInfo("Europe/Lisbon")


class RotinasDiarias:
    INTERVALO_LIQUIDACAO = timedelta(hours=2)
    ATRASO_MINIMO_JOGO = timedelta(hours=3)
    # Janelas apenas de madrugada e inicio de tarde. Nada entre 15:30 e 00:45.
    JANELAS = ((0, 45, 8, 30), (11, 0, 15, 30))
    INICIO_RELATORIO = (10, 30)
    FIM_RELATORIO = (15, 30)

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None

    @staticmethod
    def _local(agora=None):
        dt = agora or datetime.now(TZ)
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("Hora da rotina sem fuso horario")
        return dt.astimezone(TZ)

    @staticmethod
    def _timestamp_seguro(valor):
        try:
            valor = float(valor)
            if 0 < valor < 3000000000:
                return valor
        except (TypeError, ValueError, OverflowError):
            pass
        return None

    def _ler(self):
        if self.path is None:
            return {}
        if self.path.is_symlink():
            raise RuntimeError("Marcador das rotinas inseguro")
        if not self.path.exists():
            return {}
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(d, dict):
                raise ValueError("Marcador incorreto")
            for name in ("ultima_liquidacao_tentada", "ultimo_relatorio_enviado"):
                if name in d and not isinstance(d[name], str):
                    raise ValueError("Marcador incorreto")
            return d
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError("Marcador das rotinas invalido; nao sobrescrever") from exc

    def _guardar(self, d):
        if self.path is None:
            raise RuntimeError("Volume persistente em falta")
        if self.path.is_symlink():
            raise RuntimeError("Marcador inseguro")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".rotinas_", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @classmethod
    def _na_janela(cls, momento):
        minutos = momento.hour * 60 + momento.minute
        return any(
            inicio_h * 60 + inicio_m <= minutos < fim_h * 60 + fim_m
            for inicio_h, inicio_m, fim_h, fim_m in cls.JANELAS
        )

    @classmethod
    def _pendentes_maduros(cls, previsoes, momento):
        agora_ts = momento.timestamp()
        minimo = cls.ATRASO_MINIMO_JOGO.total_seconds()
        return [
            p for p in previsoes.dados.get("previsoes", [])
            if p.get("estado") == "pendente"
            and (ts := cls._timestamp_seguro(p.get("timestamp_jogo"))) is not None
            and agora_ts - ts >= minimo
        ]

    def liquidar_se_devido(self, previsoes, agora=None):
        """Uma tentativa por >=2h; so se ha jogos maduros e ESPN confirma finais."""
        if self.path is None:
            return 0
        dt = self._local(agora)
        if not self._na_janela(dt):
            return 0
        if not self._pendentes_maduros(previsoes, dt):
            return 0
        d = self._ler()
        anterior = d.get("ultima_liquidacao_tentada")
        if anterior:
            try:
                prev = datetime.fromisoformat(anterior)
                if prev.tzinfo is None:
                    raise ValueError("Sem fuso")
                if timedelta(0) <= dt - prev.astimezone(TZ) < self.INTERVALO_LIQUIDACAO:
                    return 0
            except (TypeError, ValueError):
                raise RuntimeError("Data de ultima tentativa invalida")
        # Marcador BEFORE chamadas ESPN limita repeticao apos falhas/restarts.
        d["ultima_liquidacao_tentada"] = dt.isoformat()
        self._guardar(d)
        # A implementacao ja existente so aceita scores finais, sem OddsPapi.
        total = int(previsoes.atualizar_pendentes())
        # Preservar campos quando existir edicao manual concorrente (processo unico).
        d["ultimo_total_liquidado"] = total
        d["ultima_liquidacao_concluida"] = dt.isoformat()
        self._guardar(d)
        return total

    @staticmethod
    def _formatar_roi(roi):
        if roi is None:
            return "sem dados"
        return f"{float(roi)*100:+.1f}%".replace(".", ",")

    @classmethod
    def texto_resumo(cls, previsoes, agora=None):
        """Relatorio local do DIA ANTERIOR e progresso ACUMULADO da V1.3."""
        dt = cls._local(agora)
        ontem = (dt - timedelta(days=1)).date().isoformat()
        todos = previsoes.dados.get("previsoes", [])
        anteriores = [p for p in todos if p.get("data_jogo") == ontem]
        terminados = [p for p in anteriores if p.get("resultado_binario") in (0, 1)]
        ganhos = sum(int(p["resultado_binario"]) for p in terminados)
        falta_ontem = len(anteriores) - len(terminados)
        pendentes_antigos = cls._pendentes_maduros(previsoes, dt)
        m = previsoes.metricas_v13_comercial()
        pl = m.get("lucro_unidades")
        resultado = "sem liquidadas"
        if m["liquidadas"]:
            resultado = f"{float(pl):+.2f}u".replace(".", ",")
        clv_media = m.get("clv_media")
        clv_str = cls._formatar_roi(clv_media) if m["clv_amostras"] else "ainda sem fechos"
        linhas = [
            "📨 RESUMO DIARIO — OWNER",
            f"📅 Relatorio de {dt.strftime('%d/%m/%Y')} | Jogos de {ontem}",
            "",
            "📊 RESULTADOS DE ONTEM — TODAS AS PREVISOES",
            f"• Registadas: {len(anteriores)}",
            f"• Liquidadas: {len(terminados)} | Pendentes: {falta_ontem}",
            f"• ✅ {ganhos} | ❌ {len(terminados)-ganhos}",
            "",
            "💼 V1.3 TOP5 + VALUE — COORTE PROSPETIVA ACUMULADA",
            f"• Entradas: {m['coorte_tamanho']}/{m['alvo']} | Liquidadas: {m['liquidadas']} | Pendentes: {m['pendentes']}",
            f"• Dias: {m['dias']}/{m['min_dias']} | CLV: {m['clv_amostras']}/{m['min_clv_amostras']} minimo",
            f"• ✅ {m['ganhos']} | ❌ {m['perdas']}",
            f"• P/L: {resultado} | ROI: {cls._formatar_roi(m.get('roi'))}",
            f"• CLV medio: {clv_str}",
        ]
        if pendentes_antigos:
            linhas += ["", f"⚠️ {len(pendentes_antigos)} previsao(oes) com jogos antigos ainda sem resultado confirmado."]
            for p in pendentes_antigos[:3]:
                linhas.append(
                    f"• {p.get('data_jogo') or '?'} "
                    f"{str(p.get('casa') or '?')[:32]} vs {str(p.get('fora') or '?')[:32]}"
                )
            linhas.append("Sem liquidacao forcada; confirmar a fonte ESPN.")
        linhas += [
            "",
            "🔒 V1.2 e SEL1 congeladas; V1.3 com 50 entradas fixas, sem promocao automatica.",
            "ℹ️ Resultados e ROI sao historicos; nao garantem resultados futuros.",
            "ℹ️ Sem pedidos OddsPapi. /v13_comercial para ver o protocolo completo.",
        ]
        return "\n".join(linhas)

    def enviar_relatorio_se_devido(self, previsoes, enviar, agora=None):
        """Uma mensagem por dia e apenas no horario matinal, apos sucesso Telegram."""
        if self.path is None or enviar is None:
            return False
        dt = self._local(agora)
        hora = (dt.hour, dt.minute)
        if not (self.INICIO_RELATORIO <= hora < self.FIM_RELATORIO):
            return False
        d = self._ler()
        dia = dt.date().isoformat()
        if d.get("ultimo_relatorio_enviado") == dia:
            return False
        mensagem = self.texto_resumo(previsoes, dt)
        enviar(mensagem)
        # Se ocorrer uma falha no envio, nao marca. Crash entre enviar/guardar
        # pode originar repeticao; nao e possivel entrega exatamente uma vez.
        d["ultimo_relatorio_enviado"] = dia
        d["ultimo_relatorio_em"] = dt.isoformat()
        self._guardar(d)
        return True

    def relatorio_estado(self, previsoes, agora=None):
        dt = self._local(agora)
        d = self._ler()
        maduros = len(self._pendentes_maduros(previsoes, dt))
        return "\n".join([
            "🗓️ ROTINAS DIARIAS — ADMIN",
            "Liquidacao ESPN: automatica entre 00:45–08:30 e 11:00–15:30 (Portugal).",
            "Intervalo de verificacao: minimo 2 horas, apenas com jogos iniciados ha >=3h.",
            f"Ultima tentativa ESPN: {d.get('ultima_liquidacao_tentada') or 'ainda nenhuma'}",
            f"Ultima conclusao ESPN: {d.get('ultima_liquidacao_concluida') or 'ainda nenhuma'}",
            f"Liquidadas na ultima tentativa: {d.get('ultimo_total_liquidado', 0)}",
            f"Pendentes maduros neste instante: {maduros}",
            "Resumo diario OWNER: entre 10:30 e 15:30 (Portugal).",
            f"Ultimo resumo enviado: {d.get('ultimo_relatorio_enviado') or 'ainda nenhum'}",
            "🔒 Sem OddsPapi e sem mudancas ao modelo, odds iniciais ou V1.3.",
            "ℹ️ Este comando nao faz consultas externas.",
        ])
