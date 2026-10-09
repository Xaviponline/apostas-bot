from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def metricas_probabilidade(y, p) -> dict:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    mask = np.isfinite(y) & np.isfinite(p)
    y, p = y[mask], p[mask]
    if not len(y):
        return {
            "n": 0,
            "brier": None,
            "log_loss": None,
            "prev_media": None,
            "real": None,
            "gap_pp": None,
            "ece": None,
        }

    p = np.clip(p, 1e-6, 1 - 1e-6)
    brier = float(np.mean((p - y) ** 2))
    log_loss = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    prev = float(np.mean(p))
    real = float(np.mean(y))

    # ECE simples e estável para amostras pequenas: 5 bins fixos.
    bins = np.linspace(0.0, 1.0, 6)
    ece = 0.0
    for esquerda, direita in zip(bins[:-1], bins[1:]):
        if direita == 1.0:
            idx = (p >= esquerda) & (p <= direita)
        else:
            idx = (p >= esquerda) & (p < direita)
        if not np.any(idx):
            continue
        ece += (np.sum(idx) / len(p)) * abs(float(np.mean(p[idx]) - np.mean(y[idx])))

    return {
        "n": int(len(y)),
        "brier": brier,
        "log_loss": log_loss,
        "prev_media": prev,
        "real": real,
        "gap_pp": (real - prev) * 100.0,
        "ece": float(ece),
    }


def bootstrap_delta_brier_por_dia(
    frame: pd.DataFrame,
    p_champion_col: str,
    p_challenger_col: str,
    y_col: str = "resultado",
    date_col: str = "data_jogo",
    iteracoes: int = 1000,
    seed: int = 20261009,
) -> dict:
    dados = frame[
        [date_col, y_col, p_champion_col, p_challenger_col]
    ].dropna()
    if dados.empty:
        return {"n": 0, "delta": None, "ci95_low": None, "ci95_high": None}

    datas = [d for d in dados[date_col].astype(str).unique().tolist() if d]
    if len(datas) < 2:
        return {"n": int(len(dados)), "delta": None, "ci95_low": None, "ci95_high": None}

    y = dados[y_col].to_numpy(dtype=float)
    pc = dados[p_champion_col].to_numpy(dtype=float)
    pn = dados[p_challenger_col].to_numpy(dtype=float)
    delta_real = float(np.mean((pn - y) ** 2) - np.mean((pc - y) ** 2))

    rng = np.random.default_rng(seed)
    deltas = []
    grupos = {d: dados[dados[date_col].astype(str) == d] for d in datas}
    for _ in range(max(int(iteracoes), 100)):
        amostradas = rng.choice(datas, size=len(datas), replace=True)
        partes = [grupos[d] for d in amostradas]
        amostra = pd.concat(partes, ignore_index=True)
        yy = amostra[y_col].to_numpy(dtype=float)
        pcc = amostra[p_champion_col].to_numpy(dtype=float)
        pnn = amostra[p_challenger_col].to_numpy(dtype=float)
        deltas.append(float(np.mean((pnn - yy) ** 2) - np.mean((pcc - yy) ** 2)))

    return {
        "n": int(len(dados)),
        "delta": delta_real,
        "ci95_low": float(np.quantile(deltas, 0.025)),
        "ci95_high": float(np.quantile(deltas, 0.975)),
    }


def psi(referencia: Iterable[float], recente: Iterable[float], bins: int = 6) -> float | None:
    ref = np.asarray(list(referencia), dtype=float)
    cur = np.asarray(list(recente), dtype=float)
    ref = ref[np.isfinite(ref)]
    cur = cur[np.isfinite(cur)]
    if len(ref) < 10 or len(cur) < 10:
        return None

    quantis = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(quantis) < 3:
        return 0.0
    quantis[0] = -np.inf
    quantis[-1] = np.inf
    ref_h, _ = np.histogram(ref, bins=quantis)
    cur_h, _ = np.histogram(cur, bins=quantis)
    ref_p = np.clip(ref_h / max(ref_h.sum(), 1), 1e-6, None)
    cur_p = np.clip(cur_h / max(cur_h.sum(), 1), 1e-6, None)
    return float(np.sum((cur_p - ref_p) * np.log(cur_p / ref_p)))


def relatorio_drift(df: pd.DataFrame, colunas=None) -> dict:
    if df.empty or len(df) < 30:
        return {"n": int(len(df)), "estado": "AMOSTRA_INSUFICIENTE", "features": {}}

    colunas = colunas or [
        "probabilidade",
        "probabilidade_bruta",
        "lambda_total",
        "ppg_diff",
        "margem_limite",
    ]
    corte = max(int(len(df) * 0.60), 1)
    base, recente = df.iloc[:corte], df.iloc[corte:]
    detalhes = {}
    maior = 0.0
    for coluna in colunas:
        if coluna not in df:
            continue
        valor = psi(base[coluna], recente[coluna])
        if valor is None:
            continue
        maior = max(maior, valor)
        detalhes[coluna] = round(valor, 6)

    if not detalhes:
        estado = "AMOSTRA_INSUFICIENTE"
    elif maior >= 0.25:
        estado = "ALTO"
    elif maior >= 0.10:
        estado = "MODERADO"
    else:
        estado = "ESTAVEL"
    return {
        "n": int(len(df)),
        "estado": estado,
        "psi_max": maior if detalhes else None,
        "features": detalhes,
    }


def decisao_research_candidate(champion: dict, challenger: dict, bootstrap: dict) -> dict:
    """Gate de investigação apenas; nunca equivale a promoção para produção."""
    if not champion or not challenger:
        return {"candidate": False, "motivos": ["metricas_em_falta"]}
    n = int(challenger.get("n") or 0)
    cb = challenger.get("brier")
    pb = champion.get("brier")
    gap = challenger.get("gap_pp")
    ci_high = bootstrap.get("ci95_high")

    regras = {
        "n_oos_30": n >= 30,
        "brier_melhora_0_005": bool(cb is not None and pb is not None and cb <= pb - 0.005),
        "calibracao_8pp": bool(gap is not None and abs(gap) <= 8.0),
        "bootstrap_ci_favoravel": bool(ci_high is not None and ci_high < 0.0),
    }
    return {
        "candidate": all(regras.values()),
        "regras": regras,
        "nota": "Gate de investigação; qualquer promoção exige teste prospetivo pré-registado.",
    }
