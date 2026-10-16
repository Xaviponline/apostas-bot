"""Contexto ESPN para /estudo_jogo N forma, pedido explícito e limitado.

Apenas leitura. Não altera o modelo, snapshots, odds, ranking ou coortes.
Usa no máximo DOIS pedidos públicos ESPN: fixture do dia + resultados recentes.
Rejeita liga, fixture ou hora não verificados. Sem fallback que possa disparar dezenas
de pedidos e sem incorporar resultados posteriores à criação da previsão.
"""
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

import requests

from estatisticas_espn import EstatisticasESPN


TZ_PT = ZoneInfo("Europe/Lisbon")
BASE = EstatisticasESPN.BASE
JANELA_DIAS = 70


def _hora_snapshot(previsao):
    try:
        data = datetime.fromisoformat(str(previsao["criada_em"]).replace("Z", "+00:00"))
        if data.tzinfo is None:
            return None
        return data.timestamp()
    except (KeyError, ValueError, TypeError, OverflowError):
        return None


def _dados_competidores(evento):
    try:
        comp = (evento.get("competitions") or [])[0]
        items = comp["competitors"]
        if not isinstance(items, list) or len(items) != 2:
            return None
        casa = next(x for x in items if x.get("homeAway") == "home")
        fora = next(x for x in items if x.get("homeAway") == "away")
        ids = (int(casa["team"]["id"]), int(fora["team"]["id"]))
        if ids[0] <= 0 or ids[1] <= 0 or ids[0] == ids[1]:
            return None
        return ids
    except (IndexError, KeyError, ValueError, TypeError, StopIteration):
        return None


def _resultados(eventos, liga_codigo, limite_ts):
    por_id = {}
    for evento in eventos:
        resultado = EstatisticasESPN._normalizar_resultado(evento, liga_codigo)
        if (
            resultado is not None
            and resultado["timestamp"] < limite_ts
            and resultado["golos_casa"] >= 0
            and resultado["golos_fora"] >= 0
        ):
            por_id[resultado["id"]] = resultado
    return sorted(por_id.values(), key=lambda x: x["timestamp"], reverse=True)


def _equipa_partidas(resultados, team_id, local=None):
    partidas = []
    for r in resultados:
        if team_id not in (r["casa_id"], r["fora_id"]):
            continue
        em_casa = r["casa_id"] == team_id
        if local == "casa" and not em_casa:
            continue
        if local == "fora" and em_casa:
            continue
        marcado = r["golos_casa"] if em_casa else r["golos_fora"]
        sofrido = r["golos_fora"] if em_casa else r["golos_casa"]
        adversario = r["fora"] if em_casa else r["casa"]
        partidas.append((r, marcado, sofrido, adversario, em_casa))
    return partidas


def _resumo_forma(partidas):
    jogos = partidas[:5]
    if not jogos:
        return "nenhum jogo oficial confirmado no intervalo"
    vit = sum(gf > ga for _, gf, ga, _, _ in jogos)
    emp = sum(gf == ga for _, gf, ga, _, _ in jogos)
    der = len(jogos) - vit - emp
    total_gf = sum(gf for _, gf, ga, _, _ in jogos)
    total_ga = sum(ga for _, gf, ga, _, _ in jogos)
    btts = sum(gf > 0 and ga > 0 for _, gf, ga, _, _ in jogos)
    o25 = sum(gf + ga >= 3 for _, gf, ga, _, _ in jogos)
    return (
        f"{vit}V-{emp}E-{der}D | golos {total_gf}-{total_ga} "
        f"| Over 2.5 {o25}/{len(jogos)} | Ambas Marcam {btts}/{len(jogos)}"
    )


def _lista_resultados(partidas, max_items=5):
    linhas = []
    for partida, gf, ga, adversario, em_casa in partidas[:max_items]:
        dia = datetime.fromtimestamp(partida["timestamp"], TZ_PT).strftime("%d/%m")
        local = "C" if em_casa else "F"
        linhas.append(f"  • {dia} ({local}) vs {adversario}: {gf}-{ga}")
    return linhas


def contexto_espn(previsao, session=None):
    """Relatório factual, sem odds nem reclassificação. Fail-closed."""
    base = "📚 FORMA RECENTE — ESPN (CONTEXTO SHADOW)"
    diagnostico = previsao.get("diagnostico_modelo") or {}
    if not isinstance(diagnostico, dict):
        return base + "\n⚪ Contexto indisponível: diagnóstico do snapshot inválido."
    liga = str(diagnostico.get("liga_codigo") or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,40}", liga):
        return base + "\n⚪ Código ESPN da competição indisponível ou inválido."
    try:
        fixture_id = int(previsao["event_id"])
        ts = float(previsao["timestamp_jogo"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return base + "\n⚪ Identificador ou hora do jogo indisponível."
    ts_criada = _hora_snapshot(previsao)
    if fixture_id <= 0 or ts <= 0 or ts_criada is None or ts_criada >= ts:
        return base + "\n⚪ Sem data de criação pré-jogo verificável; análise suspensa."

    dia = datetime.fromtimestamp(ts, TZ_PT).strftime("%Y%m%d")
    sessao = session or requests.Session()
    url = f"{BASE}/{liga}/scoreboard"
    try:
        r = sessao.get(url, params={"dates": dia, "limit": 500}, timeout=(4, 12))
        r.raise_for_status()
        payload = r.json()
        eventos = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(eventos, list) or len(eventos) >= 500:
            return base + "\n⚪ Calendário ESPN inválido ou truncado."
        correspondentes = [x for x in eventos if isinstance(x, dict) and str(x.get("id")) == str(fixture_id)]
        if len(correspondentes) != 1:
            return base + "\n⚪ Fixture ESPN não confirmado pelo ID; sem associação por nomes."
        fixture = correspondentes[0]
        ids = _dados_competidores(fixture)
        ts_espn = EstatisticasESPN._timestamp(fixture.get("date"))
        if ids is None or ts_espn is None or abs(ts_espn - ts) > 90 * 60:
            return base + "\n⚪ Equipas ou horário do fixture não validados."
        # Exclui conservadoramente todo o dia em que foi gerada a previsão.
        corte = min(ts_criada, ts)
        fim = datetime.fromtimestamp(corte, TZ_PT).date() - timedelta(days=1)
        inicio = fim - timedelta(days=JANELA_DIAS - 1)
        intervalo = f"{inicio:%Y%m%d}-{fim:%Y%m%d}"
        r2 = sessao.get(url, params={"dates": intervalo, "limit": 500}, timeout=(4, 12))
        r2.raise_for_status()
        payload2 = r2.json()
        eventos_historicos = payload2.get("events") if isinstance(payload2, dict) else None
        if not isinstance(eventos_historicos, list) or len(eventos_historicos) >= 500:
            return base + "\n⚪ Histórico ESPN inválido ou potencialmente truncado."
    except (requests.RequestException, ValueError, TypeError, OSError):
        return base + "\n⚪ ESPN temporariamente indisponível; estatísticas não inventadas."

    resultados = _resultados(eventos_historicos, liga, corte)
    casa, fora = ids
    casa_nome = str(previsao.get("casa") or "Casa")[:90]
    fora_nome = str(previsao.get("fora") or "Fora")[:90]
    casa_all = _equipa_partidas(resultados, casa)
    fora_all = _equipa_partidas(resultados, fora)
    casa_local = _equipa_partidas(resultados, casa, local="casa")
    fora_local = _equipa_partidas(resultados, fora, local="fora")
    h2h = [r for r in resultados if {r["casa_id"], r["fora_id"]} == {casa, fora}]
    linhas = [
        base,
        f"🔎 Liga {liga} | últimos {JANELA_DIAS} dias anteriores ao snapshot",
        "📍 Só resultados finais da mesma competição; sem jogos futuros.",
        "",
        f"🏠 {casa_nome} — até 5 resultados recentes",
        f"• Forma: {_resumo_forma(casa_all)}",
    ]
    linhas.extend(_lista_resultados(casa_all))
    linhas.extend([
        f"• Só em casa: {_resumo_forma(casa_local)}",
        "",
        f"✈️ {fora_nome} — até 5 resultados recentes",
        f"• Forma: {_resumo_forma(fora_all)}",
    ])
    linhas.extend(_lista_resultados(fora_all))
    linhas.extend([
        f"• Só fora: {_resumo_forma(fora_local)}",
        "",
        f"⚔️ Confrontos diretos na janela: {len(h2h)}",
    ])
    for r in h2h[:3]:
        dia_jogo = datetime.fromtimestamp(r["timestamp"], TZ_PT).strftime("%d/%m")
        linhas.append(f"  • {dia_jogo} {r['casa']} {r['golos_casa']}-{r['golos_fora']} {r['fora']}")
    linhas.extend([
        "",
        "⚠️ Apenas amostra ESPN da competição e período indicado; pode ser incompleta.",
        "⚠️ Contexto complementar consultado agora, NÃO dados originais congelados.",
        "🔒 Não altera V1.2, SEL1, Platt, V1.3, odds ou rankings.",
    ])
    return "\n".join(linhas)
