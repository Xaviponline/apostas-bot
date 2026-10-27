"""Auditoria offline da viabilidade do Time Machine.

Lê apenas um export JSON do Research Lab. Sem rede, sem escrita, sem apostas.
Uso: python time_machine_auditoria_shadow.py caminho/dataset.json
"""
import json
import math
import sys
from collections import Counter
from pathlib import Path


def _num(x):
    try:
        y = float(x)
        return y if math.isfinite(y) else None
    except (TypeError, ValueError, OverflowError):
        return None


def auditar(records):
    if not isinstance(records, list):
        raise ValueError("records deve ser uma lista")
    total = len(records)
    liquidados = 0
    com_odd = 0
    elegiveis = 0
    sem_odd = 0
    com_fecho = 0
    dias = set()
    mercados = Counter()
    for r in records:
        if not isinstance(r, dict):
            continue
        outcome = r.get("resultado_binario")
        if outcome not in (0, 1, "0", "1"):
            continue
        liquidados += 1
        mercados[str(r.get("mercado") or "desconhecido")] += 1
        data = str(r.get("data_jogo") or "")[:10]
        if len(data) == 10:
            dias.add(data)
        odd = _num(r.get("odd_real"))
        minima = _num(r.get("odd_minima"))
        fecho = _num(r.get("odd_fecho"))
        if odd is None or odd <= 1:
            sem_odd += 1
        else:
            com_odd += 1
        if fecho is not None and fecho > 1:
            com_fecho += 1
        if odd is not None and odd > 1 and minima is not None and odd >= minima:
            elegiveis += 1
    return {
        "registos": total,
        "liquidados": liquidados,
        "com_odd_real": com_odd,
        "liquidados_sem_odd_real": sem_odd,
        "com_odd_fecho": com_fecho,
        "elegiveis_odd_minima": elegiveis,
        "dias_distintos": len(dias),
        "mercados_liquidados": dict(mercados),
        "aviso": "Auditoria de cobertura, nao e backtest nem validacao de ROI; exige verificar timestamps e ausencia de fuga de informacao."
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python time_machine_auditoria_shadow.py dataset.json")
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(auditar(payload["records"]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
