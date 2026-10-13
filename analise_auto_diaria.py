"""Execucao diaria idempotente da analise premium, sem tocar no modelo.

O job corre numa janela curta em Europe/Lisbon, uma vez por data local.
O estado fica junto dos snapshots no volume persistente. Em caso de erro,
ha retry limitado; se o marcador estiver corrompido, falha fechado.
"""
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import logging
import os
import tempfile


TZ_PORTUGAL = ZoneInfo("Europe/Lisbon")


class AgendadorAnaliseDiaria:
    INICIO = time(9, 0)
    FIM = time(10, 0)
    INTERVALO_RETRY = timedelta(minutes=10)

    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self._ultima_tentativa = None

    @staticmethod
    def _local(agora=None):
        momento = agora if agora is not None else datetime.now(TZ_PORTUGAL)
        if momento.tzinfo is None or momento.utcoffset() is None:
            raise ValueError("Instante de analise sem fuso horario.")
        return momento.astimezone(TZ_PORTUGAL)

    def _ler_estado(self):
        if self.path is None:
            return {}
        try:
            if not self.path.exists():
                return {}
            estado = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(estado, dict) or not isinstance(estado.get("data"), str):
                raise ValueError("Marcador de analise invalido.")
            return estado
        except (OSError, ValueError, TypeError) as exc:
            # Nunca apagar/sobrescrever um marcador ilegivel; evita reexecucoes indevidas.
            raise RuntimeError("Marcador de analise diaria indisponivel.") from exc

    def devido(self, agora=None):
        if self.path is None:
            return False
        momento = self._local(agora)
        if not self.INICIO <= momento.time().replace(tzinfo=None) < self.FIM:
            return False
        if (
            self._ultima_tentativa is not None
            and self._ultima_tentativa.date() == momento.date()
            and momento - self._ultima_tentativa < self.INTERVALO_RETRY
        ):
            return False
        try:
            estado = self._ler_estado()
        except RuntimeError:
            logging.warning("ANALISE_AUTO | marcador indisponivel; execucao suspensa")
            return False
        return estado.get("data") != momento.date().isoformat()

    def _guardar_sucesso(self, momento):
        if self.path is None:
            raise RuntimeError("Sem volume persistente para analise diaria.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        marcador = {
            "data": momento.date().isoformat(),
            "executada_em": momento.isoformat(),
            "modo": "automatico",
        }
        fd, temporario = tempfile.mkstemp(prefix=".analise_auto_", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as ficheiro:
                json.dump(marcador, ficheiro, ensure_ascii=False, sort_keys=True)
                ficheiro.flush()
                os.fsync(ficheiro.fileno())
            os.replace(temporario, self.path)
        finally:
            if os.path.exists(temporario):
                os.unlink(temporario)

    def executar_se_devido(self, acao, agora=None):
        """Regista sucesso apenas apos a analise terminar.

        A propria analise protege os snapshots contra reescrita, mesmo se houver
        reinicio do processo entre o registo das previsoes e este marcador.
        """
        momento = self._local(agora)
        if not self.devido(momento):
            return False
        self._ultima_tentativa = momento
        try:
            acao()
            self._guardar_sucesso(momento)
            logging.info("ANALISE_AUTO | analise diaria concluida em %s", momento.date().isoformat())
            return True
        except Exception as exc:
            # A falha nao bloqueia Telegram, ODDS_AUTO ou CLV_AUTO.
            logging.warning("ANALISE_AUTO | falha (%s); proxima tentativa >=10 min", type(exc).__name__)
            return False

    def relatorio(self, agora=None):
        momento = self._local(agora)
        if self.path is None:
            estado = "⚪ Indisponivel: previsoes sem volume persistente"
        else:
            try:
                marcador = self._ler_estado()
                if marcador.get("data") == momento.date().isoformat():
                    estado = "🟢 Analise automatica de hoje concluida"
                else:
                    estado = "🕘 A aguardar janela diaria, ou nova tentativa"
            except RuntimeError:
                marcador = {}
                estado = "🟠 Marcador ilegivel: execucao automatica suspensa"
        ultima = marcador.get("executada_em", "ainda sem execucoes") if self.path else "n/a"
        return "\n".join([
            "🕘 ANALISE DIARIA AUTOMATICA",
            "Horario: 09:00–10:00 (Portugal, incluindo horario de verao)",
            "Frequencia: no maximo uma analise concluida por dia",
            f"Estado: {estado}",
            f"Ultima execucao automatica: {ultima}",
            "Falhas temporarias: nova tentativa apos 10 minutos, dentro da janela",
            "🔒 Sem alteracoes ao modelo V1.2, ranking, SEL1 ou protocolo V1.3.",
            "ℹ️ Consulta local: sem gastos na OddsPapi.",
        ])
