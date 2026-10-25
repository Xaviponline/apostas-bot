#!/usr/bin/env python3
"""Auditoria offline, SOMENTE LEITURA. Não importa API, não faz rede e não altera o original.

Uso, numa CÓPIA PRIVADA de ficheiros persistidos:
  python scripts/auditoria_calibracao_offline.py \
    --previsoes /copia/previsoes_premium.json \
    --rastreio /copia/odds_rastreio.jsonl \
    --tentativas /copia/clv_tentativas.json \
    --saida /copia/relatorio_auditoria

Argumentos rastreio e tentativas são opcionais. A pasta de saída é nova.
Os ficheiros de resultados contêm dados das previsões, não partilhar publicamente.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
import sys

BIN_NAMES = ("50–55%", "55–60%", "60–65%", "65–70%", "70%+", "Abaixo de 50%")
MARKETS = (
    "Vitória Casa", "Vitória Fora", "Ambas Marcam",
    "Over 1.5 Golos", "Over 2.5 Golos", "Under 2.5 Golos",
    "Under 3.5 Golos", "1X (Casa ou Empate)", "X2 (Empate ou Fora)",
)

def num(x, low=None, high=None):
    if isinstance(x, bool):
        return None
    try:
        x = float(x)
    except (TypeError, ValueError, OverflowError):
        return None
    if not isfinite(x) or (low is not None and x < low) or (high is not None and x > high):
        return None
    return x

def bin_prob(p):
    if p < 0.50: return "Abaixo de 50%"
    if p < 0.55: return "50–55%"
    if p < 0.60: return "55–60%"
    if p < 0.65: return "60–65%"
    if p < 0.70: return "65–70%"
    return "70%+"

def write_csv(path, cols, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in cols})

def read_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def load_records(path):
    obj = read_json(path)
    if isinstance(obj, dict):
        obj = obj.get("previsoes")
    if not isinstance(obj, list):
        raise ValueError("JSON deve ser lista ou conter chave 'previsoes' com lista.")
    if not all(isinstance(x, dict) for x in obj):
        raise ValueError("Previsões inválidas: pelo menos uma não é objeto.")
    return obj

def normalize_records(records):
    out, errors = [], []
    for i, r in enumerate(records, 1):
        prob = num(r.get("probabilidade"), low=0, high=1)
        outcome = r.get("resultado_binario")
        if isinstance(outcome, bool) or outcome not in (0, 1, None):
            errors.append({"snapshot": i, "causa": "resultado_invalido", "valor": repr(outcome)})
            outcome = None
        if prob is None:
            errors.append({"snapshot": i, "causa": "probabilidade_invalida", "valor": repr(r.get("probabilidade"))})
        odd = num(r.get("odd_real"), low=1.0000001)
        valor_confirmado = num(r.get("odd_valor_confirmado"), low=1.0000001)
        fecho = num(r.get("odd_fecho"), low=1.0000001)
        row = {
            "snapshot": i,
            "data": r.get("data_jogo") or "",
            "jogo": f"{r.get('casa') or '?'} vs {r.get('fora') or '?'}",
            "liga": r.get("liga") or "Liga não registada",
            "mercado": r.get("mercado") or "Mercado não registado",
            "modelo_versao": r.get("modelo_versao") or "",
            "ranking": r.get("ranking_modelo") if r.get("ranking_modelo") is not None else "",
            "probabilidade_prevista": prob,
            "probabilidade_bruta": num(r.get("probabilidade_bruta"), low=0, high=1),
            "faixa": bin_prob(prob) if prob is not None else "Probabilidade inválida",
            "odd_inicial": odd,
            "odd_valor_confirmado": valor_confirmado,
            "odd_fecho": fecho,
            "resultado": "GANHOU" if outcome == 1 else "PERDEU" if outcome == 0 else "PENDENTE/SEM RESULTADO",
            "resultado_binario": outcome,
            "marcador": f"{r.get('golos_casa')}-{r.get('golos_fora')}" if r.get("golos_casa") is not None and r.get("golos_fora") is not None else "",
            "event_id_modelo": r.get("event_id") or "",
            "estado": r.get("estado") or "",
        }
        out.append(row)
    return out, errors

def metrics(rows):
    settled = [r for r in rows if r["resultado_binario"] in (0, 1) and r["probabilidade_prevista"] is not None]
    n = len(settled)
    wins = sum(r["resultado_binario"] for r in settled)
    psum = sum(r["probabilidade_prevista"] for r in settled)
    brier = sum((r["probabilidade_prevista"] - r["resultado_binario"]) ** 2 for r in settled) / n if n else None
    return {
        "previsoes_total": len(rows),
        "liquidadas_validas": n,
        "ganhas": wins,
        "perdidas": n-wins,
        "sem_resultado_ou_prob_invalida": len(rows)-n,
        "taxa_acerto_pct": round(100 * wins/n, 4) if n else "",
        "prob_prevista_media_pct": round(100 * psum/n, 4) if n else "",
        "acertos_esperados": round(psum, 4) if n else "",
        "diferenca_real_prev_pp": round(100 * (wins-psum)/n, 4) if n else "",
        "brier": round(brier, 6) if n else "",
    }

def grouped(rows, keys):
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(r[k] for k in keys)].append(r)
    out = []
    for vals, items in sorted(groups.items(), key=lambda item: tuple(str(x) for x in item[0])):
        out.append({**dict(zip(keys, vals)), **metrics(items)})
    return out

def read_jsonl(path):
    with path.open("r", encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                x = json.loads(line)
            except (ValueError, TypeError):
                yield {"diagnostico": "linha_jsonl_invalida", "linha_erro": n}
                continue
            if isinstance(x, dict):
                yield x

def market_evidence(rastreio=None, tentativas=None):
    observed = Counter()
    failures = []
    if rastreio is not None:
        for row in read_jsonl(rastreio):
            name = str(row.get("mercado_nome_fonte") or "").strip()
            if name:
                key = (
                    row.get("fonte") or "Fonte não indicada",
                    row.get("mercado_id_fonte") or "",
                    name,
                    row.get("periodo_fonte") or "",
                    row.get("linha_fonte") if row.get("linha_fonte") is not None else "",
                    row.get("mercado_modelo") or "",
                )
                observed[key] += 1
            motivo = row.get("diagnostico")
            if motivo:
                failures.append({
                    "origem": "odds_rastreio", "data": row.get("observado_em") or "",
                    "snapshot": "", "jogo": row.get("jogo") or "",
                    "mercado_pedido": row.get("mercado_modelo") or "",
                    "motivo_guardado": motivo,
                    "observacao": "Diagnóstico registado; não implica ausência real na Betano",
                })
    if tentativas is not None:
        obj = read_json(tentativas)
        for row in obj.get("eventos", []) if isinstance(obj, dict) else []:
            if not isinstance(row, dict):
                continue
            if row.get("resultado") == "fecho_capturado":
                continue
            ctx = row.get("mercados_contexto") or {}
            observation = ""
            if isinstance(ctx, dict) and all(isinstance(ctx.get(k), int) for k in ("total", "compativeis", "sem_catalogo")):
                observation = (
                    f"recebidos={ctx['total']}; compativeis={ctx['compativeis']}; "
                    f"sem_catalogo={ctx['sem_catalogo']}"
                )
            failures.append({
                "origem": "clv_tentativas",
                "data": row.get("registado_em") or "",
                "snapshot": row.get("snapshot") or "",
                "jogo": "", "mercado_pedido": "",
                "motivo_guardado": row.get("motivo") or "desconhecido",
                "observacao": observation or "Sem metadados adicionais: causa concreta não demonstrada",
            })
    obs_cols = ("fonte", "mercado_id_fonte", "nome_mercado_fonte", "periodo_fonte", "linha_fonte", "mercado_pedido", "observacoes")
    markets = [dict(zip(obs_cols, (*key, n))) for key, n in sorted(observed.items(), key=lambda x: str(x[0]))]
    return markets, failures

def run(previsoes, saida, rastreio=None, tentativas=None):
    src = previsoes.resolve(strict=True)
    sources = [src] + [p.resolve(strict=True) for p in (rastreio, tentativas) if p is not None]
    dst = saida.resolve()
    if dst in sources or any(dst == s.parent for s in sources):
        raise ValueError("Saída tem de ser uma pasta distinta dos ficheiros de origem.")
    if dst.exists():
        raise FileExistsError("Pasta de saída já existe: não substituir resultados anteriores.")
    raws = load_records(src)
    normalized, errors = normalize_records(raws)
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    dst.mkdir(parents=True, exist_ok=False)
    pred_cols = ("snapshot","data","jogo","liga","mercado","modelo_versao","ranking","probabilidade_prevista","probabilidade_bruta","faixa","odd_inicial","odd_valor_confirmado","odd_fecho","resultado","resultado_binario","marcador","event_id_modelo","estado")
    write_csv(dst/"previsoes_todas.csv", pred_cols, normalized)
    m_cols = list(metrics([]).keys())
    group_specs = {
        "calibracao_global.csv": (),
        "calibracao_faixas.csv": ("faixa",),
        "calibracao_mercados.csv": ("mercado", "faixa"),
        "calibracao_ligas.csv": ("liga", "faixa"),
        "calibracao_mercado_liga.csv": ("mercado","liga","faixa"),
        "calibracao_por_versao.csv": ("modelo_versao","faixa"),
    }
    for filename, keys in group_specs.items():
        rows = grouped(normalized, keys) if keys else [metrics(normalized)]
        if keys == ("faixa",):
            present = {r["faixa"] for r in rows}
            rows += [
                {"faixa": label, **metrics([])}
                for label in BIN_NAMES if label not in present
            ]
            rows.sort(key=lambda row: BIN_NAMES.index(row["faixa"]) if row["faixa"] in BIN_NAMES else 99)
        write_csv(dst / filename, list(keys)+m_cols, rows)
    write_csv(dst/"avisos_dados.csv", ("snapshot","causa","valor"), errors)
    obs, fails = market_evidence(rastreio, tentativas)
    write_csv(dst/"nomes_mercados_observados.csv",
              ("fonte","mercado_id_fonte","nome_mercado_fonte","periodo_fonte","linha_fonte","mercado_pedido","observacoes"), obs)
    write_csv(dst/"falhas_mercado_historico.csv",
              ("origem","data","snapshot","jogo","mercado_pedido","motivo_guardado","observacao"), fails)
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    if before != after:
        raise RuntimeError("Hash de fonte diferente: verificar o ficheiro de origem.")
    summary = metrics(normalized)
    (dst/"LEIA_ME.txt").write_text(
        "AUDITORIA OFFLINE — SEM REDE, SEM ALTERAÇÃO DE HISTÓRICO\n"
        "Faixas não sobrepostas: [50%,55%), [55%,60%), [60%,65%), [65%,70%), [70%,100%].\n"
        "Abaixo de 50% explicitado para evitar omissões. Desconhecidos não são derrotas.\n"
        "Os CSV de mercados mostram nomes guardados no histórico local; não são catálogos completos da OddsPapi.\n"
        "Falta de observações não comprova que o mercado não existia na casa.\n"
        f"Total={summary['previsoes_total']}; liquidadas_validas={summary['liquidadas_validas']}; "
        f"ganhas={summary['ganhas']}; perdidas={summary['perdidas']}; erros={len(errors)}.\n"
        f"Hashes SHA-256 das fontes (antes=depois): {json.dumps(before, ensure_ascii=False)}\n",
        encoding="utf-8",
    )
    return summary

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--previsoes", required=True, type=Path)
    ap.add_argument("--rastreio", type=Path)
    ap.add_argument("--tentativas", type=Path)
    ap.add_argument("--saida", required=True, type=Path)
    a=ap.parse_args()
    print(json.dumps(run(a.previsoes, a.saida, a.rastreio, a.tentativas), ensure_ascii=False, indent=2))

if __name__=="__main__":
    main()
