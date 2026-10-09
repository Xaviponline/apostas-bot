from __future__ import annotations

import hmac
import os
import threading
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
import uvicorn

from . import LAB_VERSION
from .config import LabConfig
from .dataset import validar_payload
from .runner import executar_experimento
from .storage import LabStorage


config = LabConfig.from_env()
storage = LabStorage(config)
app = FastAPI(title="Apostas Research Lab", version=LAB_VERSION)
_run_lock = threading.Lock()


def _auth(authorization: str | None) -> None:
    if not config.ingest_token:
        raise HTTPException(status_code=503, detail="LAB_INGEST_TOKEN não configurado")
    recebido = str(authorization or "")
    esperado = f"Bearer {config.ingest_token}"
    if not hmac.compare_digest(recebido, esperado):
        raise HTTPException(status_code=401, detail="Não autorizado")


def _executar_e_guardar(payload: dict[str, Any]) -> None:
    # Um único treino de cada vez. Um export posterior continuará guardado e
    # pode ser analisado pelo /run se chegar durante uma execução.
    if not _run_lock.acquire(blocking=False):
        return
    try:
        report = executar_experimento(payload, config)
        storage.guardar_relatorio(report)
    finally:
        _run_lock.release()


@app.get("/health")
def health():
    return {
        "ok": True,
        "lab_version": LAB_VERSION,
        "storage": "s3" if config.s3_configurado else "local",
        "mlflow": bool(config.mlflow_tracking_uri),
    }


@app.post("/ingest")
def ingest(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
):
    _auth(authorization)
    try:
        validar_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    caminho = storage.guardar_dataset(payload)
    background_tasks.add_task(_executar_e_guardar, payload)
    return {
        "accepted": True,
        "records": int(payload.get("records_count") or 0),
        "sha256": str(payload.get("records_sha256") or ""),
        "dataset_object": caminho,
        "analysis": "scheduled",
        "production_unchanged": True,
    }


@app.post("/run")
def run_latest(
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
):
    _auth(authorization)
    payload = storage.get_json("datasets/latest.json")
    if not payload:
        raise HTTPException(status_code=404, detail="Ainda não existe dataset.")
    background_tasks.add_task(_executar_e_guardar, payload)
    return {"accepted": True, "analysis": "scheduled"}


@app.get("/status")
def status(authorization: str | None = Header(default=None)):
    _auth(authorization)
    payload = storage.get_json("datasets/latest.json", default={}) or {}
    report = storage.get_json("reports/latest.json", default=None)
    return {
        "lab_version": LAB_VERSION,
        "dataset": {
            "records": int(payload.get("records_count") or 0),
            "sha256": str(payload.get("records_sha256") or ""),
            "generated_at": payload.get("generated_at"),
        },
        "report": report,
        "analysis_running": _run_lock.locked(),
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT") or "8000")
    uvicorn.run(app, host="0.0.0.0", port=port)
