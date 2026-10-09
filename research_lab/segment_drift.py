"""Diagnóstico descritivo de drift segmentado, sem decisões de produção.

Avaliação temporal 60/40 congelada (a mesma do relatório geral); não seleciona
features, mercados, limiares ou modelos com base nos resultados observados.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .evaluation import metricas_probabilidade


FEATURES = ("media_liga_total", "lambda_total", "probabilidade", "margem_limite")
MIN_GRUPO = 8


def _categoria(valor) -> str:
    if pd.isna(valor):
        return "(sem indicação)"
    rotulo = str(valor).strip().replace("\n", " ").replace("\r", " ")
    return rotulo[:90] if rotulo else "(sem indicação)"


def _metricas(frame: pd.DataFrame) -> dict:
    return metricas_probabilidade(frame["resultado"], frame["probabilidade"])


def _serie(frame: pd.DataFrame, coluna: str) -> pd.Series:
    if coluna not in frame:
        return pd.Series(dtype=float)
    serie = pd.to_numeric(frame[coluna], errors="coerce")
    return serie.replace([np.inf, -np.inf], np.nan).dropna()


def _movimento(base: pd.DataFrame, recente: pd.DataFrame, coluna: str, minimo: int) -> dict | None:
    b, r = _serie(base, coluna), _serie(recente, coluna)
    if len(b) < minimo or len(r) < minimo:
        return None
    media_b, media_r = float(b.mean()), float(r.mean())
    std = float(np.sqrt((float(b.var(ddof=0)) + float(r.var(ddof=0))) / 2))
    smd = (media_r - media_b) / std if std > 1e-12 else None
    return {
        "base_media": media_b,
        "recente_media": media_r,
        "delta_media": media_r - media_b,
        "smd": float(smd) if smd is not None else None,
        "base_n": int(len(b)),
        "recente_n": int(len(r)),
    }


def _bootstrap_brier_periodos(base: pd.DataFrame, recente: pd.DataFrame, seed=20261009, iteracoes=600) -> dict:
    """Reamostragem por dia *dentro* de cada período, sem misturar as coortes."""
    datas_b = base["data_jogo"].fillna("").astype(str)
    datas_r = recente["data_jogo"].fillna("").astype(str)
    dias_b = sorted({d for d in datas_b if d.strip()})
    dias_r = sorted({d for d in datas_r if d.strip()})
    delta = float(_metricas(recente)["brier"] - _metricas(base)["brier"])
    resposta = {
        "delta_brier": delta,
        "ci95_low": None,
        "ci95_high": None,
        "dias_base": len(dias_b),
        "dias_recente": len(dias_r),
        "estado": "INCONCLUSIVO",
    }
    if min(len(base), len(recente)) < 15 or min(len(dias_b), len(dias_r)) < 3:
        resposta["estado"] = "DIAS_OU_AMOSTRA_INSUFICIENTES"
        return resposta
    grupos_b = {d: base.loc[datas_b == d] for d in dias_b}
    grupos_r = {d: recente.loc[datas_r == d] for d in dias_r}
    rng = np.random.default_rng(seed)
    difs = []
    for _ in range(iteracoes):
        xb = pd.concat([grupos_b[d] for d in rng.choice(dias_b, size=len(dias_b), replace=True)])
        xr = pd.concat([grupos_r[d] for d in rng.choice(dias_r, size=len(dias_r), replace=True)])
        difs.append(float(_metricas(xr)["brier"] - _metricas(xb)["brier"]))
    resposta["ci95_low"] = float(np.quantile(difs, 0.025))
    resposta["ci95_high"] = float(np.quantile(difs, 0.975))
    # Mesmo com IC sem zero: sinal exploratório, nunca uma regra de promoção.
    resposta["estado"] = "SINAL_EXPLORATORIO" if resposta["ci95_low"] > 0 or resposta["ci95_high"] < 0 else "INCONCLUSIVO"
    return resposta


def _segmentar(base: pd.DataFrame, recente: pd.DataFrame, colunas: tuple[str, ...], minimo: int) -> dict:
    def grupos(frame: pd.DataFrame) -> dict:
        f = frame.copy()
        f["_segmento"] = f[list(colunas)].apply(lambda linha: " / ".join(_categoria(v) for v in linha), axis=1)
        return {k: g for k, g in f.groupby("_segmento", sort=True)}

    gb, gr = grupos(base), grupos(recente)
    comuns = set(gb) & set(gr)
    elegiveis = {k for k in comuns if len(gb[k]) >= minimo and len(gr[k]) >= minimo}
    linhas = []
    for nome in elegiveis:
        b, r = gb[nome], gr[nome]
        metricas_b, metricas_r = _metricas(b), _metricas(r)
        linhas.append({
            "segmento": nome,
            "base_n": int(len(b)),
            "recente_n": int(len(r)),
            "brier_base": metricas_b["brier"],
            "brier_recente": metricas_r["brier"],
            "gap_base_pp": metricas_b["gap_pp"],
            "gap_recente_pp": metricas_r["gap_pp"],
            "features": {c: v for c in FEATURES if (v := _movimento(b, r, c, minimo)) is not None},
        })
    linhas.sort(key=lambda x: (-min(x["base_n"], x["recente_n"]), x["segmento"]))
    base_coberta = sum(len(gb[k]) for k in elegiveis)
    recente_coberta = sum(len(gr[k]) for k in elegiveis)
    # Estandardização para o mix de referência, APENAS em grupos comuns e elegíveis.
    # Não identifica causalidade nem mede retorno económico.
    brier_padronizado = None
    if base_coberta and recente_coberta:
        pesos = {k: len(gb[k]) / base_coberta for k in elegiveis}
        brier_padronizado = {
            "base": float(sum(pesos[x["segmento"]] * x["brier_base"] for x in linhas)),
            "recente": float(sum(pesos[x["segmento"]] * x["brier_recente"] for x in linhas)),
        }
        brier_padronizado["delta"] = brier_padronizado["recente"] - brier_padronizado["base"]
    return {
        "colunas": list(colunas),
        "min_n_por_periodo": minimo,
        "n_segmentos_base": len(gb),
        "n_segmentos_recente": len(gr),
        "n_segmentos_comuns": len(comuns),
        "n_segmentos_elegiveis": len(elegiveis),
        "base_coberta_n": base_coberta,
        "recente_coberta_n": recente_coberta,
        "base_coberta_pct": 100 * base_coberta / len(base),
        "recente_coberta_pct": 100 * recente_coberta / len(recente),
        "excluidos_amostra_n": len(comuns - elegiveis),
        "brier_mix_base": brier_padronizado,
        "segmentos": linhas,
    }


def relatorio_drift_segmentado(df: pd.DataFrame, minimo: int = MIN_GRUPO) -> dict:
    """Só lê snapshots liquidados com telemetria; devolve observações, nunca picks."""
    if df is None or df.empty or len(df) < 30:
        return {"estado": "AMOSTRA_INSUFICIENTE", "n": 0 if df is None else len(df)}
    campos = {"snapshot_index", "resultado", "probabilidade", "data_jogo", "liga", "mercado"}
    if not campos.issubset(df.columns):
        return {"estado": "CAMPOS_EM_FALTA", "n": len(df), "campos": sorted(campos - set(df.columns))}
    dados = df.sort_values("snapshot_index", kind="stable").reset_index(drop=True)
    corte = max(int(len(dados) * 0.60), 1)
    b, r = dados.iloc[:corte], dados.iloc[corte:]
    if len(b) < 15 or len(r) < 15:
        return {"estado": "AMOSTRA_INSUFICIENTE", "n": len(dados)}
    comparacao = _bootstrap_brier_periodos(b, r)
    resumo = {
        "base": {"n": len(b), "snapshot_min": int(b["snapshot_index"].min()), "snapshot_max": int(b["snapshot_index"].max()), "metricas": _metricas(b)},
        "recente": {"n": len(r), "snapshot_min": int(r["snapshot_index"].min()), "snapshot_max": int(r["snapshot_index"].max()), "metricas": _metricas(r)},
        "bootstrap_brier": comparacao,
    }
    return {
        "estado": "DESCRITIVO",
        "n": len(dados),
        "resumo": resumo,
        "por_mercado": _segmentar(b, r, ("mercado",), minimo),
        "por_liga": _segmentar(b, r, ("liga",), minimo),
        "por_liga_mercado": _segmentar(b, r, ("liga", "mercado"), minimo),
        "metodologia": "Split fixo 60/40 por snapshot, grupos n>=8 em cada período; Brier com mix-base só no suporte comum; IC95 reamostrado por dia, exploratório; sem causalidade ou promoção.",
    }
