"""Consulta forense local por data + identidade textual exata do jogo + mercado.

Nao reescreve historicos nem permite inferir cotacoes em falta. Os nomes e a
data do MODELO sao filtro, nao validacao da identidade no fornecedor.
"""
from collections import Counter
from datetime import date, datetime, timezone
from math import isfinite
from pathlib import Path
import json
import re
import unicodedata
from zoneinfo import ZoneInfo

from odds_rastreio import RastreioOdds

PT = ZoneInfo("Europe/Lisbon")
LIMITE_CARTOES = 5
AJUDA = (
    "🔎 Uso: /odds_rastreio_evento AAAA-MM-DD Casa vs Fora | Mercado\n"
    "Exemplo: /odds_rastreio_evento 2026-10-21 Aston Villa vs Viking FK | Under 3.5 Golos\n"
    "ℹ️ O mercado é opcional. Corresponde a nomes, data e mercado exatos do modelo."
)


def _normalizar(valor):
    if not isinstance(valor, str):
        return ""
    t = unicodedata.normalize("NFKD", valor).casefold()
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _partida(valor):
    if not isinstance(valor, str):
        return None
    # Aceitar somente a ordem casa/fora e o separador de jogo, nunca um nome
    # parcial como "Aston Villa", que mistura diversos adversarios/datas.
    pedacos = re.split(r"\s+(?:vs?\.?|×)\s+", valor.strip(), maxsplit=1, flags=re.IGNORECASE)
    if len(pedacos) != 2:
        return None
    casa, fora = (_normalizar(p) for p in pedacos)
    if not casa or not fora:
        return None
    return casa, fora


def _data_jogo(item):
    valor = item.get("timestamp_jogo")
    if type(valor) not in (int, float):
        return None
    n = float(valor)
    if not isfinite(n) or not 1e8 < n < 3e9:
        return None
    try:
        return datetime.fromtimestamp(n, timezone.utc).astimezone(PT).date().isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def _numero_odd(valor):
    if isinstance(valor, bool):
        return None
    try:
        f = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return f if isfinite(f) and 1 < f < 1000 else None


def _campo(item, chave, limite=75):
    valor = item.get(chave)
    if valor is None or valor == "":
        return "não registado"
    return str(valor).replace("\r", " ").replace("\n", " ")[:limite]


def _ler_argumentos(argumentos):
    texto = str(argumentos or "").strip()
    if not texto or len(texto) > 160 or texto.count("|") > 1:
        return None
    jogo_e_data, separador, mercado = texto.partition("|")
    partes = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s+(.+)", jogo_e_data.strip())
    if not partes:
        return None
    dia, jogo = partes.groups()
    try:
        if date.fromisoformat(dia).isoformat() != dia:
            return None
    except (ValueError, TypeError):
        return None
    par = _partida(jogo)
    if par is None:
        return None
    if separador and (not 3 <= len(mercado.strip()) <= 80 or not _normalizar(mercado)):
        return None
    return dia, jogo.strip(), par, mercado.strip() if separador else None


def relatorio_rastreio_evento(rastreio, argumentos):
    """Pesquisa exclusivamente o JSONL ja existente; nunca pede odds.

    O mercado, se especificado, e comparado com mercado_modelo do registo,
    nao com um mercado inferido do fornecedor.
    """
    parsed = _ler_argumentos(argumentos)
    if parsed is None:
        return AJUDA
    dia, jogo, par, mercado = parsed
    caminho = getattr(rastreio, "path", None)
    if caminho is None:
        return "🔎 RASTREIO EVENTO — ficheiro local não configurado. Zero consultas."
    caminho = Path(caminho)
    if not caminho.exists():
        return "🔎 RASTREIO EVENTO — ainda não existem observações locais. Zero consultas."
    if caminho.is_symlink() or caminho.stat().st_size > RastreioOdds.MAX_BYTES:
        raise RuntimeError("Rastreio não pode ser consultado em segurança")

    por_mercado = Counter()
    total_jogo_data = 0
    sem_data_modelo = 0
    encontrados = []
    m_normalizado = _normalizar(mercado) if mercado else None

    with caminho.open("r", encoding="utf-8") as ficheiro:
        for linha in ficheiro:
            if not linha.strip():
                continue
            item = json.loads(linha)
            if not isinstance(item, dict):
                raise ValueError("Linha de rastreio inválida")
            if _partida(item.get("jogo")) != par:
                continue
            d = _data_jogo(item)
            if d is None:
                sem_data_modelo += 1
                continue
            if d != dia:
                continue
            total_jogo_data += 1
            mercado_item = str(item.get("mercado_modelo") or "").strip()
            por_mercado[mercado_item or "não registado"] += 1
            if m_normalizado is not None and _normalizar(mercado_item) != m_normalizado:
                continue
            encontrados.append(item)
            if len(encontrados) > LIMITE_CARTOES:
                encontrados.pop(0)

    total_filtrado = sum(
        n for k, n in por_mercado.items()
        if m_normalizado is None or _normalizar(k) == m_normalizado
    )
    cabecalho = [
        "🔎 RASTREIO ODDS — JOGO/DATA EXATOS (LOCAL)",
        f"📅 {dia} · ⚽ {jogo}",
        f"🎯 Mercado modelo: {mercado or 'todos'}",
        f"📚 Observações jogo/data: {total_jogo_data}"
        f" | mercado pedido: {total_filtrado}",
        f"🗂️ Mesmo nome mas sem data do jogo no registo: {sem_data_modelo}",
    ]
    if por_mercado:
        cabecalho.append("📋 Mercados observados no jogo: " + "; ".join(
            f"{k} ({v})" for k, v in por_mercado.most_common(6)
        ))
    if not encontrados:
        cabecalho += [
            "",
            ("⚪ Existem registos desta partida, mas nenhum para o mercado exato indicado."
             if total_jogo_data else
             "⚪ Não foram encontrados registos que correspondam simultaneamente ao jogo e à data."),
            "⚠️ Isto não demonstra que o fornecedor não disponibilizou a odd;"
            " também pode significar que o rastreio não a guardou.",
            "🔒 Sem consultas pagas, sem escrita, sem alterar a coorte V1.3.",
        ]
        return "\n".join(cabecalho)

    cabecalho.append(f"🕒 Últimas {len(encontrados)} observações correspondentes (ordem do ficheiro):")
    for item in reversed(encontrados):
        odd = _numero_odd(item.get("odd_observada"))
        cabecalho += [
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🕒 Observado: {rastreio._hora_portugal(item.get('observado_em'))}"
            f" | Odd: {f'{odd:.2f}'.replace('.', ',') if odd is not None else 'não registada'}",
            f"⚽ Mercado modelo: {_campo(item,'mercado_modelo')}"
            f" | Evento modelo ID: {_campo(item,'event_id_modelo')}",
            f"📡 Fonte: {_campo(item,'fonte')}"
            f" | Fixture fornecedor: {_campo(item,'fixture_id_fonte')}",
            f"🏆 Liga modelo: {_campo(item,'liga_modelo')}"
            f" | Liga fornecedor: {_campo(item,'liga_fonte_odds')}",
            f"🔢 Mercado fornecedor: {_campo(item,'mercado_id_fonte')}"
            f" / {_campo(item,'mercado_nome_fonte')}",
            f"📋 Período: {_campo(item,'periodo_fonte')}"
            f" | Linha: {_campo(item,'linha_fonte')}"
            f" | Seleção: {_campo(item,'selecao_nome_fonte')}",
            f"🔗 Ref seleção: {_campo(item,'outcome_ref_fonte')}"
            f" | Associação: {_campo(item,'resultado_associacao')}",
            f"🕘 Início fornecedor: {rastreio._hora_portugal(item.get('inicio_fonte_fixture'))}"
            f" | Última alteração odd: {rastreio._hora_portugal(item.get('odds_atualizada_em'))}",
            f"⚠️ Diagnóstico: {_campo(item,'diagnostico')}",
        ]
    cabecalho += [
        "",
        "ℹ️ Filtro exato = data e nomes CASA/FORA do modelo; NÃO valida por si só o fixture, linha ou cotação do fornecedor.",
        "ℹ️ Campos não registados no histórico não podem ser recuperados.",
        "🔒 Consulta local read-only, sem novos pedidos OddsPapi/Betano ou alterações a V1.2/V1.3/CLV.",
    ]
    return "\n".join(cabecalho)
