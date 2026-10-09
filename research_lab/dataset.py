from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd


SCHEMA_VERSION = 1

META_NUMERIC_FEATURES = [
    "probabilidade",
    "probabilidade_bruta",
    "qualidade",
    "ranking_modelo",
    "score_modelo",
    "odd_minima",
    "margem_limite",
    "lambda_total",
    "lambda_diff",
    "ppg_diff",
    "amostra_local_min",
    "media_liga_total",
]
META_CATEGORICAL_FEATURES = ["mercado"]


def _canonical_json(valor: Any) -> bytes:
    return json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def validar_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Payload Research Lab inválido.")
    if int(payload.get("schema_version") or 0) != SCHEMA_VERSION:
        raise ValueError("Versão do dataset não suportada.")
    registos = payload.get("records")
    if not isinstance(registos, list):
        raise ValueError("Dataset sem lista de records.")
    if int(payload.get("records_count") or -1) != len(registos):
        raise ValueError("Contagem do dataset divergente.")
    esperado = hashlib.sha256(_canonical_json(registos)).hexdigest()
    recebido = str(payload.get("records_sha256") or "")
    if recebido != esperado:
        raise ValueError("Hash do dataset divergente.")


def _numero(valor):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return np.nan
    return numero if np.isfinite(numero) else np.nan


def dataframe_from_payload(payload: dict[str, Any]) -> pd.DataFrame:
    validar_payload(payload)
    linhas = []
    for registo in payload["records"]:
        if not isinstance(registo, dict):
            continue
        diag = registo.get("diagnostico_modelo")
        diag = diag if isinstance(diag, dict) else {}

        lc = _numero(diag.get("lambda_casa"))
        lf = _numero(diag.get("lambda_fora"))
        pc = _numero(diag.get("ppg_casa"))
        pf = _numero(diag.get("ppg_fora"))
        ac = _numero(diag.get("amostra_casa_local"))
        af = _numero(diag.get("amostra_fora_local"))
        mlc = _numero(diag.get("media_liga_casa"))
        mlf = _numero(diag.get("media_liga_fora"))

        resultado = registo.get("resultado_binario")
        try:
            resultado = int(resultado) if resultado in (0, 1, "0", "1") else np.nan
        except (TypeError, ValueError):
            resultado = np.nan

        ranking = _numero(registo.get("ranking_modelo"))
        linha = {
            "snapshot_index": int(registo.get("snapshot_index") or 0),
            "data_jogo": str(registo.get("data_jogo") or ""),
            "timestamp_jogo": _numero(registo.get("timestamp_jogo")),
            "liga": str(registo.get("liga") or ""),
            "mercado": str(registo.get("mercado") or ""),
            "modelo_versao": str(registo.get("modelo_versao") or ""),
            "resultado": resultado,
            "probabilidade": _numero(registo.get("probabilidade")),
            "probabilidade_bruta": _numero(registo.get("probabilidade_bruta")),
            "qualidade": _numero(registo.get("qualidade")),
            "ranking_modelo": ranking,
            "score_modelo": _numero(registo.get("score_modelo")),
            "odd_minima": _numero(registo.get("odd_minima")),
            "odd_real": _numero(registo.get("odd_real")),
            "odd_fecho": _numero(registo.get("odd_fecho")),
            "margem_limite": _numero(diag.get("margem_limite")),
            "lambda_casa": lc,
            "lambda_fora": lf,
            "lambda_total": lc + lf if np.isfinite(lc) and np.isfinite(lf) else np.nan,
            "lambda_diff": abs(lc - lf) if np.isfinite(lc) and np.isfinite(lf) else np.nan,
            "ppg_casa": pc,
            "ppg_fora": pf,
            "ppg_diff": abs(pc - pf) if np.isfinite(pc) and np.isfinite(pf) else np.nan,
            "amostra_local_min": min(ac, af) if np.isfinite(ac) and np.isfinite(af) else np.nan,
            "media_liga_total": mlc + mlf if np.isfinite(mlc) and np.isfinite(mlf) else np.nan,
            "tem_telemetria": bool(len(diag) > 1),
            "top5": bool(np.isfinite(ranking) and 1 <= ranking <= 5),
        }
        linhas.append(linha)

    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    df = df.sort_values(["snapshot_index"], kind="stable").reset_index(drop=True)
    return df


def coorte_liquidada(df: pd.DataFrame, telemetria=False) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    mask = df["resultado"].isin([0, 1]) & df["probabilidade"].between(0.0001, 0.9999)
    if telemetria:
        mask &= df["tem_telemetria"].astype(bool)
    return df.loc[mask].copy().reset_index(drop=True)
