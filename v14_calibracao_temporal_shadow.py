"""V1.4 SHADOW: calibração temporal e qualidade de odds (apenas leitura).

A coorte de análise é a PRIMEIRA vintena de snapshots V1.2 de cada dia,
igual à vitrine OWNER. O treino usa somente resultados de datas anteriores ao
corte. O teste nunca é usado para estimar correções. Não altera modelos,
probabilidades, snapshots, coortes comerciais, odds, CLV nem o gate V1.3.
Não consulta fornecedores nem fornece recomendações executáveis.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from math import isfinite, log
from zoneinfo import ZoneInfo

from auditoria_confianca_v12_shadow import _primeiras_vinte_por_dia, _faixa

PT = ZoneInfo("Europe/Lisbon")
MIN_TREINO = 150
MIN_TESTE = 60
MIN_DIAS_TREINO = 15
MIN_DIAS_TESTE = 7
MIN_SEG_TREINO = 35
MIN_DIAS_SEG_TREINO = 8
SHRINK_N = 100
MAX_CORRECAO = 0.15
MIN_SEG_TESTE = 15


def _numero(valor):
    if isinstance(valor, bool):
        return None
    try:
        n = float(valor)
    except (ValueError, TypeError, OverflowError):
        return None
    return n if isfinite(n) else None


def _prob(valor):
    n = _numero(valor)
    return n if n is not None and 0 < n < 1 else None


def _odd(valor):
    n = _numero(valor)
    return n if n is not None and 1 < n < 1000 else None


def _pt(n, casas=1):
    return f"{n:.{casas}f}".replace(".", ",")


def _clamp(n, low, high):
    return max(low, min(high, n))


def _tipo_mercado(nome):
    m = str(nome or "").casefold()
    if "ambas marcam" in m or "btts" in m:
        return "Ambas Marcam"
    if "under " in m or "menos de" in m:
        return "Under"
    if "over " in m or "mais de" in m:
        return "Over"
    if "vitória casa" in m or "vitoria casa" in m:
        return "Vitória Casa"
    if "vitória fora" in m or "vitoria fora" in m:
        return "Vitória Fora"
    if "dupla hipótese" in m or "dupla hipotese" in m:
        return "Dupla Hipótese"
    return "Outro"


def _amostras(dados):
    """Retém somente resultados coerentes, sem permitir bool ou alterações."""
    if not isinstance(dados, dict) or not isinstance(dados.get("previsoes"), list):
        raise ValueError("Snapshots inválidos")
    selecionadas = _primeiras_vinte_por_dia(dados["previsoes"])
    validas = []
    pendentes = inconsistencias = 0
    for p in selecionadas:
        try:
            d = str(p.get("data_jogo") or "")
            if date.fromisoformat(d).isoformat() != d:
                inconsistencias += 1
                continue
        except (ValueError, TypeError):
            inconsistencias += 1
            continue
        y = p.get("resultado_binario")
        if y is None:
            pendentes += 1
            continue
        prob = _prob(p.get("probabilidade"))
        if (type(y) is not int or y not in (0, 1)
                or prob is None
                or p.get("estado") != ("ganhou" if y == 1 else "perdeu")):
            inconsistencias += 1
            continue
        validas.append({
            "data": d, "p": prob, "y": y,
            "mercado": _tipo_mercado(p.get("mercado")),
            "liga": str(p.get("liga") or "Liga não registada").strip()[:80],
            "confianca": _faixa(p.get("confianca_modelo")),
        })
    return selecionadas, validas, pendentes, inconsistencias


def _dias(rows):
    return len({r["data"] for r in rows})


def _metricas(rows, predict=None):
    if not rows:
        return None
    # a mesma escala estritamente própria para comparação entre probabilidades
    # originais e calibradas, no MESMO conjunto de partidas.
    pred = [
        _clamp((predict(r) if predict else r["p"]), 1e-6, 1 - 1e-6)
        for r in rows
    ]
    n = len(rows)
    brier = sum((p - r["y"]) ** 2 for p, r in zip(pred, rows)) / n
    logloss = -sum(
        r["y"] * log(p) + (1 - r["y"]) * log(1 - p)
        for p, r in zip(pred, rows)
    ) / n
    return {
        "n": n, "dias": _dias(rows),
        "prev": sum(pred)/n, "real": sum(r["y"] for r in rows)/n,
        "brier": brier, "logloss": logloss,
    }


def _ajuste_global(treino):
    # Desvio em pp aprendido apenas com jogos anteriores à data do teste.
    delta = sum(r["y"] - r["p"] for r in treino) / len(treino)
    return _clamp(delta, -MAX_CORRECAO, MAX_CORRECAO)


def _ajustes_segmentados(treino, campo, global_delta):
    """Empirical shrinkage: pequenos segmentos ficam próximos do global."""
    grupos = defaultdict(list)
    for r in treino:
        grupos[r[campo]].append(r)
    saida = {}
    for chave, rows in grupos.items():
        n = len(rows)
        if n < MIN_SEG_TREINO or _dias(rows) < MIN_DIAS_SEG_TREINO:
            continue
        delta = sum(r["y"] - r["p"] for r in rows) / n
        peso = n / (n + SHRINK_N)
        saida[chave] = _clamp(
            global_delta + peso * (delta - global_delta),
            -MAX_CORRECAO, MAX_CORRECAO,
        )
    return saida


def _avaliar_temporal(validas):
    datas = sorted({r["data"] for r in validas})
    if len(datas) < MIN_DIAS_TREINO + MIN_DIAS_TESTE:
        return None
    idx = _clamp(int(len(datas) * .70), MIN_DIAS_TREINO, len(datas)-MIN_DIAS_TESTE)
    corte = datas[idx]
    treino = [r for r in validas if r["data"] < corte]
    teste = [r for r in validas if r["data"] >= corte]
    if (len(treino) < MIN_TREINO or len(teste) < MIN_TESTE
            or _dias(treino) < MIN_DIAS_TREINO or _dias(teste) < MIN_DIAS_TESTE):
        return None
    global_delta = _ajuste_global(treino)
    market = _ajustes_segmentados(treino, "mercado", global_delta)
    liga = _ajustes_segmentados(treino, "liga", global_delta)
    predict_global = lambda r: _clamp(r["p"] + global_delta, .01, .99)
    predict_market = lambda r: _clamp(r["p"] + market.get(r["mercado"], global_delta), .01, .99)
    predict_liga = lambda r: _clamp(r["p"] + liga.get(r["liga"], global_delta), .01, .99)
    return {
        "corte": corte, "treino": treino, "teste": teste,
        "delta": global_delta, "market": market, "liga": liga,
        "baseline": _metricas(teste),
        "global": _metricas(teste, predict_global),
        "mercado": _metricas(teste, predict_market),
        "liga_modelo": _metricas(teste, predict_liga),
    }


def _segmentos(rows, campo, max_grupos=5):
    grupos = defaultdict(list)
    for r in rows:
        grupos[r[campo]].append(r)
    linhas = []
    for chave, conjunto in sorted(
        grupos.items(), key=lambda a: (-len(a[1]), a[0])
    )[:max_grupos]:
        m = _metricas(conjunto)
        if m["n"] < MIN_SEG_TESTE:
            linhas.append(f"• {chave}: n={m['n']} — reduzida, sem leitura de desempenho.")
        else:
            linhas.append(
                f"• {chave}: n={m['n']} | Prev. {_pt(m['prev']*100)}%"
                f" → Real {_pt(m['real']*100)}%"
                f" | Δ {_pt((m['real']-m['prev'])*100)}pp"
                f" | Brier {_pt(m['brier'],4)}"
            )
    if len(grupos) > max_grupos:
        linhas.append(f"• +{len(grupos)-max_grupos} grupos não apresentados.")
    return linhas


def _parse_aware(valor):
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        dt = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _auditar_odds(selecionadas):
    """A hora da captura não é prova de preço executável/disponível."""
    cont = Counter()
    faltas_mercado = Counter()
    for p in selecionadas:
        preco = _odd(p.get("odd_valor_confirmado"))
        if preco is None:
            preco = _odd(p.get("odd_real"))
        minima = _odd(p.get("odd_minima"))
        if preco is None:
            cont["sem_odd"] += 1
            faltas_mercado[_tipo_mercado(p.get("mercado"))] += 1
            continue
        cont["com_odd"] += 1
        if minima is None:
            cont["sem_minima"] += 1
        elif str(p.get("valor_estado") or "") == "expirado":
            cont["expiradas"] += 1
        elif preco >= minima:
            cont["acima_minima_historico"] += 1
        else:
            cont["abaixo_minima"] += 1
        captura = _parse_aware(p.get("odds_capturada_em") or p.get("valor_confirmado_em"))
        inicio = _numero(p.get("timestamp_jogo"))
        if captura is None or inicio is None or not 0 < inicio < 3e9:
            cont["hora_desconhecida"] += 1
            continue
        idade = inicio - captura.timestamp()
        if idade <= 0:
            cont["captura_apos_inicio"] += 1
        elif idade <= 2*3600:
            cont["captura_ate_2h"] += 1
        elif idade <= 6*3600:
            cont["captura_2_6h"] += 1
        else:
            cont["captura_mais_6h"] += 1
    return cont, faltas_mercado


def relatorio_v14_calibracao_shadow(dados):
    selecionadas, validas, pendentes, erros = _amostras(dados)
    linhas = [
        "🧪 V1.4 SHADOW — CALIBRAÇÃO TEMPORAL",
        "🔒 V1.2 Top20 de cada dia; a V1.3 comercial não é alterada.",
        f"📚 Previsões: {len(selecionadas)} | Liquidadas válidas: {len(validas)}"
        f" | Pendentes: {pendentes} | Inconsistências: {erros}",
    ]
    avaliacao = _avaliar_temporal(validas)
    if avaliacao is None:
        linhas += [
            "",
            f"⚠️ Sem amostra temporal suficiente: treino ≥{MIN_TREINO} jogos/"
            f"{MIN_DIAS_TREINO} dias, teste ≥{MIN_TESTE} jogos/"
            f"{MIN_DIAS_TESTE} dias.",
            "Nenhum ajuste calculado ou aprovado.",
        ]
    else:
        a = avaliacao
        base = a["baseline"]
        linhas += [
            "",
            f"🧭 Corte temporal: {a['corte']} (sem dividir o mesmo dia).",
            f"📘 Treino: {len(a['treino'])} jogos/{_dias(a['treino'])} dias"
            f" | TESTE posterior: {len(a['teste'])} jogos/{_dias(a['teste'])} dias",
            f"📉 Correção GLOBAL treinada antes do corte: {_pt(a['delta']*100,1)}pp",
            "",
            "📊 COMPARAÇÃO NO MESMO TESTE HISTÓRICO",
            f"• V1.2 original: Brier {_pt(base['brier'],4)}"
            f" | LogLoss {_pt(base['logloss'],4)}",
        ]
        for chave, nome in (("global","Global"), ("mercado","Por mercado"),
                            ("liga_modelo","Por liga")):
            m = a[chave]
            variacao = base["brier"]-m["brier"]
            linhas.append(
                f"• SHADOW {nome}: Brier {_pt(m['brier'],4)}"
                f" | Δ {_pt(variacao,4)} (positivo = melhora)"
                f" | LogLoss {_pt(m['logloss'],4)}"
            )
        linhas += [
            f"📚 Segmentos treinados com amostra mínima: "
            f"{len(a['market'])} mercados, {len(a['liga'])} ligas.",
            "⚠️ Melhor resultado retrospectivo NÃO autoriza alterar produção.",
            "",
            "🎯 TESTE POR MERCADO",
            *_segmentos(a["teste"], "mercado"),
            "",
            "🏆 TESTE POR LIGA (principais)",
            *_segmentos(a["teste"], "liga"),
            "",
            "🧠 TESTE POR CONFIANÇA",
            *_segmentos(a["teste"], "confianca", 5),
        ]
    c, faltas = _auditar_odds(selecionadas)
    linhas += [
        "",
        "💶 AUDITORIA DE ODDS — HISTÓRICO TOP20",
        f"• Com cotação guardada: {c['com_odd']} | Sem cotação: {c['sem_odd']}",
        f"• Acima da mínima registada: {c['acima_minima_historico']}"
        f" | Abaixo: {c['abaixo_minima']} | Expiradas: {c['expiradas']}"
        f" | Sem mínima: {c['sem_minima']}",
        f"• Captura ≤2h antes do jogo: {c['captura_ate_2h']}"
        f" | 2–6h: {c['captura_2_6h']} | >6h: {c['captura_mais_6h']}",
        f"• Hora de captura desconhecida: {c['hora_desconhecida']}"
        f" | não anterior ao início: {c['captura_apos_inicio']}",
    ]
    if faltas:
        linhas.append("• Mercados com mais odds em falta: " + ", ".join(
            f"{nome} ({n})" for nome, n in faltas.most_common(3)
        ))
    linhas.extend([
        "",
        "ℹ️ Carimbo de captura e preço guardado NÃO confirmam disponibilidade atual ou correspondência independente do fixture.",
        "⚠️ Teste histórico com escolhas de modelos vistas após liquidação: requer validação prospectiva independente.",
        "🔒 Sem novas APIs, sem escrita, sem alterar snapshots, odds, ROI, CLV, V1.2, V1.3 ou gate.",
    ])
    return "\n".join(linhas)
