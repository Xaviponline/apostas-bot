"""Registo prospetivo SHADOW de TODOS os jogos com análise estatística.

Apenas dados calculados na análise existente; não faz pedidos externos,
não altera seleção, odds, probabilidades, CLV ou histórico oficial.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from estatisticas_espn import EstatisticasESPN


def _chave(jogo):
    # IDs estáveis: evitar colisões entre equipas e datas.
    return "|".join(str(jogo.get(k, "")) for k in
                    ("id", "timestamp", "casa_id", "fora_id", "liga_codigo"))


def criar_registo(analise):
    jogo = analise.get("jogo") or {}
    if not isinstance(jogo, dict):
        return None
    campos = ("lambda_casa", "lambda_fora", "media_liga_casa", "media_liga_fora", "probabilidades")
    if any(analise.get(campo) is None for campo in campos):
        return None
    lc, lf = float(analise["lambda_casa"]), float(analise["lambda_fora"])
    bc, bf = float(analise["media_liga_casa"]), float(analise["media_liga_fora"])
    if min(lc, lf, bc, bf) <= 0:
        return None
    atual = analise["probabilidades"]
    if not isinstance(atual, dict) or any(k not in atual for k in ("Vitória Casa", "Empate", "Vitória Fora")):
        return None
    novo = EstatisticasESPN._probabilidades(.6*lc+.4*bc, .6*lf+.4*bf)
    return {
        "versao": 1,
        "capturado_em_utc": datetime.now(timezone.utc).isoformat(),
        "chave": str(analise.get("liga_codigo") or "") + "|" + _chave(jogo),
        "jogo": {k: jogo.get(k) for k in ("id","timestamp","horario","casa_id","fora_id","casa","fora","liga_codigo")},
        "liga_codigo": analise.get("liga_codigo"),
        "lambda_casa": lc, "lambda_fora": lf,
        "media_liga_casa": bc, "media_liga_fora": bf,
        "original_1x2": {k: atual[k] for k in ("Vitória Casa","Empate","Vitória Fora")},
        "alternativa_1x2": {k: novo[k] for k in ("Vitória Casa","Empate","Vitória Fora")},
        "resultado": None,
    }


def guardar_registos(caminho, analises):
    """Append-only, deduplicado; falhas são isoladas da análise principal."""
    destino = Path(caminho)
    novos = [r for a in analises if (r := criar_registo(a)) is not None]
    ignorados = len(analises) - len(novos)
    if ignorados:
        logging.info("LAMBDA_SHADOW | snapshots_incompletos_ignorados=%s | validos=%s", ignorados, len(novos))
    if not novos:
        logging.info("LAMBDA_SHADOW | recebidos=%s | validos=0 | incompletos=%s | duplicados=0 | gravados=0", len(analises), ignorados)
        return 0
    destino.parent.mkdir(parents=True, exist_ok=True)
    existentes = set()
    if destino.exists():
        with destino.open(encoding="utf-8") as f:
            for linha in f:
                try:
                    obj=json.loads(linha)
                    existentes.add(obj.get("chave"))
                except (ValueError,TypeError):
                    continue
    gravados=0
    duplicados=0
    with destino.open("a",encoding="utf-8") as f:
        for reg in novos:
            if reg["chave"] in existentes:
                duplicados += 1
                continue
            f.write(json.dumps(reg,ensure_ascii=False,allow_nan=False)+"\n")
            existentes.add(reg["chave"])
            gravados+=1
    logging.info("LAMBDA_SHADOW | recebidos=%s | validos=%s | incompletos=%s | duplicados=%s | gravados=%s | destino=%s", len(analises), len(novos), ignorados, duplicados, gravados, destino)
    return gravados


def registar_seguro(caminho, analises):
    try:
        return guardar_registos(caminho, analises)
    except (OSError,ValueError,TypeError,KeyError,OverflowError):
        logging.exception("LAMBDA_SHADOW | falha isolada na telemetria")
        return 0
