"""Validação manual de resultados finais de hoje para snapshots Lambda Shadow.

Apenas ESPN, sem odds pagas. Registos originais e previsões oficiais não
são modificados. Resultados confirmados são acrescentados ao ficheiro
independente JSONL, com identidade de evento estrita.
"""
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from estatisticas_espn import EstatisticasESPN
from lambda_resultados_shadow import guardar_resultados, identidade, ler

PORTUGAL = ZoneInfo("Europe/Lisbon")
LIGA_SEGURA = re.compile(r"^[a-zA-Z0-9._]+$")
ESPERA_MINUTOS = 85
TETO_LIGAS = 12


def _finais_existentes(caminho):
    finais = set()
    for r in ler(caminho):
        try:
            k = identidade(r["jogo"], r["liga_codigo"])
            if (k is not None and r.get("fonte") == "ESPN_STATUS_FINAL"
                    and type(r["golos_casa"]) is int and type(r["golos_fora"]) is int
                    and min(r["golos_casa"], r["golos_fora"]) >= 0):
                finais.add((r["chave"], k))
        except (KeyError, TypeError, ValueError):
            continue
    return finais


def validar_hoje(caminho_snapshots, agora=None, session=None):
    """Um comando do OWNER: ESPN por liga de jogos iniciados, no máximo 12 GET.

    A ESPN pode não ter resultados finais disponíveis durante o dia;
    esses jogos mantêm-se pendentes até nova verificação manual ou diária.
    """
    agora = agora or datetime.now(PORTUGAL)
    if agora.tzinfo is None:
        raise ValueError("agora deve incluir fuso horário")
    hoje = agora.astimezone(PORTUGAL).date()
    caminho = Path(caminho_snapshots)
    destino = caminho.with_name("lambda_prospectivo_resultados.jsonl")
    linhas = [f"🧪 LAMBDA HOJE — {hoje.strftime('%d/%m/%Y')}",
              "🔒 Apenas resultados ESPN; zero odds pagas; V1.3 intacta."]
    if not caminho.is_file():
        return "\n".join(linhas + ["📭 Sem snapshots Shadow guardados."])

    elegiveis = {}
    rejeitados = Counter()
    for r in ler(caminho):
        try:
            j = r["jogo"]
            liga = r["liga_codigo"]
            chave = r["chave"]
            k = identidade(j, liga)
            captura = datetime.fromisoformat(r["capturado_em_utc"])
            if r.get("versao") != 1 or k is None or not chave or not isinstance(liga, str) or not LIGA_SEGURA.fullmatch(liga):
                rejeitados["identidade"] += 1
                continue
            if captura.tzinfo is None or captura.timestamp() >= k[-1]:
                rejeitados["captura"] += 1
                continue
            if datetime.fromtimestamp(k[-1], PORTUGAL).date() != hoje:
                continue
            elegiveis[(chave, k)] = r
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            rejeitados["invalido"] += 1

    ja_iniciados = {k:r for k,r in elegiveis.items()
                    if k[1][-1] <= agora.timestamp() - ESPERA_MINUTOS * 60}
    ja_finais = _finais_existentes(destino)
    por_resolver = {k:r for k,r in ja_iniciados.items() if k not in ja_finais}
    ligas = sorted({r["liga_codigo"] for r in por_resolver.values()})
    consultar = ligas[:TETO_LIGAS]
    falhas = []
    historicos = {}
    cliente = session or requests.Session()
    for liga in consultar:
        try:
            resposta = cliente.get(
                f"{EstatisticasESPN.BASE}/{liga}/scoreboard",
                params={"dates": hoje.strftime("%Y%m%d"), "limit": 500},
                timeout=(5, 25),
            )
            resposta.raise_for_status()
            payload = resposta.json()
            eventos = payload.get("events") if isinstance(payload, dict) else None
            if not isinstance(eventos, list):
                raise ValueError("Resposta ESPN sem lista de eventos")
            historicos[liga] = [
                p for evento in eventos
                if (p := EstatisticasESPN._normalizar_resultado(evento, liga)) is not None
                and p.get("final_regulamentar_shadow") is True
            ]
        except (requests.RequestException, TypeError, KeyError, ValueError):
            falhas.append(liga)

    novos = guardar_resultados(caminho, destino, historicos) if historicos else 0
    depois = _finais_existentes(destino)
    confirmados = len(set(elegiveis) & depois)
    pendentes = len(elegiveis) - confirmados
    linhas.extend([
        f"📚 Jogos de hoje com snapshot pré-jogo: {len(elegiveis)}",
        f"⏱️ Já iniciados há pelo menos {ESPERA_MINUTOS} min: {len(ja_iniciados)} | ainda cedo: {len(elegiveis)-len(ja_iniciados)}",
        f"✅ Resultados ESPN finais confirmados: {confirmados} | novos gravados nesta verificação: {novos}",
        f"⏳ Sem resultado final confirmado: {pendentes}",
        f"🌐 Competições consultadas: {len(consultar)} | falhas: {len(falhas)} | adiadas pelo limite: {max(0,len(ligas)-TETO_LIGAS)}",
    ])
    if falhas:
        linhas.append("⚠️ ESPN indisponível: " + ", ".join(falhas))
    linhas.append("ℹ️ Um jogo só é liquidado no Shadow com IDs, horário e STATUS_FINAL exatos. O Brier fica dependente dos resultados concluídos.")
    return "\n".join(linhas)


def validar_pendentes(caminho_snapshots, agora=None, session=None):
    """Recupera até três dias de resultados Shadow, incluindo após a meia-noite.

    Apenas o OWNER chama esta função. No máximo 12 consultas públicas ESPN,
    zero odds. Todos os resultados são estritamente reconciliados com os
    snapshots originais capturados antes do início dos jogos.
    """
    agora = agora or datetime.now(PORTUGAL)
    if agora.tzinfo is None:
        raise ValueError("agora deve incluir fuso horário")
    hoje = agora.astimezone(PORTUGAL).date()
    inicio = hoje - timedelta(days=2)
    caminho = Path(caminho_snapshots)
    destino = caminho.with_name("lambda_prospectivo_resultados.jsonl")
    linhas = [f"🧪 LAMBDA PENDENTES — {inicio:%d/%m} a {hoje:%d/%m/%Y}",
              "🔒 ESPN independente, zero odds pagas; V1.3 intacta."]
    if not caminho.is_file():
        return "\n".join(linhas + ["📭 Sem snapshots Shadow guardados."])

    elegiveis = {}
    precoces = 0
    for r in ler(caminho):
        try:
            j, liga, chave = r["jogo"], r["liga_codigo"], r["chave"]
            k = identidade(j, liga)
            captura = datetime.fromisoformat(r["capturado_em_utc"])
            if (r.get("versao") != 1 or k is None or not chave
                    or not isinstance(liga, str) or not LIGA_SEGURA.fullmatch(liga)
                    or captura.tzinfo is None or captura.timestamp() >= k[-1]):
                continue
            dia = datetime.fromtimestamp(k[-1], PORTUGAL).date()
            if not inicio <= dia <= hoje:
                continue
            if k[-1] > agora.timestamp() - ESPERA_MINUTOS * 60:
                precoces += 1
                continue
            elegiveis[(chave, k)] = (dia, liga)
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            continue

    confirmados_antes = _finais_existentes(destino)
    por_resolver = {k: valor for k, valor in elegiveis.items()
                    if k not in confirmados_antes}
    # Uma chamada para cada dia/competição, nunca um pedido por partida.
    grupos = sorted(set(por_resolver.values()))
    consultar = grupos[:TETO_LIGAS]
    historicos = {}
    falhas = []
    cliente = session or requests.Session()
    for dia, liga in consultar:
        try:
            resposta = cliente.get(
                f"{EstatisticasESPN.BASE}/{liga}/scoreboard",
                params={"dates": dia.strftime("%Y%m%d"), "limit": 500},
                timeout=(5, 25),
            )
            resposta.raise_for_status()
            payload = resposta.json()
            eventos = payload.get("events") if isinstance(payload, dict) else None
            if not isinstance(eventos, list):
                raise ValueError("Resposta ESPN sem lista de eventos")
            historicos.setdefault(liga, []).extend(
                p for evento in eventos
                if (p := EstatisticasESPN._normalizar_resultado(evento, liga)) is not None
                and p.get("final_regulamentar_shadow") is True
            )
        except (requests.RequestException, TypeError, KeyError, ValueError):
            falhas.append(f"{liga}/{dia:%d-%m}")

    novos = guardar_resultados(caminho, destino, historicos) if historicos else 0
    finais_depois = _finais_existentes(destino)
    confirmados = len(set(elegiveis) & finais_depois)
    linhas.extend([
        f"📚 Snapshots elegíveis (últimos 3 dias): {len(elegiveis)} | demasiado recentes: {precoces}",
        f"✅ Resultados ESPN confirmados: {confirmados} | novos gravados: {novos}",
        f"⏳ Ainda sem final confirmado: {len(elegiveis) - confirmados}",
        f"🌐 Consultas ESPN: {len(consultar)} | falhas: {len(falhas)} | grupos adiados: {max(0, len(grupos)-TETO_LIGAS)}",
    ])
    if falhas:
        linhas.append("⚠️ Falhas ESPN: " + ", ".join(falhas))
    linhas.append("ℹ️ Só jogos com identidade e STATUS_FINAL exatos. Sem alterações aos snapshots originais.")
    return "\n".join(linhas)
