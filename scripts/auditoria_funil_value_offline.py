#!/usr/bin/env python3
"""Diagnostico SHADOW do funil Top5/Value num JSON PRIVADO e copiado do Railway.

Nao altera o ficheiro-fonte; nao usa API, variaveis de ambiente nem requests.
As classificacoes representam EVIDENCIA GUARDADA, nao a causa real da falha.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from math import isfinite
from pathlib import Path

START = 207
TARGET = 50
FIELDS = ("snapshot", "data_jogo", "jogo", "liga", "mercado", "ranking", "versao", "probabilidade", "odd_minima", "odd_inicial", "odd_atual", "odd_confirmada", "odd_entrada_oficial", "classe", "valor_estado", "resultado_binario", "notas")


def quote(value):
    if isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if isfinite(x) and x > 1 else None


def prob(value):
    if isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if isfinite(x) and 0 < x < 1 else None


def official_entry(p):
    """Reproduz estritamente RegistoPrevisoes._odd_entrada_valor (V1.3)."""
    confirmed = quote(p.get("odd_valor_confirmado"))
    if confirmed is not None:
        return confirmed
    first = quote(p.get("odd_real"))
    minimum = quote(p.get("odd_minima"))
    if first is not None and minimum is not None and first >= minimum:
        return first
    return None


def classify(p):
    first = quote(p.get("odd_real"))
    current = quote(p.get("odd_mercado_atual"))
    minimum = quote(p.get("odd_minima"))
    entry = official_entry(p)
    notes = []
    if entry is not None:
        if minimum is None:
            notes.append("VALUE guardado mas odd_minima ausente/invalida")
        return "VALUE_confirmado", entry, notes
    if p.get("valor_confirmado_em"):
        notes.append("Data de confirmacao sem odd de entrada oficial valida")
    if minimum is None:
        return "limiar_ausente", None, notes
    observed = [x for x in (first, current) if x is not None]
    if not observed:
        # Sem odd guardada != casa sem mercado != falta de tentativa
        return "sem_odd_guardada", None, notes
    if max(observed) < minimum:
        return "odds_guardadas_abaixo_minimo", None, notes
    return "inconsistencia_metadados_ou_tempos", None, notes


def process(records):
    out = []
    for idx, p in enumerate(records, 1):
        if idx < START or str(p.get("modelo_versao") or "") != "V1.2":
            continue
        try:
            ranking = int(p.get("ranking_modelo"))
        except (ValueError, TypeError):
            continue
        if ranking not in range(1, 6):
            continue
        reason, entry, notes = classify(p)
        out.append({
            "snapshot": idx,
            "data_jogo": str(p.get("data_jogo") or ""),
            "jogo": f"{p.get('casa') or '?'} vs {p.get('fora') or '?'}",
            "liga": str(p.get("liga") or "Nao registada"),
            "mercado": str(p.get("mercado") or "Nao registado"),
            "ranking": ranking,
            "versao": "V1.2",
            "probabilidade": prob(p.get("probabilidade")),
            "odd_minima": quote(p.get("odd_minima")),
            "odd_inicial": quote(p.get("odd_real")),
            "odd_atual": quote(p.get("odd_mercado_atual")),
            "odd_confirmada": quote(p.get("odd_valor_confirmado")),
            "odd_entrada_oficial": entry,
            "classe": reason,
            "valor_estado": str(p.get("valor_estado") or ""),
            "resultado_binario": p.get("resultado_binario") if p.get("resultado_binario") in (0, 1) else None,
            "notas": "; ".join(notes),
            "_tempo": str(p.get("valor_confirmado_em") or p.get("odds_capturada_em") or p.get("criada_em") or ""),
        })
    # Coorte oficial ordenada por confirmacao, sem substituicao
    confirms = sorted((x for x in out if x["odd_entrada_oficial"] is not None), key=lambda x: (x["_tempo"] or "9999-12-31T23:59:59Z", x["snapshot"]))
    included = {x["snapshot"] for x in confirms[:TARGET]}
    for x in out:
        x["coorte_v13"] = "SIM" if x["snapshot"] in included else "NAO"
    return out


def csvwrite(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def run(source: Path, destination: Path):
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if source == destination or destination.exists() or source.is_symlink() or destination.is_symlink():
        raise ValueError("Origem/saida insegura: exigir copia real e nova pasta de saida")
    hash_before = hashlib.sha256(source.read_bytes()).hexdigest()
    doc = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("previsoes"), list):
        raise ValueError("Formato de historico invalido: falta lista 'previsoes'")
    if not all(isinstance(x, dict) for x in doc["previsoes"]):
        raise ValueError("Registo de previsao invalido")
    records = process(doc["previsoes"])
    by_reason = Counter(x["classe"] for x in records)
    by_market = defaultdict(Counter)
    by_league = defaultdict(Counter)
    for row in records:
        by_market[row["mercado"]][row["classe"]] += 1
        by_league[row["liga"]][row["classe"]] += 1
    destination.mkdir(parents=True, exist_ok=False)
    csvwrite(destination/"top5_funil_detalhe.csv", list(FIELDS)+["coorte_v13"], records)
    csvwrite(destination/"funil_motivos.csv", ["classe", "quantidade"], [{"classe": k, "quantidade": v} for k,v in sorted(by_reason.items())])
    cols=["grupo", "classe", "quantidade"]
    csvwrite(destination/"funil_por_mercado.csv", cols, [{"grupo": key,"classe": k,"quantidade": n} for key,cnt in sorted(by_market.items()) for k,n in sorted(cnt.items())])
    csvwrite(destination/"funil_por_liga.csv", cols, [{"grupo": key,"classe": k,"quantidade": n} for key,cnt in sorted(by_league.items()) for k,n in sorted(cnt.items())])
    hash_after = hashlib.sha256(source.read_bytes()).hexdigest()
    if hash_after != hash_before:
        raise RuntimeError("O ficheiro-fonte mudou durante o diagnostico")
    n_confirmed=sum(x["odd_entrada_oficial"] is not None for x in records)
    summary={"top5_monitorizadas":len(records), "value_confirmadas_elegiveis":n_confirmed,
             "coorte_v13":min(TARGET,n_confirmed),"por_classe":dict(by_reason),"sha256_original":hash_before,"fonte_intacta":hash_before==hash_after}
    (destination/"RESUMO.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (destination/"LEIA_ME.txt").write_text(
        "SHADOW: Resultado offline, nao altera a V1.3.\n"
        "sem_odd_guardada significa apenas falta de cotacao NOS SNAPSHOTS.\n"
        "NAO prova ausencia de mercado Betano, falta de tentativa ou ausencia de odds em outras casas.\n"
        "odds_guardadas_abaixo_minimo identifica somente cotacoes historicamente guardadas.\n"
        "Nao inferir oportunidades alternativas, frequencia de erros nem lucros.\n"
        "A coorte comercial mantem o seu critério original de primeira odd confirmada.\n",
        encoding="utf-8")
    return summary


if __name__ == "__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--previsoes", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True)
    a=ap.parse_args()
    print(json.dumps(run(a.previsoes,a.saida),ensure_ascii=False,indent=2))
