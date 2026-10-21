"""Auditoria OWNER da identidade de fixtures — apenas leitura de dados existentes.

Cruza snapshots V1.2 com odds_rastreio.jsonl por ID original, mercado, equipas e
hora congelada. Divergencias sao avisos, nao prova de erro ou novas regras VALUE.
Zero HTTP, zero escrita, sem modificar a selecao ou a coorte prospetiva.
"""
from collections import Counter
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo
import json

TZ_PT = ZoneInfo("Europe/Lisbon")
MAX_BYTES = 20 * 1024 * 1024
MAX_DETALHES = 8
TOLERANCIA_ASSOCIACAO = 1.0
TOLERANCIA_HORARIO = 90 * 60

# Alias observados no mesmo torneio, apenas para leitura do relatorio.
# NUNCA alteram a descoberta de fixtures, as odds ou os snapshots.
ALIASES_LIGA = {
    frozenset(("portuguese primeira liga", "liga portugal")),
    frozenset(("argentine liga profesional", "primera lpf")),
    frozenset(("keuken kampioen divisie", "eerste divisie")),
}


def _nome_liga(nome):
    return " ".join(str(nome or "").strip().casefold().split())


def _mesma_liga_por_alias(modelo, fonte):
    nomes = {_nome_liga(modelo), _nome_liga(fonte)}
    return len(nomes) == 2 and frozenset(nomes) in ALIASES_LIGA


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
        return numero if isfinite(numero) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _timestamp_fonte(valor):
    """Uma hora sem fuso explicito nao basta para provar divergencia."""
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        dt = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt.timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


def _chave(item, rastreio=False):
    if rastreio:
        ident = str(item.get("event_id_modelo") or "").strip()
        mercado = str(item.get("mercado_modelo") or "").strip()
        nome = str(item.get("jogo") or "").strip().casefold()
        ts = _numero(item.get("timestamp_jogo"))
    else:
        ident = str(item.get("event_id") or "").strip()
        mercado = str(item.get("mercado") or "").strip()
        nome = f"{item.get('casa') or '?'} vs {item.get('fora') or '?'}".casefold()
        ts = _numero(item.get("timestamp_jogo"))
    if not ident or not mercado or not nome or ts is None:
        return None
    return ident, mercado, nome, ts


def _ler_rastreio(path):
    if path is None:
        return [], "Rastreio local nao configurado."
    path = Path(path)
    if path.is_symlink():
        return [], "Rastreio inseguro (ligacao simbolica); auditoria suspensa."
    if not path.exists():
        return [], "Rastreio ainda nao encontrado neste volume."
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        return [], "Rastreio indisponivel ou maior que 20 MB; auditoria suspensa."
    try:
        itens = []
        with path.open("r", encoding="utf-8") as fich:
            for linha in fich:
                if not linha.strip():
                    continue
                item = json.loads(linha)
                if not isinstance(item, dict):
                    raise ValueError("Registo invalido")
                itens.append(item)
        return itens, None
    except (OSError, UnicodeError, ValueError, TypeError):
        return [], "Rastreio ilegivel; nao foram utilizadas observacoes parciais."


def _associar(previsoes, rastreio):
    """Nunca associa apenas por nomes, por ranking nem por fixture externo."""
    indice = {}
    for obs in rastreio:
        chave = _chave(obs, rastreio=True)
        if chave is not None:
            indice.setdefault(chave[:3], []).append((chave[3], obs))
    for item in previsoes:
        chave = _chave(item)
        observacoes = []
        if chave:
            observacoes = [
                obs for ts, obs in indice.get(chave[:3], [])
                if abs(ts - chave[3]) <= TOLERANCIA_ASSOCIACAO
            ]
        yield item, observacoes[-1] if observacoes else None


def _sinais(p, obs):
    sinais = set()
    ts = _numero(p.get("timestamp_jogo"))
    if ts is None:
        sinais.add("hora_modelo_invalida")
    else:
        try:
            dia = datetime.fromtimestamp(ts, timezone.utc).astimezone(TZ_PT).date().isoformat()
            if dia != p.get("data_jogo"):
                sinais.add("data_modelo_divergente")
        except (ValueError, OverflowError, OSError):
            sinais.add("hora_modelo_invalida")
    prob = _numero(p.get("probabilidade"))
    if prob is None or not 0 < prob < 1:
        sinais.add("probabilidade_invalida")
    if obs:
        for aviso in obs.get("alertas_contexto") or []:
            if aviso in {"horario_divergente", "competicao_divergente"}:
                sinais.add(aviso)
        fonte_ts = _timestamp_fonte(obs.get("inicio_fonte_fixture"))
        if ts is not None and fonte_ts is not None and abs(ts - fonte_ts) > TOLERANCIA_HORARIO:
            sinais.add("horario_divergente")
    return sinais


def relatorio_auditoria_fixture(previsoes, path, argumento="", agora=None):
    """Relatorio por dia, sem IO de rede ou mutacao dos argumentos."""
    agora = agora or datetime.now(TZ_PT)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=TZ_PT)
    data = agora.astimezone(TZ_PT).date().isoformat()
    arg = str(argumento or "").strip()
    if arg:
        try:
            parsed = datetime.strptime(arg, "%Y-%m-%d").date()
            if parsed.isoformat() != arg:
                raise ValueError("Data nao canonica")
            data = arg
        except ValueError:
            return "Formato: /auditoria_fixture ou /auditoria_fixture AAAA-MM-DD."
    dia = datetime.fromisoformat(data).strftime("%d/%m/%Y")
    snapshots = [
        p for p in (previsoes or [])
        if isinstance(p, dict) and p.get("data_jogo") == data
        and str(p.get("modelo_versao") or "") == "V1.2"
    ]
    linhas = [
        f"🧭 AUDITORIA DE FIXTURES — SHADOW | {dia}",
        "🔒 Apenas snapshots e rastreio local; zero OddsPapi.",
        f"📚 Previsoes V1.2: {len(snapshots)}",
    ]
    if not snapshots:
        return "\n".join(linhas + [
            "⚪ Sem previsoes V1.2 guardadas para esta data.",
            "ℹ️ Isto nao confirma ausencia de jogos.",
        ])

    obs, aviso = _ler_rastreio(path)
    if aviso and ("suspensa" in aviso or "ilegivel" in aviso):
        return "\n".join(linhas + [f"⚠️ {aviso}", "🔒 Nenhum registo modificado."])
    contagem = Counter()
    detalhes = []
    aliases_conhecidos = []
    sem_contexto = []
    for p, ultimo in _associar(snapshots, obs):
        sinais = _sinais(p, ultimo)
        contagem["rastreio" if ultimo else "sem_rastreio"] += 1
        tem_contexto = bool(ultimo and (
            ultimo.get("liga_fonte_fixture") or ultimo.get("inicio_fonte_fixture")
        ))
        if tem_contexto:
            contagem["contexto_fixture"] += 1
        else:
            sem_contexto.append(p)
        # So descrever alias previamente reconhecido quando ambos os nomes
        # constam no rastreio. O alerta original e mantido nos ficheiros.
        if "competicao_divergente" in sinais and ultimo and _mesma_liga_por_alias(
            p.get("liga"), ultimo.get("liga_fonte_fixture")
        ):
            sinais.remove("competicao_divergente")
            aliases_conhecidos.append((p, ultimo))
        for sinal in sinais:
            contagem[sinal] += 1
        if sinais:
            detalhes.append((p, ultimo, sorted(sinais)))
    linhas.extend([
        f"🔎 Com observacao associada: {contagem['rastreio']}/{len(snapshots)}",
        f"🏟️ Com contexto do fixture: {contagem['contexto_fixture']}/{len(snapshots)}",
        f"⚠️ Horario divergente: {contagem['horario_divergente']}",
        f"⚠️ Competicao divergente: {contagem['competicao_divergente']}",
        f"ℹ️ Nomes alternativos conhecidos: {len(aliases_conhecidos)}",
        f"⚪ Sem contexto do fixture: {len(sem_contexto)}",
        f"⚠️ Data do snapshot incoerente: {contagem['data_modelo_divergente']}",
        f"⚠️ Probabilidade/hora invalida: "
        f"{contagem['probabilidade_invalida'] + contagem['hora_modelo_invalida']}",
    ])
    if aviso:
        linhas.append(f"ℹ️ {aviso}")
    if aliases_conhecidos:
        linhas.extend(["", "🏆 DESIGNACOES ALTERNATIVAS (NAO EXCLUIR JOGOS):"])
        for p, ult in aliases_conhecidos[:MAX_DETALHES]:
            linhas.append(
                f"• {str(p.get('casa') or '?')[:48]} vs {str(p.get('fora') or '?')[:48]}: "
                f"{str(p.get('liga') or '?')[:58]} / "
                f"{str(ult.get('liga_fonte_fixture') or '?')[:58]}"
            )
    if sem_contexto:
        linhas.extend(["", "⚪ SEM CONTEXTO EXTERNO REGISTADO:"])
        for p in sem_contexto[:3]:
            linhas.append(
                f"• #{p.get('ranking_modelo') or '—'} "
                f"{str(p.get('casa') or '?')[:48]} vs {str(p.get('fora') or '?')[:48]}"
            )
        linhas.append("ℹ️ Rastreio parcial: a identidade deste fixture nao ficou comprovada.")
    if detalhes:
        linhas.extend(["", "🔬 SINAIS PARA REVISAO (max. 8):"])
        for p, ult, sinais in detalhes[:MAX_DETALHES]:
            rank = p.get("ranking_modelo")
            ranking = f"#{rank}" if isinstance(rank, int) and not isinstance(rank, bool) else "#—"
            nome = f"{p.get('casa') or '?'} vs {p.get('fora') or '?'}"[:105]
            linhas.append(f"• {ranking} {nome}")
            linhas.append("  " + ", ".join(s.replace("_", " ") for s in sinais))
            if ult and ult.get("liga_fonte_fixture"):
                linhas.append(
                    f"  Liga modelo: {str(p.get('liga') or '?')[:65]} | "
                    f"fonte: {str(ult['liga_fonte_fixture'])[:65]}"
                )
        if len(detalhes) > MAX_DETALHES:
            linhas.append(f"↳ +{len(detalhes) - MAX_DETALHES} sinais nao listados.")
    elif sem_contexto:
        linhas.append("⚪ Contexto de fixtures insuficiente: validacao externa incompleta.")
    else:
        linhas.append("✅ Sem divergencias nos metadados observados; identidade externa nao garantida.")

    linhas.extend([
        "",
        "⚠️ Ausencia de rastreio nao prova que o jogo esteja correto ou errado.",
        "⚠️ Nomes de ligas diferentes podem ser apenas designacoes distintas.",
        "⚠️ Isto nao confirma identidade externa nem VALUE na Betano.",
        "🔒 Sem reatribuir fixtures, odds, resultados ou alterar V1.2/SEL1/V1.3.",
    ])
    return "\n".join(linhas)
