from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

import mlflow
from mlflow.tracking import MlflowClient
import numpy as np
import pandas as pd

from .config import LabConfig
from .dataset import coorte_liquidada, dataframe_from_payload
from .evaluation import (
    bootstrap_delta_brier_por_dia,
    decisao_research_candidate,
    metricas_probabilidade,
    relatorio_drift,
)
from .models import WalkForwardConfig, walk_forward_meta_logit, walk_forward_platt


def _metricas_frame(frame: pd.DataFrame, coluna: str) -> dict:
    if frame is None or frame.empty:
        return metricas_probabilidade([], [])
    return metricas_probabilidade(frame["resultado"], frame[coluna])


def _segmento_top5(frame: pd.DataFrame, coluna: str) -> dict:
    if frame is None or frame.empty or "top5" not in frame:
        return metricas_probabilidade([], [])
    return _metricas_frame(frame[frame["top5"].astype(bool)], coluna)


def _auditoria_mercado(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"elegiveis": 0, "liquidadas": 0, "roi": None, "clv_media": None, "clv_n": 0}
    dados = df.copy()
    odd = pd.to_numeric(dados["odd_real"], errors="coerce")
    minima = pd.to_numeric(dados["odd_minima"], errors="coerce")
    resultado = pd.to_numeric(dados["resultado"], errors="coerce")
    elegivel = odd.notna() & minima.notna() & (odd >= minima) & resultado.isin([0, 1])
    e = dados.loc[elegivel].copy()
    if e.empty:
        return {"elegiveis": 0, "liquidadas": 0, "roi": None, "clv_media": None, "clv_n": 0}

    odds = pd.to_numeric(e["odd_real"], errors="coerce").to_numpy(dtype=float)
    ys = pd.to_numeric(e["resultado"], errors="coerce").to_numpy(dtype=int)
    pnl = np.where(ys == 1, odds - 1.0, -1.0)
    fechos = pd.to_numeric(e["odd_fecho"], errors="coerce").to_numpy(dtype=float)
    mask_clv = np.isfinite(fechos) & (fechos > 1.0)
    clv = (odds[mask_clv] / fechos[mask_clv]) - 1.0 if np.any(mask_clv) else np.array([])
    return {
        "elegiveis": int(len(e)),
        "liquidadas": int(len(e)),
        "ganhos": int(np.sum(ys)),
        "perdas": int(len(ys) - np.sum(ys)),
        "pnl_unidades": float(np.sum(pnl)),
        "roi": float(np.mean(pnl)),
        "clv_media": float(np.mean(clv)) if len(clv) else None,
        "clv_n": int(len(clv)),
    }


def _avaliar_challenger(nome: str, frame: pd.DataFrame) -> dict:
    if frame is None or frame.empty:
        return {
            "nome": nome,
            "estado": "AMOSTRA_INSUFICIENTE",
            "oos_n": 0,
        }
    champion = _metricas_frame(frame, "p_champion")
    challenger = _metricas_frame(frame, "p_challenger")
    bootstrap = bootstrap_delta_brier_por_dia(
        frame,
        p_champion_col="p_champion",
        p_challenger_col="p_challenger",
    )
    decisao = decisao_research_candidate(champion, challenger, bootstrap)

    top5_frame = frame[frame["top5"].astype(bool)].copy() if "top5" in frame else frame.iloc[0:0].copy()
    top5_champion = _metricas_frame(top5_frame, "p_champion")
    top5_challenger = _metricas_frame(top5_frame, "p_challenger")
    top5_bootstrap = bootstrap_delta_brier_por_dia(
        top5_frame,
        p_champion_col="p_champion",
        p_challenger_col="p_challenger",
    ) if not top5_frame.empty else {
        "n": 0,
        "delta": None,
        "ci95_low": None,
        "ci95_high": None,
    }
    top5_delta = (
        top5_challenger["brier"] - top5_champion["brier"]
        if top5_challenger.get("brier") is not None
        and top5_champion.get("brier") is not None
        else None
    )

    return {
        "nome": nome,
        "estado": "CANDIDATO_RESEARCH" if decisao["candidate"] else "SHADOW",
        "oos_n": int(len(frame)),
        "champion_mesma_coorte": champion,
        "challenger": challenger,
        "delta_brier": (
            challenger["brier"] - champion["brier"]
            if challenger.get("brier") is not None and champion.get("brier") is not None
            else None
        ),
        "bootstrap_delta_brier": bootstrap,
        "top5_oos_n": int(len(top5_frame)),
        "top5_champion": top5_champion,
        "top5_challenger": top5_challenger,
        "top5_delta_brier": top5_delta,
        "top5_bootstrap_delta_brier": top5_bootstrap,
        "gate_research": decisao,
    }


def _preparar_experimento_mlflow(config: LabConfig) -> None:
    """Configura tracking persistente sem exigir um servidor MLflow separado."""
    mlflow.set_tracking_uri(config.mlflow_tracking_uri)
    client = MlflowClient()
    existente = client.get_experiment_by_name(config.experiment_name)
    if existente is None:
        kwargs = {}
        if config.mlflow_artifact_root:
            kwargs["artifact_location"] = config.mlflow_artifact_root
        try:
            client.create_experiment(config.experiment_name, **kwargs)
        except Exception:
            # Corrida rara de criação; set_experiment resolve se já existir.
            pass
    mlflow.set_experiment(config.experiment_name)


def executar_experimento(payload: dict[str, Any], config: LabConfig) -> dict[str, Any]:
    df = dataframe_from_payload(payload)
    liquidadas = coorte_liquidada(df, telemetria=False)
    telemetria = coorte_liquidada(df, telemetria=True)

    champion_total = metricas_probabilidade(
        liquidadas["resultado"] if not liquidadas.empty else [],
        liquidadas["probabilidade"] if not liquidadas.empty else [],
    )
    champion_top5 = metricas_probabilidade(
        liquidadas.loc[liquidadas["top5"], "resultado"] if not liquidadas.empty else [],
        liquidadas.loc[liquidadas["top5"], "probabilidade"] if not liquidadas.empty else [],
    )

    challengers = {}

    if len(liquidadas) >= 70:
        platt = walk_forward_platt(
            liquidadas,
            WalkForwardConfig(
                min_train=60,
                test_block=10,
                trials=config.optuna_trials,
            ),
        )
        challengers["platt_calibration_v1"] = _avaliar_challenger(
            "platt_calibration_v1", platt
        )
    else:
        challengers["platt_calibration_v1"] = {
            "nome": "platt_calibration_v1",
            "estado": "AMOSTRA_INSUFICIENTE",
            "oos_n": 0,
            "minimo_recomendado": 70,
        }

    if len(telemetria) >= 70:
        meta = walk_forward_meta_logit(
            telemetria,
            WalkForwardConfig(
                min_train=50,
                test_block=10,
                trials=config.optuna_trials,
            ),
        )
        challengers["meta_logit_v1"] = _avaliar_challenger("meta_logit_v1", meta)
    else:
        challengers["meta_logit_v1"] = {
            "nome": "meta_logit_v1",
            "estado": "AMOSTRA_INSUFICIENTE",
            "oos_n": 0,
            "minimo_recomendado": 70,
        }

    drift = relatorio_drift(telemetria)
    mercado = _auditoria_mercado(liquidadas)

    report = {
        "lab_version": "1.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset": {
            "records": int(len(df)),
            "liquidadas": int(len(liquidadas)),
            "telemetria_liquidada": int(len(telemetria)),
            "sha256": str(payload.get("records_sha256") or ""),
            "generated_at": payload.get("generated_at"),
        },
        "champion": {
            "nome": "V1.2",
            "total": champion_total,
            "top5": champion_top5,
        },
        "challengers": challengers,
        "drift": drift,
        "market_audit_descritivo": mercado,
        "governance": {
            "production_unchanged": True,
            "auto_promotion": False,
            "walk_forward_only": True,
            "optuna_nested_in_training": True,
            "note": (
                "Resultados do lab são exploratórios. Qualquer regra/modelo vencedor "
                "tem de ser congelado e testado prospectivamente antes de produção."
            ),
        },
        "mlflow": {"logged": False, "run_id": None, "error": None},
    }

    if config.mlflow_tracking_uri:
        try:
            _preparar_experimento_mlflow(config)
            with mlflow.start_run(run_name="research-lab-v1") as run:
                mlflow.set_tags(
                    {
                        "lab_version": "1.1.0",
                        "production_unchanged": "true",
                        "auto_promotion": "false",
                        "dataset_sha256": str(payload.get("records_sha256") or ""),
                    }
                )
                mlflow.log_params(
                    {
                        "optuna_trials": config.optuna_trials,
                        "platt_min_train": 60,
                        "meta_min_train": 50,
                        "walk_forward": True,
                    }
                )
                if champion_total.get("brier") is not None:
                    mlflow.log_metric("champion_brier", champion_total["brier"])
                    mlflow.log_metric("champion_gap_pp", champion_total["gap_pp"])
                for nome, dados in challengers.items():
                    ch = dados.get("challenger") if isinstance(dados, dict) else None
                    if isinstance(ch, dict) and ch.get("brier") is not None:
                        safe = nome.replace("-", "_")
                        mlflow.log_metric(f"{safe}_brier", ch["brier"])
                        mlflow.log_metric(f"{safe}_gap_pp", ch["gap_pp"])
                        delta = dados.get("delta_brier")
                        if delta is not None and math.isfinite(float(delta)):
                            mlflow.log_metric(f"{safe}_delta_brier", float(delta))
                mlflow.log_dict(report, "research_report.json")
                report["mlflow"] = {
                    "logged": True,
                    "run_id": run.info.run_id,
                    "error": None,
                }
        except Exception as exc:
            report["mlflow"] = {
                "logged": False,
                "run_id": None,
                "error": f"{type(exc).__name__}: {exc}"[:500],
            }

    return report
