"""Painel /odds_falhas [RANKING] — auditoria passiva por jogo V1.2.

Lê somente snapshots e rastreio_odds.jsonl previamente guardados. Zero HTTP,
zero gravação, sem efeitos sobre odds, picks, SEL1 ou V1.3.
"""
from collections import Counter
from datetime import datetime, timezone
import json
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo


TZ_PT = ZoneInfo("Europe/Lisbon")
MAX_JOGOS = 20
MAX_RASTREIO_BYTES = 20 * 1024 * 1024
TOLERANCIA_TS = 90 * 60

# Explicações conservadoras: um evento omitido ou erro HTTP NÃO prova ausência
# de odds nem de oferta comercial Betano.
DIAGNOSTICOS = {
    "evento_nao_encontrado": ("identificação", "jogo não encontrado na lista consultada"),
    "evento_ambiguo": ("identificação", "mais de um jogo compatível; não foi associado"),
    "evento_sem_id": ("identificação", "jogo identificado sem ID utilizável"),
    "horario_recuperacao_nao_validado": ("validação da hora", "hora do jogo recuperado não validada"),
    "odds_payload_evento_divergente": ("validação do evento", "resposta de odds incompatível com o jogo"),
    "fixture_omitido_no_lote": ("resposta de odds", "fixture omitido no lote — inconclusivo"),
    "odds_evento_sem_resposta": ("resposta de odds", "fixture sem resposta — inconclusivo"),
    "odds_evento_indisponiveis": ("resposta de odds", "odds do evento não obtidas — inconclusivo"),
    "betano_sem_odds_no_evento": ("bookmaker", "fornecedor indicou Betano sem odds no evento"),
    "mercado_nao_disponivel": ("mercado", "mercado não encontrado no payload recebido"),
    "linha_ou_selecao_nao_disponivel": ("linha/seleção", "linha ou seleção não encontrada no payload"),
    "odd_nao_extraida": ("extração", "não foi possível extrair odd validada"),
    "probabilidade_invalida": ("validação local", "probabilidade local inválida"),
    "odds_quota_esgotada": ("quota", "fornecedor indicou quota esgotada"),
    "odds_rate_limit_429": ("fornecedor", "limite temporário HTTP 429"),
    "odds_timeout": ("fornecedor", "timeout na consulta"),
    "odds_ligacao_indisponivel": ("fornecedor", "ligação indisponível"),
    "odds_rede_indisponivel": ("fornecedor", "rede indisponível"),
}
ALERTAS = {
    "horario_divergente": "divergência de horário sinalizada",
    "competicao_divergente": "divergência de competição sinalizada",
}


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        v = float(valor)
        return v if isfinite(v) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _data_pt(ts):
    v = _numero(ts)
    if v is None:
        return None
    try:
        return datetime.fromtimestamp(v, timezone.utc).astimezone(TZ_PT).date().isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def _hora_pt(ts):
    v = _numero(ts)
    if v is None:
        return "--:--"
    try:
        return datetime.fromtimestamp(v, timezone.utc).astimezone(TZ_PT).strftime("%H:%M")
    except (ValueError, OverflowError, OSError):
        return "--:--"


def _valor_odd(v):
    n = _numero(v)
    return n if n is not None and n > 1 else None


def _fmt(v):
    return f"{v:.2f}".replace(".", ",")


def _diag(codigo):
    codigo = str(codigo or "")[:64]
    if codigo in DIAGNOSTICOS:
        return DIAGNOSTICOS[codigo]
    if codigo.startswith("odds_http_") and codigo[10:].isdigit():
        return "fornecedor", f"erro HTTP {codigo[10:]} — inconclusivo"
    if codigo:
        return "indeterminado", "diagnóstico técnico não classificado — inconclusivo"
    return "sem diagnóstico", "não existe diagnóstico detalhado neste registo"


def _snapshot_historico(p):
    odd = _valor_odd(p.get("odd_real"))
    fonte = str(p.get("odds_fonte") or "").casefold()
    return odd if odd is not None and "oddspapi" in fonte else None


def _observacoes(path, data_hoje):
    if path is None:
        return [], "Ficheiro de rastreio não configurado."
    path = Path(path)
    if path.is_symlink():
        return [], "Rastreio local inseguro; leitura suspensa."
    if not path.exists():
        return [], "Ainda não existe rastreio detalhado neste volume."
    if not path.is_file() or path.stat().st_size > MAX_RASTREIO_BYTES:
        return [], "Rastreio indisponível ou superior ao limite de segurança."
    obs = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for linha in f:
                if not linha.strip():
                    continue
                item = json.loads(linha)
                if not isinstance(item, dict):
                    raise ValueError("Registo inválido")
                if _data_pt(item.get("timestamp_jogo")) == data_hoje:
                    obs.append(item)
    except (OSError, UnicodeError, ValueError, TypeError):
        return [], "Rastreio local ilegível; não foram usados registos parciais."
    return obs, None


def _associados(p, obs):
    # Exigir ID, mercado, nomes das duas equipas e hora na janela de 90 minutos.
    # Não pesquisar alternativas por nomes; IDs de fontes distintas podem colidir.
    event_id = str(p.get("event_id") or "").strip()
    mercado = str(p.get("mercado") or "")
    ts = _numero(p.get("timestamp_jogo"))
    casa = str(p.get("casa") or "").strip().casefold()
    fora = str(p.get("fora") or "").strip().casefold()
    if not event_id or not mercado or ts is None or not casa or not fora:
        return []
    nome = f"{casa} vs {fora}"
    encontrados = []
    for item in obs:
        rt = _numero(item.get("timestamp_jogo"))
        if (
            str(item.get("event_id_modelo") or "").strip() == event_id
            and str(item.get("mercado_modelo") or "") == mercado
            and rt is not None and abs(rt - ts) <= TOLERANCIA_TS
            and str(item.get("jogo") or "").strip().casefold() == nome
        ):
            encontrados.append(item)
    # As observações são append-only; o último registo do ficheiro é o último
    # gravado, mesmo quando um timestamp escrito pelo fornecedor é inválido.
    return encontrados


def _resumo(p, observacoes):
    registos = _associados(p, observacoes)
    ultimo = registos[-1] if registos else None
    historica = _snapshot_historico(p)
    odds_rastreio = [
        v for r in registos if (v := _valor_odd(r.get("odd_observada"))) is not None
    ]
    if ultimo is None:
        situacao = "sem rastreio detalhado associado"
    elif str(ultimo.get("diagnostico") or ""):
        _, situacao = _diag(ultimo.get("diagnostico"))
    elif _valor_odd(ultimo.get("odd_observada")) is not None:
        situacao = "odd observada no rastreio"
    else:
        situacao = "sem classificação conclusiva"
    return registos, historica, odds_rastreio, situacao


def gerar_painel_falhas(previsoes, path, argumento="", agora=None):
    """Devolve lista de hoje ou detalhe de ranking; nunca escreve no disco."""
    agora = agora or datetime.now(TZ_PT)
    data_hoje = agora.astimezone(TZ_PT).date().isoformat()
    dia = agora.astimezone(TZ_PT).strftime("%d/%m/%Y")
    hoje = [
        p for p in previsoes or []
        if isinstance(p, dict) and p.get("data_jogo") == data_hoje
        and str(p.get("modelo_versao") or "") == "V1.2"
        and isinstance(p.get("ranking_modelo"), int)
        and not isinstance(p.get("ranking_modelo"), bool)
        and p.get("ranking_modelo") > 0
    ]
    hoje.sort(key=lambda p: (p["ranking_modelo"], str(p.get("chave") or "")))
    titulo = f"🔎 FALHAS DE ODDS POR JOGO — SHADOW | {dia}"
    if not hoje:
        return titulo + "\n⚪ Não existem previsões V1.2 de hoje para cruzar. Zero consultas externas."
    obs, aviso = _observacoes(path, data_hoje)
    if aviso and ("ilegível" in aviso or "inseguro" in aviso or "limite" in aviso):
        return titulo + f"\n⚪ {aviso}\n🔒 Nenhuma alteração efetuada."

    arg = str(argumento or "").strip()
    if arg and (not arg.isascii() or not arg.isdecimal()):
        return "Formato: /odds_falhas ou /odds_falhas 1 (ranking do dia)."

    if not arg:
        linhas = [titulo, "📚 Snapshots e rastreio já existentes — zero OddsPapi", ""]
        for p in hoje[:MAX_JOGOS]:
            rank = p["ranking_modelo"]
            regs, hist, quotes, situacao = _resumo(p, obs)
            nome = f"{p.get('casa') or '?'} vs {p.get('fora') or '?'}"[:125]
            marcador = "✅" if hist is not None else ("📍" if quotes else "⚪")
            linhas.append(f"{marcador} #{rank} · {_hora_pt(p.get('timestamp_jogo'))} · {nome}")
            linhas.append(f"    {str(p.get('mercado') or '?')[:60]} | {situacao[:105]}")
        if len(hoje) > MAX_JOGOS:
            linhas.append(f"… mais {len(hoje) - MAX_JOGOS} previsões não apresentadas.")
        linhas.extend([
            "", "Detalhe: /odds_falhas 1 (substitui pelo ranking).",
            "✅ Odd confirmada no snapshot | 📍 observada só no rastreio | ⚪ sem confirmação no snapshot.",
        ])
        if aviso:
            linhas.append(f"⚠️ {aviso}")
        linhas.extend([
            "⚠️ Sem registo não significa Betano sem cobertura.",
            "🔒 Sem novas consultas, decisões de VALUE, exclusões ou alterações aos snapshots.",
        ])
        return "\n".join(linhas)

    rank = int(arg)
    candidatos = [p for p in hoje if p["ranking_modelo"] == rank]
    if len(candidatos) != 1:
        return "⚪ Ranking inexistente ou repetido. Usa /odds_falhas."

    p = candidatos[0]
    regs, hist, quotes, situacao = _resumo(p, obs)
    odd_min = _valor_odd(p.get("odd_minima"))
    nome = f"{p.get('casa') or '?'} vs {p.get('fora') or '?'}"
    linhas = [
        titulo, f"⚽ #{rank} · {nome}",
        f"🏆 {p.get('liga') or 'Competição não registada'} | {_hora_pt(p.get('timestamp_jogo'))}",
        f"🎯 {p.get('mercado') or 'Mercado não identificado'}",
        "", "📌 COTAÇÃO ORIGINAL CONGELADA",
    ]
    if hist is None:
        linhas.append("• Odd OddsPapi/Betano inicial: sem confirmação no snapshot.")
    else:
        linhas.append(f"• Odd OddsPapi/Betano inicial: {_fmt(hist)} (histórica).")
    if odd_min is None:
        linhas.append("• Mínimo congelado: indisponível.")
    elif hist is None:
        linhas.append(f"• Mínimo congelado: {_fmt(odd_min)}; sem odd inicial para comparar.")
    elif hist < odd_min:
        linhas.append(f"🔴 Odd inicial {_fmt(hist)} abaixo do mínimo {_fmt(odd_min)}.")
    else:
        linhas.append(f"🟡 Odd inicial {_fmt(hist)} atingiu o mínimo {_fmt(odd_min)}; não comprova VALUE.")

    linhas.extend(["", "🧪 RASTREIO PASSIVO DA FONTE"])
    if not regs:
        linhas.append("⚪ Sem observações detalhadas associadas ao mesmo ID/mercado/equipas/hora.")
        if aviso:
            linhas.append(f"⚠️ {aviso}")
    else:
        linhas.append(f"• Registos observados: {len(regs)} (não são pedidos distintos à API).")
        linhas.append(f"• Último diagnóstico: {situacao}.")
        ultimo = regs[-1]
        codigo = str(ultimo.get("diagnostico") or "")
        fase, _ = _diag(codigo)
        if codigo:
            linhas.append(f"• Etapa: {fase}.")
        if quotes:
            linhas.append(f"• Odd observada em rastreio: {_fmt(quotes[-1])} (histórica, não cotação atual).")
        fixture = str(ultimo.get("fixture_id_fonte") or "")[:64]
        if fixture:
            linhas.append(f"• Fixture identificado na fonte: {fixture}.")
        else:
            linhas.append("• ID de fixture na fonte: não guardado neste registo.")
        mercado = str(ultimo.get("mercado_id_fonte") or "")[:64]
        selecao = str(ultimo.get("outcome_ref_fonte") or "")[:64]
        if mercado and selecao:
            linhas.append(f"• Mercado fonte: {mercado} | seleção fonte: {selecao}.")
        else:
            linhas.append("• IDs de mercado/seleção: sem confirmação neste registo.")
        alertas = [
            ALERTAS[a] for a in (ultimo.get("alertas_contexto") or [])
            if isinstance(a, str) and a in ALERTAS
        ]
        for alerta in sorted(set(alertas))[:3]:
            linhas.append(f"⚠️ {alerta}.")
        motivos = Counter(
            _diag(r.get("diagnostico"))[0]
            for r in regs if r.get("diagnostico")
        )
        if motivos:
            linhas.append("• Etapas com diagnóstico observado: " +
                          ", ".join(f"{v}× {k}" for k, v in motivos.most_common(5)))
    linhas.extend([
        "", "⚠️ Diagnósticos são observações do fornecedor; HTTP/fixture omitido",
        "não provam indisponibilidade de odds na Betano.",
        "⚠️ Sem rastreio anterior não é possível reconstituir a causa histórica.",
        "🔒 Leitura local apenas. Zero OddsPapi, sem VALUE novo nem alterações à V1.2/SEL1/V1.3.",
    ])
    return "\n".join(linhas)
