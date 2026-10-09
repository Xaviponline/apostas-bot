from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class LabConfig:
    ingest_token: str
    s3_endpoint: str
    s3_bucket: str
    s3_region: str
    s3_access_key_id: str
    s3_secret_access_key: str
    mlflow_tracking_uri: str
    experiment_name: str
    local_dir: str
    optuna_trials: int

    @classmethod
    def from_env(cls) -> "LabConfig":
        return cls(
            ingest_token=str(os.getenv("LAB_INGEST_TOKEN") or ""),
            s3_endpoint=str(os.getenv("LAB_S3_ENDPOINT") or ""),
            s3_bucket=str(os.getenv("LAB_S3_BUCKET") or ""),
            s3_region=str(os.getenv("LAB_S3_REGION") or "auto"),
            s3_access_key_id=str(os.getenv("LAB_S3_ACCESS_KEY_ID") or ""),
            s3_secret_access_key=str(os.getenv("LAB_S3_SECRET_ACCESS_KEY") or ""),
            mlflow_tracking_uri=str(os.getenv("MLFLOW_TRACKING_URI") or ""),
            experiment_name=str(os.getenv("MLFLOW_EXPERIMENT_NAME") or "apostas-bot-research"),
            local_dir=str(os.getenv("LAB_LOCAL_DIR") or "/tmp/apostas-research-lab"),
            optuna_trials=max(int(os.getenv("LAB_OPTUNA_TRIALS") or 16), 4),
        )

    @property
    def s3_configurado(self) -> bool:
        return bool(
            self.s3_endpoint
            and self.s3_bucket
            and self.s3_access_key_id
            and self.s3_secret_access_key
        )
