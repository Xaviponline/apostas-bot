"""Auditoria descritiva das 20 previsões V1.2/dia por confiança original.

Só leitura dos snapshots e resultados liquidados. Sem consultas externas, sem
ajustes de modelos e sem utilizar a coorte comercial V1.3 como base.
"""
from collections import defaultdict
from datetime import datetime
from math import isfinite, sqrt
from zoneinfo import ZoneInfo
import unicodedata

from alertas_prejogo import AlertasPreJogo

PT = ZoneInfo("Europe/Lisbon")
FAIXAS = (
    ("ALTA", "🟢 ALTA"),
    ("MÉDIA-ALTA", "🟡 MÉDIA-ALTA"),
    ("MÉDIA", "🟠 MÉDIA"),
    ("BAIXA", "🔴 BAIXA"),
    ("DESCONHECIDA", "⚪ NÃO CLASSIFICADA"),
)
MIN_N_EXPLORATORIO = 30
MIN_DIAS_EXPLORATORIO = 10


def _numero(valor):
    if isinstance(valor, bool):
        return None
    try:
        n = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if isfinite(n) else None


def _faixa(valor):
    if not isinstance(valor, str):
        return "DESCONHECIDA"
    normalizado = unicodedata.normalize("NFC", valor).strip().upper()
    normalizado = " ".join(normalizado.split()).replace(" - ", "-")
    normalizado = normalizado.replace("MEDIA", "MÉDIA")
    return normalizado if normalizado in dict(FAIXAS) else "DESCONHECIDA"


def _primeiras_vinte_por_dia(registos):
    """A mesma definição de coorte diária dos alertas OWNER, incluindo jogos findos."""
    datas = sorted({
        p.get("data_jogo")
        for p in (registos or [])
        if isinstance(p, dict) and isinstance(p.get("data_jogo"), str)
        and p.get("modelo_versao") == "V1.2"
    })
    resultado = []
    for dia in datas:
        try:
            instante = datetime.fromisoformat(dia)
            if instante.date().isoformat() != dia:
                continue
            instante = instante.replace(tzinfo=PT)
        except (ValueError, TypeError, OverflowError):
            continue
        resultado.extend(p for _, _, _, p in AlertasPreJogo._selecoes_do_dia(registos, instante))
    return resultado


def _resumo(amostras):
    n = len(amostras)
    if n == 0:
        return None
    pmedia = sum(p for p, _, _ in amostras) / n
    real = sum(y for _, y, _ in amostras) / n
    brier = sum((p - y) ** 2 for p, y, _ in amostras) / n
    # Intervalo Wilson 95% da taxa binária; não corrige correlação entre jogos.
    z = 1.96
    centro = (real + z*z/(2*n)) / (1 + z*z/n)
    margem = z * sqrt(real*(1-real)/n + z*z/(4*n*n)) / (1 + z*z/n)
    return {
        "n": n,
        "ganhos": sum(y for _, y, _ in amostras),
        "dias": len({d for _, _, d in amostras}),
        "pmedia": pmedia,
        "real": real,
        "brier": brier,
        "gap_pp": (real - pmedia)*100,
        "ic95": (max(0, centro-margem), min(1, centro+margem)),
    }


def _pt(n, casas=1):
    return f"{n:.{casas}f}".replace(".", ",")


def _linha(rotulo, amostras):
    m = _resumo(amostras)
    if not m:
        return f"{rotulo} · n=0 — sem resultados liquidados."
    linha = (
        f"{rotulo} · n={m['n']} | ✅ {m['ganhos']}"
        f" | Prev. {_pt(m['pmedia']*100)}% → Real {_pt(m['real']*100)}%"
        f" | Δ {_pt(m['gap_pp'],1)}pp | Brier {_pt(m['brier'],4)}"
    )
    if m["n"] < MIN_N_EXPLORATORIO or m["dias"] < MIN_DIAS_EXPLORATORIO:
        linha += f"\n   ⚠️ Amostra reduzida ({m['n']} jogos/{m['dias']} dias); não concluir que esta faixa é superior."
    else:
        linha += (
            f"\n   IC95% acerto {_pt(m['ic95'][0]*100)}–"
            f"{_pt(m['ic95'][1]*100)}% (descritivo)"
        )
    return linha


def relatorio_confianca_modelo(dados):
    """Auditar coorte histórica V1.2/Top20, sem depender de odds ou de APIs."""
    if not isinstance(dados, dict) or not isinstance(dados.get("previsoes"), list):
        raise ValueError("Histórico de previsões inválido")
    originais = dados["previsoes"]
    selecionadas = _primeiras_vinte_por_dia(originais)
    grupos = defaultdict(list)
    pendentes = defaultdict(int)
    invalidas = 0
    dias_registados = set()
    for p in selecionadas:
        dia = p["data_jogo"]
        dias_registados.add(dia)
        faixa = _faixa(p.get("confianca_modelo"))
        y = p.get("resultado_binario")
        if y is None:
            pendentes[faixa] += 1
            continue
        prob = _numero(p.get("probabilidade"))
        if (type(y) is not int or y not in (0, 1)
                or prob is None or not 0 < prob < 1
                or p.get("estado") != ("ganhou" if y else "perdeu")):
            invalidas += 1
            continue
        grupos[faixa].append((prob, y, dia))

    tudo = [item for k in dict(FAIXAS) for item in grupos[k]]
    liquidadas = len(tudo)
    n_pend = sum(pendentes.values())
    linhas = [
        "🧪 CONFIANÇA DO MODELO — AUDITORIA V1.2",
        "📚 Primeiras 20 previsões distintas de cada dia (sem filtro VALUE).",
        f"📅 Dias com previsões: {len(dias_registados)}"
        + (f" · {min(dias_registados)} a {max(dias_registados)}" if dias_registados else ""),
        f"🧾 Seleções: {len(selecionadas)} | Liquidadas válidas: {liquidadas}"
        f" | Pendentes: {n_pend} | Inconsistências: {invalidas}",
        "",
        _linha("🎯 GLOBAL", tudo),
        "",
        "📊 COMPARAÇÃO POR NÍVEL DE CONFIANÇA",
    ]
    for nome, rotulo in FAIXAS:
        if not grupos[nome] and not pendentes[nome]:
            continue
        linhas.append(_linha(rotulo, grupos[nome]))
        if pendentes[nome]:
            linhas.append(f"   ⏳ Por liquidar: {pendentes[nome]}")
    if not selecionadas:
        linhas.append("⚪ Ainda sem previsões válidas para esta auditoria.")
    linhas.extend([
        "",
        "ℹ️ Prev. = probabilidade média do modelo; Real = acertos observados.",
        "ℹ️ A confiança é um rótulo original, não uma taxa de acerto garantida.",
        "⚠️ Grupos podem ter ligas/mercados diferentes; IC95% não considera dependência entre jogos.",
        "🔒 Não mede rentabilidade nem valida V1.3; zero HTTP, zero escrita e nenhuma promoção automática.",
    ])
    return "\n".join(linhas)
