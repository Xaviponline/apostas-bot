"""Copias de seguranca locais, auditaveis e de restauro exclusivamente manual.

Copia apenas ficheiros de estado em /data para pastas com hash SHA-256. Nao
altera fontes, snapshots, cotacoes nem dados dos clientes. Copias neste
mesmo volume NAO protegem contra perda/corrupcao do proprio volume Railway.
"""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
import os
import re
import shutil
import tempfile


TZ = ZoneInfo("Europe/Lisbon")


class CopiasSeguranca:
    RETER_DIAS = 14
    MIN_HORA = (9, 15)
    LIMITE_FICHEIRO = 30 * 1024 * 1024
    LIMITE_TOTAL = 50 * 1024 * 1024
    FICHEIROS = (
        "previsoes_premium.json",
        "apostas_historico.json",
        "acessos_premium.json",
        "analise_diaria_auto.json",
        "odds_pedidos.json",
        "odds_cobertura.json",
        "odds_verificacoes.json",
        "clv_avisos.json",
        "odds_rastreio.jsonl",
    )

    def __init__(self, pasta):
        self.pasta = Path(pasta) if pasta is not None else None
        self.destino = self.pasta / "backups_locais" if self.pasta is not None else None

    @staticmethod
    def _agora(agora=None):
        dt = agora or datetime.now(TZ)
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("Hora sem fuso horario")
        return dt.astimezone(TZ)

    @staticmethod
    def _hash(dados):
        return hashlib.sha256(dados).hexdigest()

    def _nomes(self):
        if self.destino is None or not self.destino.is_dir():
            return []
        return sorted(
            [p for p in self.destino.iterdir()
             if p.is_dir() and not p.is_symlink() and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", p.name)],
            key=lambda p: p.name, reverse=True,
        )

    @staticmethod
    def _escrever(path, dados):
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(dados)
            f.flush()
            os.fsync(f.fileno())

    def validar(self, pasta):
        pasta = Path(pasta)
        if pasta.is_symlink():
            return False
        try:
            m = json.loads((pasta / "manifest.json").read_text(encoding="utf-8"))
            if not isinstance(m, dict) or not isinstance(m.get("ficheiros"), dict):
                return False
            if not m["ficheiros"] or "previsoes_premium.json" not in m["ficheiros"]:
                return False
            for nome, meta in m["ficheiros"].items():
                if nome not in self.FICHEIROS or (pasta / nome).is_symlink():
                    return False
                dados = (pasta / nome).read_bytes()
                if len(dados) != meta["bytes"] or self._hash(dados) != meta["sha256"]:
                    return False
                if nome.endswith(".json"):
                    json.loads(dados)
            return True
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return False

    def executar_se_devido(self, agora=None):
        if self.pasta is None:
            return False
        dt = self._agora(agora)
        if (dt.hour, dt.minute) < self.MIN_HORA:
            return False
        if self.pasta.is_symlink():
            raise RuntimeError("Pasta de estado nao pode ser symlink")
        if not self.pasta.is_dir():
            raise RuntimeError("Volume de dados indisponivel")
        if self.destino.is_symlink():
            raise RuntimeError("Pasta de backup insegura")
        self.destino.mkdir(mode=0o700, parents=True, exist_ok=True)
        alvo = self.destino / dt.date().isoformat()
        if alvo.exists():
            if not self.validar(alvo):
                raise RuntimeError("Backup existente invalido; nao foi substituido")
            return False

        temp = Path(tempfile.mkdtemp(prefix=".backup_em_curso_", dir=self.destino))
        os.chmod(temp, 0o700)
        try:
            manifest = {
                "versao": 1,
                "data": dt.date().isoformat(),
                "criado_em": dt.isoformat(),
                "ficheiros": {},
                "nota": "Copia local no mesmo volume; restauro apenas manual",
            }
            total = 0
            for nome in self.FICHEIROS:
                origem = self.pasta / nome
                if not origem.exists():
                    if nome == "previsoes_premium.json":
                        raise RuntimeError("Ficheiro essencial de previsoes em falta")
                    continue
                if origem.is_symlink() or not origem.is_file():
                    raise RuntimeError("Origem do backup invalida")
                if origem.stat().st_size > self.LIMITE_FICHEIRO:
                    raise RuntimeError("Backup ultrapassou limite por ficheiro")
                dados = origem.read_bytes()
                total += len(dados)
                if total > self.LIMITE_TOTAL:
                    raise RuntimeError("Backup ultrapassou limite de tamanho")
                if nome.endswith(".json"):
                    json.loads(dados)
                self._escrever(temp / nome, dados)
                manifest["ficheiros"][nome] = {
                    "bytes": len(dados), "sha256": self._hash(dados)
                }
            self._escrever(
                temp / "manifest.json",
                json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            if not self.validar(temp):
                raise RuntimeError("Verificacao SHA-256 falhou")
            os.replace(temp, alvo)
        finally:
            if temp.exists():
                shutil.rmtree(temp)
        for antigo in self._nomes()[self.RETER_DIAS:]:
            shutil.rmtree(antigo)
        return True

    def relatorio(self, agora=None):
        if self.destino is None:
            return "💾 BACKUPS — sem volume persistente; indisponiveis."
        nomes = self._nomes()
        ultimo = nomes[0] if nomes else None
        valido = self.validar(ultimo) if ultimo else None
        hoje = self._agora(agora).date().isoformat()
        return "\n".join([
            "💾 COPIAS DE SEGURANCA — VOLUME LOCAL",
            f"Hoje: {hoje}",
            f"Ultimo backup: {ultimo.name if ultimo else 'nenhum'}",
            f"Integridade SHA-256: {'✅ VALIDA' if valido else '🔴 FALHA' if ultimo else '⚪ SEM BACKUP'}",
            f"Copias retidas: {len(nomes)} (maximo {self.RETER_DIAS})",
            "Execucao: 1 vez/dia apos 09:15, hora de Portugal",
            "🔒 Apenas leitura do historico; restauro manual, nunca automatico.",
            "⚠️ COPIA NO MESMO VOLUME: nao substitui backup externo nem snapshots nativos Railway.",
            "ℹ️ /backup_status nao faz consultas OddsPapi.",
        ])
