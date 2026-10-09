from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import boto3

from .config import LabConfig


class LabStorage:
    """S3 Railway em produção; filesystem local como fallback de desenvolvimento."""

    def __init__(self, config: LabConfig):
        self.config = config
        self._s3 = None
        if config.s3_configurado:
            self._s3 = boto3.client(
                "s3",
                endpoint_url=config.s3_endpoint,
                region_name=config.s3_region or None,
                aws_access_key_id=config.s3_access_key_id,
                aws_secret_access_key=config.s3_secret_access_key,
            )
        else:
            Path(config.local_dir).mkdir(parents=True, exist_ok=True)

    def put_json(self, key: str, value: Any) -> None:
        corpo = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if self._s3 is not None:
            self._s3.put_object(
                Bucket=self.config.s3_bucket,
                Key=key,
                Body=corpo,
                ContentType="application/json",
            )
            return
        destino = Path(self.config.local_dir) / key
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(corpo)

    def get_json(self, key: str, default=None):
        if self._s3 is not None:
            try:
                resposta = self._s3.get_object(Bucket=self.config.s3_bucket, Key=key)
            except self._s3.exceptions.NoSuchKey:
                return default
            except Exception as exc:
                codigo = (
                    getattr(exc, "response", {})
                    .get("Error", {})
                    .get("Code")
                )
                if codigo in {"NoSuchKey", "404", "NotFound"}:
                    return default
                raise
            return json.loads(resposta["Body"].read().decode("utf-8"))

        destino = Path(self.config.local_dir) / key
        if not destino.exists():
            return default
        return json.loads(destino.read_text(encoding="utf-8"))

    def guardar_dataset(self, payload: dict[str, Any]) -> str:
        agora = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        digest = str(payload.get("records_sha256") or "")[:12] or "semhash"
        historico = f"datasets/{agora}-{digest}.json"
        self.put_json(historico, payload)
        self.put_json("datasets/latest.json", payload)
        return historico

    def guardar_relatorio(self, relatorio: dict[str, Any]) -> str:
        agora = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        historico = f"reports/{agora}.json"
        self.put_json(historico, relatorio)
        self.put_json("reports/latest.json", relatorio)
        return historico
