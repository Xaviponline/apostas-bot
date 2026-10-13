"""Observacao da coorte CLV V1.3: apenas leitura dos snapshots.

Os alertas sao mensagens administrativas sobre falhas de recolha ja ocorridas,
sem consultar OddsPapi, alterar snapshots, odds, selecoes ou gate comercial.
"""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import tempfile


TZ_PORTUGAL = ZoneInfo("Europe/Lisbon")


class ObservatorioCLV:
    # Apos o inicio do jogo ja nao e possivel recolher CLV pre-jogo.
    ATRASO_AVISO_SEG = 5 * 60
    MAX_ATRASO_AVISO_SEG = 60 * 60

    def __init__(self, path=None):
        self.path = Path(path) if path else None

    @staticmethod
    def _agora(agora=None):
        dt = agora or datetime.now(timezone.utc)
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("Hora sem fuso horario.")
        return dt.timestamp()

    @staticmethod
    def _identificador(p):
        return f"{p['snapshot']}:{p['data_jogo']}"

    def dados(self, previsoes, agora=None):
        """Reutiliza a coorte fixa de metricas_v13_comercial(), sem replica-la."""
        ts_agora = self._agora(agora)
        metricas = previsoes.metricas_v13_comercial()
        registos = previsoes.dados.get("previsoes", [])
        detalhes = []
        totais = {
            "com_fecho": 0,
            "antes_janela": 0,
            "em_janela": 0,
            "inicio_recente": 0,
            "sem_fecho": 0,
            "horario_indisponivel": 0,
        }
        for p in metricas["coorte"]:
            indice = int(p["snapshot"]) - 1
            original = registos[indice] if 0 <= indice < len(registos) else {}
            inicio = original.get("timestamp_jogo")
            fecho = p.get("odd_fecho")
            if fecho is not None:
                situacao = "com_fecho"
            elif not isinstance(inicio, (int, float)):
                situacao = "horario_indisponivel"
            elif float(inicio) > ts_agora + 1800:
                situacao = "antes_janela"
            elif float(inicio) > ts_agora:
                situacao = "em_janela"
            elif ts_agora - float(inicio) < self.ATRASO_AVISO_SEG:
                situacao = "inicio_recente"
            else:
                situacao = "sem_fecho"

            totais[situacao] += 1
            detalhes.append({
                **p,
                "timestamp_jogo": inicio,
                "situacao": situacao,
                "id_aviso": self._identificador(p),
            })
        return {"metricas": metricas, "totais": totais, "detalhes": detalhes}

    def relatorio(self, previsoes, agora=None):
        d = self.dados(previsoes, agora=agora)
        t = d["totais"]
        m = d["metricas"]
        linhas = [
            "🔎 DIAGNOSTICO CLV — V1.3 TOP5 + VALUE",
            "🔒 Apenas leitura; mesma coorte fixa do /v13_comercial",
            "",
            f"Coorte: {m['coorte_tamanho']}/{m['alvo']} | CLV oficial: {t['com_fecho']}/{m['coorte_tamanho']}",
            f"✅ Com fecho: {t['com_fecho']}",
            f"🕒 Antes da janela T-30m: {t['antes_janela']}",
            f"⏳ Na janela T-30m: {t['em_janela']}",
            f"⚪ Jogo iniciado ha menos de 5m: {t['inicio_recente']}",
            f"⚠️ Sem fecho apos o inicio: {t['sem_fecho']}",
        ]
        if t["horario_indisponivel"]:
            linhas.append(f"❓ Hora de inicio indisponivel: {t['horario_indisponivel']}")
        sem = [p for p in d["detalhes"] if p["situacao"] == "sem_fecho"]
        if sem:
            linhas.extend(["", "⚠️ FECHOS EM FALTA (mais recentes)"])
            for p in sorted(sem, key=lambda x: float(x["timestamp_jogo"] or 0), reverse=True)[:6]:
                linhas.append(
                    f"• #{p['snapshot']} {p['data_jogo']} {p['casa']} vs {p['fora']} | {p['mercado']}"
                )
            if len(sem) > 6:
                linhas.append(f"• +{len(sem)-6} outros; consultar /carteira_detalhe")
        linhas.extend([
            "",
            "ℹ️ Sem fecho nao indica necessariamente erro de API; causa ainda por apurar.",
            "🛡️ Nenhuma odd e inferida e nenhum dado historico e reescrito.",
            "ℹ️ Nao consulta a OddsPapi.",
        ])
        return "\n".join(linhas)

    def _ler_avisados(self):
        if self.path is None:
            raise RuntimeError("Sem volume persistente.")
        if not self.path.exists():
            return set()
        try:
            estado = json.loads(self.path.read_text(encoding="utf-8"))
            avisados = estado.get("avisados") if isinstance(estado, dict) else None
            if not isinstance(avisados, list) or not all(isinstance(v, str) for v in avisados):
                raise ValueError("Marcador CLV invalido.")
            return set(avisados)
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError("Marcador CLV indisponivel; alertas suspensos.") from exc

    def _guardar_avisados(self, avisados):
        if self.path is None:
            raise RuntimeError("Sem volume persistente.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporario = tempfile.mkstemp(prefix=".clv_avisos_", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"avisados": sorted(avisados)}, f, ensure_ascii=False, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporario, self.path)
        finally:
            if os.path.exists(temporario):
                os.unlink(temporario)

    def avisar_fechos_em_falta(self, previsoes, enviar, agora=None):
        """Avisa owner uma unica vez por entrada, 5 a 60 min apos inicio.

        Nao cria alertas retroativos em massa ao fazer deploy. Um erro de envio
        nao marca como enviado, permitindo nova tentativa.
        """
        if self.path is None:
            return 0
        ts_agora = self._agora(agora)
        hoje = datetime.fromtimestamp(ts_agora, tz=timezone.utc).astimezone(
            TZ_PORTUGAL
        ).strftime("%Y-%m-%d")
        d = self.dados(previsoes, agora=agora)
        candidatos = [
            p for p in d["detalhes"]
            if p["situacao"] == "sem_fecho"
            and p["data_jogo"] == hoje
            and isinstance(p["timestamp_jogo"], (int, float))
            and self.ATRASO_AVISO_SEG <= ts_agora - p["timestamp_jogo"] < self.MAX_ATRASO_AVISO_SEG
        ]
        if not candidatos:
            return 0
        avisados = self._ler_avisados()  # Se corrompido, falhar fechado.
        novos = [p for p in candidatos if p["id_aviso"] not in avisados]
        if not novos:
            return 0
        linhas = [
            "⚠️ CLV EM FALTA — V1.3",
            f"{len(novos)} entrada(s) da coorte sem fecho pre-jogo registado:",
        ]
        for p in novos[:8]:
            linhas.append(f"• #{p['snapshot']} {p['casa']} vs {p['fora']} | {p['mercado']}")
        if len(novos) > 8:
            linhas.append(f"• +{len(novos)-8} outras")
        linhas.extend([
            "ℹ️ Motivo desconhecido: nao significa necessariamente falha da OddsPapi.",
            "🔎 Usa /clv_diagnostico para auditoria.",
            "🛡️ Sem consultar odds nem alterar a coorte V1.3.",
        ])
        enviar("\n".join(linhas))
        avisados.update(p["id_aviso"] for p in novos)
        self._guardar_avisados(avisados)
        return len(novos)
