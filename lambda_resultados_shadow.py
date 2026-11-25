"""Resultados independentes para snapshots Lambda, sem chamadas externas."""
import json
from datetime import datetime
from pathlib import Path
from math import isfinite


def identidade(j, liga):
    try:
        ts = float(j["timestamp"])
        ids = tuple(int(j[k]) for k in ("id", "casa_id", "fora_id"))
        if not liga or not isfinite(ts) or min(ids) <= 0:
            return None
        return (str(liga), *ids, ts)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def ler(path):
    if Path(path).exists():
        with Path(path).open(encoding="utf-8") as f:
            for linha in f:
                try:
                    r = json.loads(linha)
                    if isinstance(r, dict):
                        yield r
                except ValueError:
                    continue


def guardar_resultados(snapshots, destino, historicos):
    finais = {}
    conflitos = set()
    for liga, partidas in historicos.items():
        for p in partidas:
            if p.get("final_regulamentar_shadow") is not True:
                continue
            k = identidade(p, liga)
            gc, gf = p.get("golos_casa"), p.get("golos_fora")
            if k is None or type(gc) is not int or type(gf) is not int or min(gc, gf) < 0:
                continue
            if k in finais and finais[k] != (gc, gf):
                conflitos.add(k)
            finais[k] = (gc, gf)
    existentes = {r.get("chave") for r in ler(destino)}
    novos = []
    for r in ler(snapshots):
        try:
            if r.get("versao") != 1:
                continue
            k = identidade(r["jogo"], r["liga_codigo"])
            chave = r["chave"]
            captura = datetime.fromisoformat(r["capturado_em_utc"])
            if not chave or k is None or captura.tzinfo is None or captura.timestamp() >= k[-1]:
                continue
            if k in conflitos or k not in finais or chave in existentes:
                continue
            gc, gf = finais[k]
            novos.append({"versao": 1, "chave": chave, "jogo": r["jogo"], "liga_codigo": r["liga_codigo"], "golos_casa": gc, "golos_fora": gf, "fonte": "ESPN_STATUS_FINAL"})
            existentes.add(chave)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    if novos:
        with Path(destino).open("a", encoding="utf-8") as f:
            for r in novos:
                f.write(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n")
    return len(novos)
