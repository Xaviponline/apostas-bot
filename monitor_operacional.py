"""Saude interna do bot: heartbeat local e alertas de tarefas em atraso.

Depende do proprio processo: NAO detecta uma paragem total enquanto ela dura.
A verificacao externa Railway/uptime tem de ser configurada separadamente.
"""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import tempfile


TZ = ZoneInfo("Europe/Lisbon")


class MonitorOperacional:
    INTERVALO_ALERTA_HORA = (10, 15)

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None

    @staticmethod
    def _agora(agora=None):
        dt = agora or datetime.now(TZ)
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("Hora sem fuso horario")
        return dt.astimezone(TZ)

    def _ler(self):
        if self.path is None:
            return {"heartbeat": None, "avisados": []}
        if not self.path.exists():
            return {"heartbeat": None, "avisados": []}
        if self.path.is_symlink():
            raise RuntimeError("Estado de monitorizacao inseguro")
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(d, dict) or not isinstance(d.get("avisados"), list):
                raise ValueError("Estado invalido")
            if not all(isinstance(v, str) for v in d["avisados"]):
                raise ValueError("Avisos invalidos")
            return d
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError("Estado do monitor corrompido; nao sobrescrever") from exc

    def _guardar(self, d):
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".monitor_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def verificar(self, agenda_analise, backups, enviar=None, agora=None):
        """Atualiza heartbeat e avisa atrasos diários uma vez por causa/data."""
        if self.path is None:
            return 0
        dt = self._agora(agora)
        d = self._ler()
        avisados = set(d["avisados"])
        pendentes = []
        data = dt.date().isoformat()
        if (dt.hour, dt.minute) >= self.INTERVALO_ALERTA_HORA:
            estado = agenda_analise.relatorio(agora=dt)
            if f"Ultima execucao automatica: {data}T" not in estado:
                pendentes.append(("analise", "A analise automatica de hoje nao tem execucao concluida."))
            nomes = backups._nomes()
            if not nomes or nomes[0].name != data or not backups.validar(nomes[0]):
                pendentes.append(("backup", "Nao existe backup local valido de hoje."))
        novos = [(chave, texto) for chave, texto in pendentes if f"{data}:{chave}" not in avisados]
        if novos and enviar is not None:
            mensagem = [
                "🚨 MONITOR OPERACIONAL — ADMIN",
                *[f"• {texto}" for _, texto in novos],
                "🔎 /monitor_status e /backup_status para detalhes.",
                "ℹ️ Diagnostico interno; nao prova que Railway esteja indisponivel.",
            ]
            enviar("\n".join(mensagem))
            avisados.update(f"{data}:{chave}" for chave, _ in novos)
        d["heartbeat"] = dt.isoformat()
        d["avisados"] = sorted(avisados)[-60:]
        self._guardar(d)
        return len(novos) if enviar is not None else 0

    def relatorio(self, agenda_analise, backups, agora=None):
        dt = self._agora(agora)
        d = self._ler()
        hb = d.get("heartbeat")
        atraso = None
        try:
            if hb:
                t = datetime.fromisoformat(str(hb))
                if t.tzinfo is not None:
                    atraso = max((dt - t.astimezone(TZ)).total_seconds(), 0)
        except (ValueError, TypeError):
            pass
        analise = agenda_analise.relatorio(agora=dt)
        analise_ok = f"Ultima execucao automatica: {dt.date().isoformat()}T" in analise
        nomes = backups._nomes()
        backup_ok = bool(nomes and nomes[0].name == dt.date().isoformat() and backups.validar(nomes[0]))
        if atraso is None:
            estado = "⚪ Sem heartbeat"
        elif atraso > 600:
            estado = "⚠️ Heartbeat antigo"
        else:
            estado = "🟢 Heartbeat recente"
        return "\n".join([
            "🩺 MONITOR OPERACIONAL — INTERNO",
            f"Estado: {estado}",
            f"Ultimo heartbeat: {hb or 'ainda nenhum'}",
            f"Analise de hoje: {'✅' if analise_ok else '⚪ Sem execucao registada'}",
            f"Backup de hoje: {'✅' if backup_ok else '⚪ Ainda sem copia valida'}",
            f"Alertas ja enviados (historico marcador): {len(d.get('avisados') or [])}",
            "Avisos de tarefas em atraso apos 10:15, hora de Portugal.",
            "⚠️ Monitor interno nao pode notificar durante paragem total do bot.",
            "ℹ️ Apenas leitura; zero pedidos OddsPapi.",
        ])
