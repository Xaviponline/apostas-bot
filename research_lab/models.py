from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import optuna
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .dataset import META_CATEGORICAL_FEATURES, META_NUMERIC_FEATURES


optuna.logging.set_verbosity(optuna.logging.WARNING)


@dataclass
class WalkForwardConfig:
    min_train: int
    test_block: int
    trials: int
    seed: int = 20261009


def _splits_temporais(n: int, min_train: int, test_block: int):
    inicio = max(int(min_train), 20)
    bloco = max(int(test_block), 1)
    for start in range(inicio, n, bloco):
        stop = min(start + bloco, n)
        if stop > start:
            yield np.arange(0, start), np.arange(start, stop)


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-5, 1 - 1e-5)
    return np.log(p / (1.0 - p)).reshape(-1, 1)


def _inner_split(n: int):
    valid = max(8, int(round(n * 0.20)))
    if n - valid < 20:
        valid = max(5, n // 4)
    return np.arange(0, n - valid), np.arange(n - valid, n)


def _tune_c_platt(p, y, trials: int, seed: int) -> float:
    if len(y) < 30 or len(np.unique(y)) < 2:
        return 1.0
    tr, va = _inner_split(len(y))
    if len(np.unique(y[tr])) < 2:
        return 1.0

    x = _logit(p)

    def objective(trial):
        c = trial.suggest_float("C", 1e-3, 100.0, log=True)
        model = LogisticRegression(C=c, solver="lbfgs", max_iter=2000, random_state=seed)
        model.fit(x[tr], y[tr])
        pred = model.predict_proba(x[va])[:, 1]
        return float(np.mean((pred - y[va]) ** 2))

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    study.optimize(objective, n_trials=max(int(trials), 4), show_progress_bar=False)
    return float(study.best_params["C"])


def walk_forward_platt(df: pd.DataFrame, config: WalkForwardConfig) -> pd.DataFrame:
    dados = df.sort_values("snapshot_index", kind="stable").reset_index(drop=True)
    linhas = []
    for fold, (tr, te) in enumerate(
        _splits_temporais(len(dados), config.min_train, config.test_block), 1
    ):
        y_train = dados.loc[tr, "resultado"].to_numpy(dtype=int)
        if len(np.unique(y_train)) < 2:
            continue
        p_train = dados.loc[tr, "probabilidade"].to_numpy(dtype=float)
        c = _tune_c_platt(p_train, y_train, config.trials, config.seed + fold)
        model = LogisticRegression(
            C=c,
            solver="lbfgs",
            max_iter=2000,
            random_state=config.seed + fold,
        )
        model.fit(_logit(p_train), y_train)
        p_test = dados.loc[te, "probabilidade"].to_numpy(dtype=float)
        pred = model.predict_proba(_logit(p_test))[:, 1]

        for indice, prob_nova in zip(te, pred):
            row = dados.loc[indice]
            linhas.append(
                {
                    "snapshot_index": int(row["snapshot_index"]),
                    "data_jogo": str(row["data_jogo"]),
                    "resultado": int(row["resultado"]),
                    "top5": bool(row["top5"]),
                    "p_champion": float(row["probabilidade"]),
                    "p_challenger": float(prob_nova),
                    "fold": fold,
                    "C": c,
                }
            )
    return pd.DataFrame(linhas)


def _pipeline_meta(c: float, seed: int) -> Pipeline:
    numerico = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
        ]
    )
    categorico = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    pre = ColumnTransformer(
        [
            ("num", numerico, META_NUMERIC_FEATURES),
            ("cat", categorico, META_CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )
    return Pipeline(
        [
            ("features", pre),
            (
                "model",
                LogisticRegression(
                    C=float(c),
                    solver="lbfgs",
                    max_iter=3000,
                    random_state=seed,
                ),
            ),
        ]
    )


def _tune_c_meta(frame: pd.DataFrame, y: np.ndarray, trials: int, seed: int) -> float:
    if len(y) < 35 or len(np.unique(y)) < 2:
        return 1.0
    tr, va = _inner_split(len(y))
    if len(np.unique(y[tr])) < 2:
        return 1.0
    x = frame[META_NUMERIC_FEATURES + META_CATEGORICAL_FEATURES]

    def objective(trial):
        c = trial.suggest_float("C", 1e-3, 30.0, log=True)
        pipe = _pipeline_meta(c, seed)
        pipe.fit(x.iloc[tr], y[tr])
        pred = pipe.predict_proba(x.iloc[va])[:, 1]
        return float(np.mean((pred - y[va]) ** 2))

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    study.optimize(objective, n_trials=max(int(trials), 4), show_progress_bar=False)
    return float(study.best_params["C"])


def walk_forward_meta_logit(df: pd.DataFrame, config: WalkForwardConfig) -> pd.DataFrame:
    dados = df.sort_values("snapshot_index", kind="stable").reset_index(drop=True)
    linhas = []
    features = META_NUMERIC_FEATURES + META_CATEGORICAL_FEATURES
    for fold, (tr, te) in enumerate(
        _splits_temporais(len(dados), config.min_train, config.test_block), 1
    ):
        y_train = dados.loc[tr, "resultado"].to_numpy(dtype=int)
        if len(np.unique(y_train)) < 2:
            continue
        train_frame = dados.loc[tr].reset_index(drop=True)
        c = _tune_c_meta(train_frame, y_train, config.trials, config.seed + 1000 + fold)
        pipe = _pipeline_meta(c, config.seed + 1000 + fold)
        pipe.fit(train_frame[features], y_train)
        test_frame = dados.loc[te]
        pred = pipe.predict_proba(test_frame[features])[:, 1]

        for (_, row), prob_nova in zip(test_frame.iterrows(), pred):
            linhas.append(
                {
                    "snapshot_index": int(row["snapshot_index"]),
                    "data_jogo": str(row["data_jogo"]),
                    "resultado": int(row["resultado"]),
                    "top5": bool(row["top5"]),
                    "p_champion": float(row["probabilidade"]),
                    "p_challenger": float(prob_nova),
                    "fold": fold,
                    "C": c,
                }
            )
    return pd.DataFrame(linhas)
