"""Protocolo de validação Platt verdadeiramente prospetivo e 100% shadow.

Regras PRÉ-REGISTADAS (versão 1, antes da primeira previsão):
- Calibrador Platt treinado UMA VEZ usando apenas V1.2 já liquidadas há >=6h,
  no mínimo 80 resultados e 10 dias. Hiperparâmetro C=1, sem otimização OOS.
- Guardar coeficiente e intercepto num estado persistente; nunca refazer o fit.
- Inscrever APENAS snapshots novos ou conhecidos com evento FUTURO no instante
  da inscrição, criados antes do jogo; V1.2 ranking 1..5.
- Congelar ANTES do jogo ambas as probabilidades e o fingerprint original.
- Resultados entram posteriormente por export; nunca recalcular prognósticos.
- Checkpoint fixo: PRIMEIROS 100 jogos inscritos, >=20 dias distintos, todos
  liquidados. Bootstrap por dia (1000, seed fixa) e redução Brier >=0.005 com
  limite superior do IC95 <0; gap absoluto inferior ao champion.
- Estatísticas preliminares são descritivas; SEM promoção automática.
A coorte V1.3 Top5+VALUE é INDEPENDENTE e nunca é tocada aqui.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from .evaluation import bootstrap_delta_brier_por_dia, metricas_probabilidade

SCHEMA = 1
MIN_TREINO = 80
MIN_DIAS_TREINO = 10
MARGEM_RESULTADO_SEG = 6 * 3600
MARGEM_LIQUIDACAO_SEG = 3 * 3600
ALVO = 100
DIAS_MIN = 20
BRIER_MIN = 0.005
SEED = 20261017


def _numero(valor):
    if isinstance(valor, bool):
        return None
    try:
        n = float(valor)
    except (ValueError, TypeError, OverflowError):
        return None
    return n if math.isfinite(n) else None


def _instante(valor):
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        dt = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc).timestamp()


def _indice(item):
    if isinstance(item.get("snapshot_index"), bool):
        return None
    try:
        i = int(item.get("snapshot_index"))
    except (ValueError, TypeError, OverflowError):
        return None
    return i if i > 0 else None


def _resultado(item):
    r = item.get("resultado_binario")
    return int(r) if r in (0, 1, "0", "1") and not isinstance(r, bool) else None


def _logit(prob):
    p = min(max(float(prob), 1e-5), 1 - 1e-5)
    return math.log(p / (1 - p))


def _assinar(item):
    """Fingerprint só de atributos imutáveis; resultados/odds são mutáveis."""
    campos = (
        "snapshot_index", "chave", "event_id", "data_jogo",
        "timestamp_jogo", "criada_em", "modelo_versao",
        "ranking_modelo", "mercado", "probabilidade",
    )
    base = {campo: item.get(campo) for campo in campos}
    blob = json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _base_treino(registos, agora_ts):
    filtrados = []
    for item in registos:
        if not isinstance(item, dict) or item.get("modelo_versao") != "V1.2":
            continue
        i = _indice(item)
        y = _resultado(item)
        p = _numero(item.get("probabilidade"))
        ts = _numero(item.get("timestamp_jogo"))
        criada = _instante(item.get("criada_em"))
        dia = str(item.get("data_jogo") or "")
        if (i is None or y is None or p is None or not 0 < p < 1
                or ts is None or ts > agora_ts - MARGEM_RESULTADO_SEG
                or criada is None or criada >= ts or not dia):
            continue
        filtrados.append((i, p, y, dia))
    filtrados.sort(key=lambda x: x[0])
    return filtrados


def _fit_modelo(treino):
    if len(treino) < MIN_TREINO or len({x[3] for x in treino}) < MIN_DIAS_TREINO:
        return None
    yy = np.asarray([x[2] for x in treino], dtype=int)
    if len(set(yy.tolist())) < 2:
        return None
    xx = np.asarray([[_logit(x[1])] for x in treino], dtype=float)
    modelo = LogisticRegression(
        C=1.0, solver="lbfgs", max_iter=2000, random_state=SEED,
    )
    modelo.fit(xx, yy)
    return float(modelo.coef_[0][0]), float(modelo.intercept_[0])


def _platt(p, coef, intercept):
    x = coef * _logit(p) + intercept
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1 + ex)


def atualizar_protocolo(estado: dict | None, payload: dict, agora=None) -> dict:
    """Atualização pura: cópias; o armazenamento faz o commit fora desta função.

    Os registos não são modificados. O modelo fica frozen depois do primeiro
    fit. Uma entrada inscrita não pode ser trocada ou recalculada posteriormente.
    """
    agora = agora or datetime.now(timezone.utc)
    if agora.tzinfo is None:
        raise ValueError("Instante UTC/aware obrigatório")
    ts = agora.timestamp()
    marca = agora.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    registos = payload.get("records")
    if not isinstance(registos, list):
        raise ValueError("Dataset sem records")
    if estado is None:
        treino = _base_treino(registos, ts)
        fit = _fit_modelo(treino)
        if fit is None:
            return {
                "schema": SCHEMA, "estado": "AGUARDA_TREINO",
                "treino_candidatos": len(treino),
                "treino_dias": len({x[3] for x in treino}),
                "previsoes": {}, "avisos": [],
            }
        coef, intercept = fit
        canonico = json.dumps(treino, separators=(",", ":")).encode("utf-8")
        estado = {
            "schema": SCHEMA, "estado": "CONGELADO",
            "congelado_em": marca,
            "treino_digest": hashlib.sha256(canonico).hexdigest(),
            "dataset_digest_inicial": payload.get("records_sha256"),
            "treino_n": len(treino),
            "treino_dias": len({x[3] for x in treino}),
            "coef": coef,
            "intercept": intercept,
            "hiperparametros": {"C": 1.0, "seed": SEED},
            "previsoes": {}, "avisos": [],
        }
    elif estado.get("estado") == "AGUARDA_TREINO":
        # Ainda não houve modelo nem previsão; usar a base atual até poder
        # realizar o primeiro fit. Não afeta histórico ou os gates V1.3.
        return atualizar_protocolo(None, payload, agora=agora)
    elif (estado.get("schema") != SCHEMA or estado.get("estado") != "CONGELADO"
          or not isinstance(estado.get("previsoes"), dict)
          or _numero(estado.get("coef")) is None
          or _numero(estado.get("intercept")) is None):
        raise ValueError("Estado prospetivo incompatível — não sobrescrever")

    # Copiar estado para impedir mutações do objeto anterior (e de snapshots).
    novo = json.loads(json.dumps(estado, ensure_ascii=False, allow_nan=False))
    congeladas = novo["previsoes"]
    por_indice = {}
    for item in registos:
        if isinstance(item, dict) and _indice(item) is not None:
            i = str(_indice(item))
            if i in por_indice:
                raise ValueError("Dataset com snapshot_index repetido; recusar atualização")
            por_indice[i] = item

    avisos = set(novo.get("avisos", []))
    # FIRST: atualizar somente resultados de previsões congeladas em exports
    # anteriores. Perdeu-se ou mudou a identidade => manter e avisar.
    for i, congelada in congeladas.items():
        item = por_indice.get(i)
        if item is None or _assinar(item) != congelada["fingerprint"]:
            avisos.add(f"snapshot_{i}_identidade_divergente")
            continue
        resultado = _resultado(item)
        kickoff = _numero(item.get("timestamp_jogo"))
        if resultado is None or kickoff is None or ts < kickoff + MARGEM_LIQUIDACAO_SEG:
            continue
        if congelada.get("resultado") is None:
            congelada["resultado"] = resultado
            congelada["liquidacao_observada_em"] = marca
        elif congelada["resultado"] != resultado:
            avisos.add(f"snapshot_{i}_resultado_divergente")

    # SECOND: congelar novas probabilidades, só com kickoff no futuro.
    # Não criar pseudo-previsões históricas ao importar a base antiga.
    for i, item in sorted(por_indice.items(), key=lambda x: int(x[0])):
        if i in congeladas or item.get("modelo_versao") != "V1.2":
            continue
        try:
            rank = int(item.get("ranking_modelo"))
        except (ValueError, TypeError, OverflowError):
            continue
        if rank not in range(1, 6):
            continue
        kickoff = _numero(item.get("timestamp_jogo"))
        criada = _instante(item.get("criada_em"))
        p = _numero(item.get("probabilidade"))
        if (kickoff is None or kickoff <= ts or criada is None
                or criada > ts or criada >= kickoff
                or p is None or not 0 < p < 1):
            continue
        pp = _platt(p, novo["coef"], novo["intercept"])
        congeladas[i] = {
            "snapshot_index": int(i),
            "data_jogo": str(item.get("data_jogo") or ""),
            "ranking_modelo": rank,
            "fingerprint": _assinar(item),
            "evento_em": kickoff,
            "congelada_em": marca,
            "p_champion": p,
            "p_platt": pp,
            "resultado": None,
        }

    novo["avisos"] = sorted(avisos)[:40]
    return novo


def resumo_protocolo(estado: dict | None) -> dict:
    if not estado:
        return {"estado": "NÃO_INICIADO", "previsoes": 0, "liquidadas": 0}
    if estado.get("estado") != "CONGELADO":
        return {"estado": estado.get("estado", "INVÁLIDO"),
                "treino_candidatos": estado.get("treino_candidatos", 0),
                "treino_dias": estado.get("treino_dias", 0),
                "previsoes": 0, "liquidadas": 0}
    previsoes = list((estado.get("previsoes") or {}).values())
    # Coorte FIXA: os primeiros 100 registados em ordem de inscrição.
    previsoes.sort(key=lambda p: (p["congelada_em"], p["snapshot_index"]))
    selecionadas = previsoes[:ALVO]
    liquidadas = [p for p in selecionadas if p.get("resultado") in (0, 1)]
    dias = len({p["data_jogo"] for p in selecionadas if p.get("data_jogo")})
    dias_liq = len({p["data_jogo"] for p in liquidadas if p.get("data_jogo")})
    conclusiva = len(selecionadas) == ALVO and len(liquidadas) == ALVO and dias >= DIAS_MIN
    saida = {
        "estado": "AVALIAÇÃO_DESCRITIVA" if not conclusiva else "CHECKPOINT_ATINGIDO",
        "congelado_em": estado["congelado_em"],
        "treino_n": estado["treino_n"],
        "treino_dias": estado["treino_dias"],
        "treino_digest": estado["treino_digest"][:16],
        "inscritas_total": len(previsoes),
        "previsoes": len(selecionadas),
        "alvo": ALVO,
        "liquidadas": len(liquidadas),
        "dias": dias,
        "dias_liquidados": dias_liq,
        "avisos": len(estado.get("avisos", [])),
        "promocao_automatica": False,
    }
    if not liquidadas:
        return saida
    ys = [p["resultado"] for p in liquidadas]
    pc = [p["p_champion"] for p in liquidadas]
    pp = [p["p_platt"] for p in liquidadas]
    mc = metricas_probabilidade(ys, pc)
    mp = metricas_probabilidade(ys, pp)
    saida.update({
        "brier_champion": mc["brier"],
        "brier_platt": mp["brier"],
        "delta_brier": mp["brier"] - mc["brier"],
        "gap_champion_pp": mc["gap_pp"],
        "gap_platt_pp": mp["gap_pp"],
    })
    if conclusiva:
        frame = pd.DataFrame([{
            "data_jogo": p["data_jogo"], "resultado": p["resultado"],
            "p_champion": p["p_champion"], "p_platt": p["p_platt"],
        } for p in liquidadas])
        bootstrap = bootstrap_delta_brier_por_dia(
            frame, "p_champion", "p_platt", seed=SEED, iteracoes=1000
        )
        saida["ic95_delta"] = [bootstrap["ci95_low"], bootstrap["ci95_high"]]
        passa = (saida["delta_brier"] <= -BRIER_MIN
                 and bootstrap["ci95_high"] is not None and bootstrap["ci95_high"] < 0
                 and abs(mp["gap_pp"]) < abs(mc["gap_pp"]))
        saida["conclusao_shadow"] = "MELHORIA_ESTÁVEL" if passa else "NÃO_COMPROVADA"
        saida["necessita_decisao_humana"] = True
    return saida
