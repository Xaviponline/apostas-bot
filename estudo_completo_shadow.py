"""Relatório /estudo_jogo N completo: contexto verificado vs snapshot V1.2.

Somente OWNER, somente SHADOW, sem probabilidades novas e sem seleção de apostas.
Usa o recolhedor ESPN existente (até 2 pedidos) e nunca altera os snapshots.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from estudo_forma_espn import contexto_espn
from estudo_jogo_shadow import gerar_estudo_jogo


TZ_PT = ZoneInfo("Europe/Lisbon")


def _ocorrencias(partidas, mercado):
    """Conta eventos observados; nunca converte frequências em probabilidade."""
    regras = {
        "Over 1.5 Golos": lambda gf, ga: gf + ga >= 2,
        "Over 2.5 Golos": lambda gf, ga: gf + ga >= 3,
        "Under 2.5 Golos": lambda gf, ga: gf + ga <= 2,
        "Under 3.5 Golos": lambda gf, ga: gf + ga <= 3,
        "Ambas Marcam": lambda gf, ga: gf > 0 and ga > 0,
    }
    regra = regras.get(mercado)
    if regra is None:
        return None
    validos = [
        (gf, ga) for item, gf, ga, adversario, casa in partidas
        if isinstance(gf, int) and isinstance(ga, int) and gf >= 0 and ga >= 0
    ]
    return sum(regra(gf, ga) for gf, ga in validos), len(validos)


def _conclusao_mercado(mercado, dados):
    casa = dados.get("casa_local") or []
    fora = dados.get("fora_local") or []
    taxa_casa = _ocorrencias(casa, mercado)
    taxa_fora = _ocorrencias(fora, mercado)
    linhas = ["🔎 CRUZAMENTO — V1.2 vs RESULTADOS OBSERVADOS"]
    if taxa_casa is None or taxa_fora is None:
        linhas.append(
            "• Mercado sem comparação estatística direta nesta versão; "
            "consultar o histórico factual abaixo."
        )
        return linhas

    c, n_c = taxa_casa
    f, n_f = taxa_fora
    linhas.append(f"• {mercado}, equipa da casa em casa: {c}/{n_c} jogos")
    linhas.append(f"• {mercado}, visitantes fora: {f}/{n_f} jogos")
    if min(n_c, n_f) < 3:
        linhas.append(
            "⚪ Amostra local insuficiente (<3 jogos) para classificar a concordância."
        )
        return linhas

    p_c = c / n_c
    p_f = f / n_f
    if p_c >= 0.67 and p_f >= 0.67:
        linhas.append(
            "🟢 Tendência observada concordante nas duas equipas; "
            "não valida a probabilidade estimada pela V1.2."
        )
    elif p_c <= 0.33 and p_f <= 0.33:
        linhas.append(
            "🔴 Possível contradição: resultados locais de ambas as equipas "
            "têm baixa frequência do mercado escolhido."
        )
    elif (p_c >= 0.67 and p_f <= 0.33) or (p_f >= 0.67 and p_c <= 0.33):
        linhas.append(
            "🟠 Tendências locais opostas entre equipas; "
            "a previsão merece cautela acrescida."
        )
    else:
        linhas.append(
            "🟡 Tendência mista ou inconclusiva; sem concordância forte "
            "com os dois históricos locais."
        )
    if min(n_c, n_f) < 5:
        linhas.append(
            "⚠️ Amostra casa/fora curta (<5 jogos em pelo menos uma equipa). "
            "As frequências são descritivas, não probabilidades calibradas."
        )
    linhas.append(
        "⚠️ Estas observações podem sobrepor-se aos dados usados na V1.2; "
        "não são validação estatística independente nem fora da amostra."
    )
    return linhas


def gerar_estudo_completo(previsao, ranking, agora=None, session=None):
    """Relatório integrado. Uma chamada ao contexto ESPN (máx. 2 requests)."""
    agora = agora or datetime.now(TZ_PT)
    data_hoje = agora.astimezone(TZ_PT).date().isoformat()
    if (
        not isinstance(previsao, dict)
        or previsao.get("data_jogo") != data_hoje
        or previsao.get("modelo_versao") != "V1.2"
        or previsao.get("ranking_modelo") != ranking
    ):
        return "⚪ Estudo completo indisponível: snapshot V1.2 do dia não confirmado."

    base = gerar_estudo_jogo([previsao], str(ranking), agora=agora)
    dados = {}
    from_espn = contexto_espn(previsao, session=session, detalhes=dados)
    linhas = [
        f"📘 ESTUDO COMPLETO — SHADOW | RANKING #{ranking}",
        "",
        base,
        "",
        "──────────",
        "",
    ]
    if dados:
        linhas.extend(_conclusao_mercado(str(previsao.get("mercado") or ""), dados))
        linhas.extend(["", "──────────", ""])
    else:
        linhas.extend([
            "⚪ Cruzamento automático suspenso: ESPN não devolveu "
            "contexto verificado. Não atribuí conclusões à forma.",
            "",
        ])
    linhas.extend([
        from_espn,
        "",
        "🔐 Relatório exclusivamente informativo: sem novas apostas, sem "
        "VALUE recalculado e sem mudanças à V1.2/SEL1/Platt/V1.3.",
    ])
    return "\n".join(linhas)
