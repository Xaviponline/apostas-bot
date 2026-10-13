"""Backup offsite encriptado AES-256-GCM, com verificacao de restauro.

Desativado por defeito. Envia SOMENTE o arquivo cifrado para um bucket S3
fora do Railway quando todas as variaveis forem explicitamente configuradas.
Nunca restaura, elimina ou altera os snapshots em producao.
"""
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import tempfile
import zipfile

from backups_locais import CopiasSeguranca


TZ = ZoneInfo("Europe/Lisbon")
MAGIC = b"APOSTAS-OFFSITE-V1\x00"
CHAVE_DIA = re.compile(r"^20\d{2}-\d{2}-\d{2}$")


class BackupExterno:
    MIN_HORA = (9, 30)
    HORA_LIMITE = 18
    MAX_ZIP_BYTES = 60 * 1024 * 1024
    VARS = (
        "BACKUP_S3_ENDPOINT_URL", "BACKUP_S3_REGION", "BACKUP_S3_BUCKET",
        "BACKUP_S3_ACCESS_KEY_ID", "BACKUP_S3_SECRET_ACCESS_KEY",
        "BACKUP_AES256_KEY_B64",
    )

    def __init__(self, backups, env=None, client=None):
        self.backups = backups
        self.env = os.environ if env is None else env
        self.client = client
        self.state = (
            backups.pasta / "backup_externo_estado.json"
            if backups.pasta is not None else None
        )

    def estado_config(self):
        presente = sum(bool(str(self.env.get(k) or "").strip()) for k in self.VARS)
        if presente == 0:
            return "desativado"
        return "configurado" if presente == len(self.VARS) else "incompleto"

    def _config(self):
        if self.estado_config() != "configurado":
            raise RuntimeError("Backup externo ainda nao configurado")
        endpoint = str(self.env["BACKUP_S3_ENDPOINT_URL"]).strip()
        url = urlparse(endpoint)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Endpoint S3 tem de usar HTTPS sem credenciais na URL")
        if not re.fullmatch(r"[a-zA-Z0-9.\-]+", url.hostname):
            raise ValueError("Hostname S3 invalido")
        bucket = str(self.env["BACKUP_S3_BUCKET"]).strip()
        if not re.fullmatch(r"[a-zA-Z0-9._-]{3,63}", bucket):
            raise ValueError("Bucket invalido")
        prefix = str(self.env.get("BACKUP_S3_PREFIX") or "apostas-bot-offsite").strip().strip("/")
        if not re.fullmatch(r"[a-zA-Z0-9_./-]{1,100}", prefix) or ".." in prefix.split("/"):
            raise ValueError("Prefixo inseguro")
        try:
            raw = base64.b64decode(str(self.env["BACKUP_AES256_KEY_B64"]).strip(), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Chave AES-256 invalida") from exc
        if len(raw) != 32:
            raise ValueError("A chave AES-256 tem de ter 32 bytes")
        return {
            "endpoint": endpoint,
            "region": str(self.env["BACKUP_S3_REGION"]).strip(),
            "bucket": bucket,
            "prefix": prefix,
            "key": raw,
            "access": str(self.env["BACKUP_S3_ACCESS_KEY_ID"]).strip(),
            "secret": str(self.env["BACKUP_S3_SECRET_ACCESS_KEY"]).strip(),
        }

    def _s3(self, cfg):
        if self.client is not None:
            return self.client
        import boto3
        from botocore.config import Config
        return boto3.client(
            "s3",
            endpoint_url=cfg["endpoint"],
            region_name=cfg["region"],
            aws_access_key_id=cfg["access"],
            aws_secret_access_key=cfg["secret"],
            config=Config(connect_timeout=5, read_timeout=25, retries={"max_attempts": 2},
                          s3={"addressing_style": "path"}),
        )

    @staticmethod
    def _hash(b):
        return hashlib.sha256(b).hexdigest()

    @staticmethod
    def _now(agora=None):
        dt = agora or datetime.now(TZ)
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("Hora sem fuso horario")
        return dt.astimezone(TZ)

    def _estado(self):
        if self.state is None or not self.state.exists():
            return {}
        if self.state.is_symlink():
            raise RuntimeError("Estado externo inseguro")
        try:
            d = json.loads(self.state.read_text(encoding="utf-8"))
            if not isinstance(d, dict) or not isinstance(d.get("data"), str):
                raise ValueError("Estado invalido")
            return d
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError("Estado externo corrompido; falha fechada") from exc

    def _guardar(self, d):
        if self.state is None:
            raise RuntimeError("Sem volume de dados")
        self.state.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.state.parent, prefix=".backup_offsite_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.state)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def _zip_local(self, pasta):
        if not self.backups.validar(pasta):
            raise RuntimeError("Copia local sem integridade")
        manifest = json.loads((pasta / "manifest.json").read_text(encoding="utf-8"))
        nomes = sorted(manifest["ficheiros"])
        with BytesIO() as saida:
            with zipfile.ZipFile(saida, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
                z.writestr("manifest.json", (pasta / "manifest.json").read_bytes())
                for nome in nomes:
                    if nome not in CopiasSeguranca.FICHEIROS:
                        raise RuntimeError("Ficheiro fora da allowlist")
                    z.writestr(nome, (pasta / nome).read_bytes())
            resultado = saida.getvalue()
        if len(resultado) > self.MAX_ZIP_BYTES:
            raise RuntimeError("Arquivo demasiado grande")
        return resultado, manifest

    @staticmethod
    def _cifrar(blob, key, data):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = secrets.token_bytes(12)
        return MAGIC + nonce + AESGCM(key).encrypt(
            nonce, blob, MAGIC + data.encode("ascii")
        )

    @classmethod
    def validar_cifrado(cls, cifrado, chave, data, manifest_esperado=None):
        """Valida recuperacao real em memoria; nao escreve/restaura ficheiros."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        if not CHAVE_DIA.fullmatch(data) or not cifrado.startswith(MAGIC) or len(cifrado) < len(MAGIC) + 12 + 16:
            raise ValueError("Arquivo externo invalido")
        pos = len(MAGIC)
        blob = AESGCM(chave).decrypt(cifrado[pos:pos+12], cifrado[pos+12:], MAGIC + data.encode("ascii"))
        if len(blob) > cls.MAX_ZIP_BYTES:
            raise ValueError("Arquivo externo excessivo")
        with zipfile.ZipFile(BytesIO(blob), "r") as z:
            nomes = z.namelist()
            if len(nomes) != len(set(nomes)) or "manifest.json" not in nomes:
                raise ValueError("Arquivo com entradas inesperadas")
            manifest = json.loads(z.read("manifest.json"))
            if not isinstance(manifest, dict) or manifest.get("data") != data:
                raise ValueError("Data ou manifesto invalido")
            ficheiros = manifest.get("ficheiros")
            if not isinstance(ficheiros, dict) or "previsoes_premium.json" not in ficheiros:
                raise ValueError("Ficheiros essenciais em falta")
            if set(nomes) != {"manifest.json", *ficheiros} or not set(ficheiros).issubset(CopiasSeguranca.FICHEIROS):
                raise ValueError("Lista de ficheiros invalida")
            total = 0
            for nome, metadados in ficheiros.items():
                inf = z.getinfo(nome)
                if inf.file_size > CopiasSeguranca.LIMITE_FICHEIRO:
                    raise ValueError("Ficheiro excessivo")
                total += inf.file_size
                if total > CopiasSeguranca.LIMITE_TOTAL:
                    raise ValueError("Arquivo excede o limite local")
                dados = z.read(nome)
                if cls._hash(dados) != metadados["sha256"] or len(dados) != metadados["bytes"]:
                    raise ValueError("SHA-256 invalido")
                if nome.endswith(".json"):
                    json.loads(dados)
        if manifest_esperado is not None and manifest != manifest_esperado:
            raise ValueError("Backup remoto de origem diferente")
        return manifest

    @staticmethod
    def _head_opcional(client, bucket, objeto):
        from botocore.exceptions import ClientError
        try:
            return client.head_object(Bucket=bucket, Key=objeto)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise

    def executar_se_devido(self, agora=None):
        if self.estado_config() != "configurado" or self.backups.pasta is None:
            return False
        dt = self._now(agora)
        if (dt.hour, dt.minute) < self.MIN_HORA or dt.hour >= self.HORA_LIMITE:
            return False
        data = dt.date().isoformat()
        local = self.backups.destino / data
        if not local.is_dir() or not self.backups.validar(local):
            return False
        if self._estado().get("data") == data:
            return False
        cfg = self._config()
        blob, manifest = self._zip_local(local)
        destino = cfg["prefix"] + "/" + data + "/estado.abk"
        s3 = self._s3(cfg)
        antigo = self._head_opcional(s3, cfg["bucket"], destino)
        if antigo is None:
            cifrado = self._cifrar(blob, cfg["key"], data)
            s3.put_object(Bucket=cfg["bucket"], Key=destino, Body=cifrado,
                          ContentType="application/octet-stream",
                          Metadata={"sha256": self._hash(cifrado), "data": data})
        # Confirmacao end-to-end via GET, AES-GCM, hashes e manifesto.
        resposta = s3.get_object(Bucket=cfg["bucket"], Key=destino)
        remoto = resposta["Body"].read(self.MAX_ZIP_BYTES + 1024)
        if len(remoto) > self.MAX_ZIP_BYTES + 512:
            raise RuntimeError("Objeto remoto demasiado grande")
        if resposta.get("Metadata", {}).get("sha256") != self._hash(remoto):
            raise RuntimeError("Hash remoto nao corresponde ao objeto")
        self.validar_cifrado(remoto, cfg["key"], data, manifest_esperado=manifest)
        self._guardar({
            "data": data, "confirmado_em": dt.isoformat(),
            "arquivo_sha256": self._hash(remoto), "ficheiros": len(manifest["ficheiros"]),
            "verificacao": "GET + AES-256-GCM + SHA-256 + manifesto",
        })
        return True

    def relatorio(self, agora=None):
        config = self.estado_config()
        try:
            d = self._estado()
        except RuntimeError:
            return "🔴 BACKUP EXTERNO — estado corrompido; verificar antes de qualquer envio."
        ultimo = d.get("data") or "ainda sem upload"
        hoje = self._now(agora).date().isoformat()
        atual = d.get("data") == hoje
        return "\n".join([
            "🌐 BACKUP EXTERNO — AUDITORIA LOCAL",
            f"Configuracao: {config}",
            f"Ultima copia confirmada: {ultimo}",
            f"Hoje: {'✅ Upload e recuperacao testados' if atual else '⚪ Sem verificacao offsite hoje'}",
            f"Verificacao: {d.get('verificacao') or 'ainda nenhuma'}",
            f"Ficheiros da ultima copia: {d.get('ficheiros', 0)}",
            "Horario: apos 09:30 ate antes das 18:00 (Portugal); sem interferir com CLV.",
            "🔒 AES-256-GCM antes do envio. A chave nunca e guardada no bucket.",
            "🔒 Restauro apenas manual e testado em memoria; nunca reescreve o modelo.",
            "⚠️ A perda da chave de encriptacao impede recuperar os backups.",
            "ℹ️ Este comando nao consulta rede, S3 nem OddsPapi.",
        ])
