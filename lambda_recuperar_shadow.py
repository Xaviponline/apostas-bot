"""Recuperação HISTÓRICA controlada de finais ESPN para o Lambda SHADOW.

Por omissão apenas pré-visualização local, sem HTTP nem escrita.
Só a instrução explícita OWNER '/lambda_recuperar executar N' consulta no
máximo seis pares (data, liga) na ESPN e acrescenta finais verificados ao
ficheiro independente existente. Não mexe no modelo V1.2/V1.3, picks,
preços, CLV, ROI, snapshots prospetivos nem no relatório original.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import re

import requests

from estatisticas_espn import EstatisticasESPN
from lambda_cobertura_shadow import _indices_independentes, _vetor, _captura_pre_jogo
from lambda_resultados_shadow import identidade, guardar_resultados, ler

PORTUGAL = ZoneInfo("Europe/Lisbon")
TETO_GRUPOS = 6
ESPERA_MINUTOS = 85
LIGA_SEGURA = re.compile(r"^[A-Za-z0-9._]+$")


def _grupos(snapshots_path, agora):
    """Paginação estável sobre TODOS os pares históricos válidos.

    Não descarta grupos cujo resultado já foi confirmado: assim, o grupo
    da página N nunca muda de página só porque um resultado foi acrescentado.
    """
    registos = defaultdict(dict)
    rejeitados = Counter()
    seen = set()
    for r in ler(snapshots_path):
        try:
            if r.get("versao") != 1 or not _vetor(r):
                rejeitados["vetor_invalido"] += 1
                continue
            j, liga, chave = r["jogo"], r["liga_codigo"], r["chave"]
            k = identidade(j, liga)
            if (k is None or not isinstance(liga, str)
                    or not LIGA_SEGURA.fullmatch(liga)
                    or not isinstance(chave, str) or not chave):
                rejeitados["identidade_invalida"] += 1
                continue
            par = (chave, k)
            if par in seen:
                rejeitados["duplicados"] += 1
                continue
            seen.add(par)
            if not _captura_pre_jogo(r, k):
                rejeitados["captura_invalida"] += 1
                continue
            if k[-1] > agora.timestamp() - ESPERA_MINUTOS * 60:
                rejeitados["recente_ou_futuro"] += 1
                continue
            dia = datetime.fromtimestamp(k[-1], PORTUGAL).date()
            registos[(dia, liga)][par] = r
        except (KeyError, TypeError, ValueError, OverflowError):
            rejeitados["registo_invalido"] += 1
    grupos = sorted(registos.items(), key=lambda x: (-x[0][0].toordinal(), x[0][1]))
    return grupos, rejeitados


def _args(argumentos):
    s = str(argumentos or "").strip().lower()
    if not s:
        return False, 1
    tokens = s.split()
    if len(tokens) == 1 and tokens[0].isascii() and tokens[0].isdecimal():
        return False, int(tokens[0]) if len(tokens[0]) <= 4 else 0
    if (len(tokens) == 2 and tokens[0] == "executar"
            and tokens[1].isascii() and tokens[1].isdecimal()):
        return True, int(tokens[1]) if len(tokens[1]) <= 4 else 0
    return False, 0


def _eventos_finais(payload, liga, alvos):
    """Nunca aceitar marcador por nome, por data aproximada ou por IDs parciais."""
    eventos = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(eventos, list):
        raise ValueError("ESPN não devolveu lista de eventos")
    brutos = defaultdict(list)
    normalizados = defaultdict(list)
    for evento in eventos:
        if not isinstance(evento, dict):
            continue
        if evento.get("id") is not None:
            brutos[str(evento["id"])].append(evento)
        n = EstatisticasESPN._normalizar_resultado(evento, liga)
        if n is not None:
            normalizados[str(n["id"])].append(n)
    finais = []
    motivos = Counter()
    for chave, k in alvos:
        ident = str(k[1])
        bruto = brutos.get(ident, [])
        norm = normalizados.get(ident, [])
        if not bruto:
            motivos["id_ausente"] += 1
        elif len(bruto) != 1 or len(norm) > 1:
            motivos["id_ambiguo"] += 1
        elif not norm:
            motivos["nao_normalizado"] += 1
        elif norm[0].get("final_regulamentar_shadow") is not True:
            motivos["nao_final_regulamentar"] += 1
        elif identidade(norm[0], liga) != k:
            if norm[0]["casa_id"] != k[2] or norm[0]["fora_id"] != k[3]:
                motivos["equipas_id_divergente"] += 1
            else:
                motivos["horario_divergente"] += 1
        else:
            motivos["confirmavel"] += 1
            finais.append(norm[0])
    return len(eventos), finais, motivos


def relatorio_lambda_recuperar(snapshots_path, argumentos="", agora=None, session=None):
    """Pré-visualiza página; execução explícita consulta até seis grupos."""
    agora = agora or datetime.now(timezone.utc)
    if agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError("É necessário um horário com timezone")
    executar, pagina = _args(argumentos)
    if pagina < 1:
        return (
            "🔎 Uso: /lambda_recuperar [N] — pré-visualizar página N sem HTTP\n"
            "🔐 /lambda_recuperar executar N — até 6 consultas públicas ESPN, "
            "apenas resultados SHADOW append-only."
        )
    caminho = Path(snapshots_path)
    if not caminho.is_file():
        return "📭 LAMBDA RECUPERAR — sem snapshots prospetivos no volume."
    destino = caminho.with_name("lambda_prospectivo_resultados.jsonl")
    grupos, rejeitados = _grupos(caminho, agora)
    validos, conflitos = _indices_independentes(destino)
    total_grupos = len(grupos)
    total_paginas = max(1, (total_grupos + TETO_GRUPOS - 1) // TETO_GRUPOS)
    if pagina > total_paginas:
        return (
            f"⚪ Página {pagina} inexistente. "
            f"Há {total_paginas} página(s), com {total_grupos} grupos históricos."
        )
    total_falta = sum(
        1 for _, r in grupos for par in r
        if par not in validos or par in conflitos
    )
    inicio = (pagina - 1) * TETO_GRUPOS
    selecionados = grupos[inicio:inicio + TETO_GRUPOS]
    linhas = [
        "🧪 LAMBDA RECUPERAÇÃO HISTÓRICA — SHADOW",
        f"📚 Grupos dia×liga: {total_grupos} | página {pagina}/{total_paginas}",
        f"⚠️ Registos sem confirmação ESPN exata: {total_falta}",
        f"🛡️ Não há resultados inventados nem alteração de previsões oficiais.",
    ]
    if rejeitados:
        linhas.append("⚪ Registos não elegíveis: " + "; ".join(
            f"{k}={v}" for k, v in sorted(rejeitados.items())))
    por_consultar = []
    for (dia, liga), regs in selecionados:
        falta = [par for par in regs if par not in validos or par in conflitos]
        linhas.append(
            f"• {dia:%Y-%m-%d} {liga}: {len(regs)} snapshots"
            f" | sem ESPN exata {len(falta)}"
        )
        if falta:
            por_consultar.append((dia, liga, falta))

    if not executar:
        linhas.extend([
            "",
            f"🔎 Esta página exigiria {len(por_consultar)} consultas públicas ESPN.",
            "🔒 PRÉ-VISUALIZAÇÃO: zero HTTP, zero escrita.",
            f"ℹ️ Para executar APENAS esta página: /lambda_recuperar executar {pagina}",
            "ℹ️ Resultados históricos não obtidos não serão substituídos por nomes ou placares prováveis.",
        ])
        return "\n".join(linhas)

    # Ação explícita OWNER — restrita a scoreboard diário e ligas do whitelist.
    cliente = session or requests.Session()
    historicos = defaultdict(list)
    atualizados = Counter()
    erros = []
    for dia, liga, falta in por_consultar:
        try:
            resposta = cliente.get(
                f"{EstatisticasESPN.BASE}/{liga}/scoreboard",
                params={"dates": dia.strftime("%Y%m%d"), "limit": 500},
                timeout=(5, 25),
            )
            resposta.raise_for_status()
            n_eventos, finais, motivos = _eventos_finais(
                resposta.json(), liga, falta
            )
            historicos[liga].extend(finais)
            atualizados.update(motivos)
            linhas.append(
                f"🔬 {dia:%d/%m} {liga}: ESPN {n_eventos} eventos"
                f" | identidades finais exatas {motivos['confirmavel']}"
                f" | IDs ausentes {motivos['id_ausente']}"
                f" | horários ≠ {motivos['horario_divergente']}"
                f" | equipas ≠ {motivos['equipas_id_divergente']}"
                f" | não normalizados {motivos['nao_normalizado']}"
                f" | sem final regular {motivos['nao_final_regulamentar']}"
                f" | duplicados/ambíguos {motivos['id_ambiguo']}"
            )
        except (requests.RequestException, TypeError, ValueError, KeyError, OverflowError):
            erros.append(f"{dia:%Y-%m-%d} {liga}")
    # Append-only, idempotente e já protegido no módulo histórico: apenas
    # status final regulamentar, IDs/equipas/horário e captura antes do jogo.
    novos = guardar_resultados(caminho, destino, historicos) if historicos else 0
    linhas.extend([
        "",
        f"🌐 Consultas ESPN efetuadas: {len(por_consultar)}"
        f" | grupos falhados: {len(erros)}",
        f"✅ Novos resultados SHADOW guardados: {novos}",
        f"🔍 Total de alvos com identidade final exata nesta página: {atualizados['confirmavel']}",
    ])
    if erros:
        linhas.append("⚠️ Grupos indisponíveis: " + "; ".join(erros[:TETO_GRUPOS]))
    linhas.extend([
        "⚠️ Uma ausência pode ser falta do evento, diferente kickoff, estado final",
        "   não reconhecido ou indisponibilidade da ESPN. Sem correspondência exata: NÃO gravar.",
        "🔒 Zero consultas OddsPapi/Betano. Somente resultados independentes"
        " append-only. V1.2, V1.3, coorte, preços, ROI e CLV intactos.",
    ])
    return "\n".join(linhas)
