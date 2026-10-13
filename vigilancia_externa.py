"""Heartbeat push para Healthchecks.io, independente do Railway.

Chamada apenas DEPOIS de ciclos Telegram bem sucedidos. Se o bot parar, o
servico externo deteta a ausencia de pings e notifica por configuracao sua.
Sem URL/chave em logs ou relatorios e sem pedidos de odds.
"""
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit
import json
import os
import tempfile

import requests


class VigilanciaExterna:
    INTERVALO_SEG = 5 * 60

    def __init__(self, path=None, env=None, session=None, tempo=None):
        self.path = Path(path) if path is not None else None
        self.env = os.environ if env is None else env
        self.session = session or requests.Session()
        self._tempo = tempo or monotonic
        self._proximo = 0.0

    @staticmethod
    def _url_seguro(texto):
        if not texto:
            return None
        v = urlsplit(str(texto).strip())
        # Somente pings HTTPS para Healthchecks.io, nunca enviar segredos
        # por HTTP ou URL arbitraria (SSRF/misconfiguration).
        if v.scheme != "https" or v.hostname != "hc-ping.com" or v.port not in (None, 443):
            raise ValueError("Destino de heartbeat externo invalido")
        if v.username or v.password or v.query or v.fragment:
            raise ValueError("URL de heartbeat insegura")
        import re
        if not re.fullmatch(r"/[a-zA-Z0-9-]{20,100}", v.path):
            raise ValueError("Identificador de heartbeat invalido")
        return str(texto).strip()

    def configurado(self, var="HEALTHCHECKS_PING_URL"):
        return bool(self.env.get(var, "").strip())

    def ping(self, var="HEALTHCHECKS_PING_URL", agora=None, forcar=False):
        if not self.configurado(var):
            return False
        t = self._tempo()
        if not forcar and t < self._proximo:
            return False
        self._proximo = t + self.INTERVALO_SEG
        url = self._url_seguro(self.env[var])
        try:
            r = self.session.get(url, timeout=(3, 6), allow_redirects=False)
            if r.status_code != 200:
                raise RuntimeError("Monitor externo recusou o heartbeat")
        except (requests.RequestException, RuntimeError):
            # Nunca incluir str(exception) porque contem o token da URL.
            raise RuntimeError("Falha no heartbeat externo") from None
        if self.path is not None:
            self._guardar({
                "ultimo_sucesso": (agora or datetime.now(timezone.utc)).isoformat(),
                "monitor": var,
            })
        return True

    def _guardar(self, data):
        if self.path.is_symlink():
            raise RuntimeError("Estado de ping inseguro")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, nome = tempfile.mkstemp(dir=self.path.parent, prefix=".hc_ping_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(nome, self.path)
        finally:
            if os.path.exists(nome):
                os.unlink(nome)

    def relatorio(self, var="HEALTHCHECKS_PING_URL"):
        if not self.configurado(var):
            return "🔔 VIGILANCIA EXTERNA — ainda nao configurada."
        try:
            self._url_seguro(self.env[var])
        except (ValueError, TypeError):
            return "🔴 VIGILANCIA EXTERNA — URL de monitorizacao invalida."
        if self.path is None or not self.path.exists() or self.path.is_symlink():
            ultima = "ainda sem pings confirmados neste processo"
        else:
            try:
                estado = json.loads(self.path.read_text(encoding="utf-8"))
                ultima = estado.get("ultimo_sucesso") or "ainda nenhum"
            except (ValueError, OSError, TypeError):
                ultima = "estado local indisponivel"
        return "\n".join([
            "🔔 VIGILANCIA EXTERNA — HEALTHCHECKS.IO",
            "Configuracao: presente",
            f"Ultimo ping HTTP 200: {ultima}",
            "Pings: apos ciclos Telegram completos, a cada 5 minutos.",
            "Se Railway ou polling parar, alertas sao emitidos pelo servico externo.",
            "⚠️ Confirmar canais de alerta e janela de tolerancia (15-20 min) no Healthchecks.",
            "ℹ️ Relatorio local, sem API. URL privada nunca e exibida.",
        ])
