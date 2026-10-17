"""Auditoria SHADOW de consistencia das previsoes do dia.

Apenas leitura dos snapshots congelados. Nunca consulta APIs, atribui
novas probabilidades, altera resultados, reordena a V1.2 ou a coorte V1.3.
Rankings duplicados entre rondas sao observacoes, nao falhas de integridade.
"""
from collections import Counter, defaultdict
from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo

TZ_PT = ZoneInfo("Europe/Lisbon")
LIMIAR_EV = 0.25
LIMIAR_DESVIO = 0.25


def _numero(valor):
    if isinstance(valor, bool):
        return None
    try:
        n = float(valor)
    except (ValueError, TypeError, OverflowError):
        return None
    return n if isfinite(n) else None


def _odd(valor):
    n = _numero(valor)
    return n if n is not None and 1 < n < 1000 else None


def _ranking(valor):
    if isinstance(valor, bool):
        return None
    try:
        n = int(valor)
    except (ValueError, TypeError, OverflowError):
        return None
    return n if n > 0 else None


def relatorio_consistencia(previsoes, agora=None):
    """Devolve o resumo do dia, usando somente dados guardados no disco.

    O maximo 20 da V1.2 e por execucao. Snapshots de rondas diferentes
    podem ocupar o mesmo ranking, sem permitir renumeracao retroativa.
    """
    agora = agora or datetime.now(TZ_PT)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=TZ_PT)
    agora_pt = agora.astimezone(TZ_PT)
    dia = agora_pt.date().isoformat()
    ts_agora = agora_pt.timestamp()
    items = [
        p for p in (previsoes or [])
        if isinstance(p, dict) and p.get("data_jogo") == dia
    ]
    linhas = [
        "🛡️ CONSISTÊNCIA DE SELEÇÕES — SHADOW",
        f"📅 {agora_pt.strftime('%d/%m/%Y')} | hora de Portugal",
        "🔒 Auditoria passiva dos snapshots do dia, sem pedidos a APIs.",
        "",
        f"📚 Snapshots acumulados: {len(items)}",
        "🧠 Limite V1.2: até 20 seleções POR execução, não por dia.",
    ]
    if not items:
        linhas.extend([
            "⚪ Ainda sem previsões registadas para hoje.",
            "ℹ️ Não significa que a agenda desportiva esteja vazia.",
        ])
        return "\n".join(linhas)

    ranks = Counter()
    chaves = Counter()
    jogos_mercados = defaultdict(set)
    futuros = iniciados = sem_hora = com_odd = sem_odd = abaixo = value = 0
    suspeitas = []

    for p in items:
        rank = _ranking(p.get("ranking_modelo"))
        if rank is not None:
            ranks[rank] += 1

        eid = p.get("event_id")
        mercado = str(p.get("mercado") or "")
        if eid is not None and mercado:
            chaves[(str(eid), mercado)] += 1
            jogos_mercados[str(eid)].add(mercado)

        ts = _numero(p.get("timestamp_jogo"))
        if ts is None:
            sem_hora += 1
        elif ts <= ts_agora:
            iniciados += 1
        else:
            futuros += 1

        odd = _odd(p.get("odd_valor_confirmado"))
        if odd is None:
            odd = _odd(p.get("odd_real"))
        minima = _odd(p.get("odd_minima"))
        prob = _numero(p.get("probabilidade"))

        if odd is None:
            sem_odd += 1
        else:
            com_odd += 1
            if minima is not None and odd < minima:
                abaixo += 1
            elif minima is not None and odd >= minima:
                value += 1

            if (
                minima is not None
                and prob is not None and 0 < prob <= 1
                and odd >= minima
            ):
                ev = prob * odd - 1.0
                desvio = odd / minima - 1.0
                if ev >= LIMIAR_EV or desvio >= LIMIAR_DESVIO:
                    suspeitas.append({
                        "rank": rank, "casa": p.get("casa") or "?",
                        "fora": p.get("fora") or "?",
                        "mercado": mercado or "?",
                        "odd": odd, "ev": ev,
                        "event_id": str(eid or ""),
                    })

    ranks_repetidos = [(rank, qty) for rank, qty in sorted(ranks.items()) if qty > 1]
    chaves_repetidas = [(key, qty) for key, qty in chaves.items() if qty > 1]
    eventos_multimercado = sum(len(mercados) > 1 for mercados in jogos_mercados.values())
    linhas.extend([
        f"🕒 Por começar: {futuros} | Já iniciados: {iniciados} | Sem hora fiável: {sem_hora}",
        f"💶 Com odd registada: {com_odd} | Sem odd: {sem_odd}",
        f"🟢 Preço ≥ mínimo: {value} | 🔴 Abaixo do mínimo: {abaixo}",
        "",
        "🔎 IDENTIDADE E RANKING",
        f"• Rankings repetidos entre snapshots: {len(ranks_repetidos)}",
        f"• Chaves evento + mercado repetidas: {len(chaves_repetidas)}",
        f"• Eventos com mercados diferentes: {eventos_multimercado}",
    ])

    if ranks_repetidos:
        texto_ranks = ", ".join(f"#{r} ({n}x)" for r, n in ranks_repetidos[:12])
        linhas.append(f"↳ {texto_ranks}")
        linhas.append("ℹ️ Ranking repetido pode resultar de reanálises; não prova previsão duplicada.")
    if chaves_repetidas:
        linhas.append("⚠️ A mesma chave evento+mercado aparece mais de uma vez; investigar sem apagar snapshots.")
        for (event_id, mercado), count in sorted(chaves_repetidas)[:3]:
            linhas.append(f"↳ evento {event_id} | {mercado} ({count}x)")
    if eventos_multimercado:
        linhas.append("⚠️ Há eventos com mercados distintos em snapshots do dia; verificar sequência temporal.")

    linhas.extend([
        "",
        f"⚠️ ODDS / EV INVULGARES: {len(suspeitas)}",
    ])
    suspeitas.sort(key=lambda x: (-x["ev"], x["event_id"], x["mercado"]))
    for p in suspeitas[:5]:
        label = f"#{p['rank']}" if p["rank"] is not None else "#—"
        linhas.append(
            f"• {label} {p['casa']} vs {p['fora']} | {p['mercado']}"
        )
        linhas.append(f"  @ {p['odd']:.2f} | EV modelo {p['ev']*100:+.1f}%".replace(".", ","))
    if len(suspeitas) > 5:
        linhas.append(f"↳ E mais {len(suspeitas) - 5} alerta(s).")

    linhas.extend([
        "",
        "ℹ️ EV invulgar é sinal de revisão, não prova de odd errada.",
        "ℹ️ O preço ≥ mínimo não demonstra rentabilidade; odds são históricas.",
        "🔒 Zero alterações à V1.2, SEL1, V1.3, snapshots, odds e CLV.",
    ])
    return "\n".join(linhas)
