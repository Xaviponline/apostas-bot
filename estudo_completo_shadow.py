"""Relatório /estudo_jogo N completo: contexto verificado vs snapshot V1.2.

Somente OWNER, somente SHADOW, sem probabilidades novas e sem seleção de apostas.
Usa o recolhedor ESPN existente (até 2 pedidos) e nunca altera os snapshots.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from estudo_forma_espn import contexto_espn
from estudo_jogo_shadow import gerar_estudo_jogo, _numero, _fmt


TZ_PT = ZoneInfo("Europe/Lisbon")


def _ocorrencias(partidas, mercado, lado):
    """Contagem de indicadores alinhados, não é probabilidade de um mercado."""
    golos = {
        "Over 1.5 Golos": lambda gf, ga: gf + ga >= 2,
        "Over 2.5 Golos": lambda gf, ga: gf + ga >= 3,
        "Under 2.5 Golos": lambda gf, ga: gf + ga <= 2,
        "Under 3.5 Golos": lambda gf, ga: gf + ga <= 3,
        "Ambas Marcam": lambda gf, ga: gf > 0 and ga > 0,
    }
    regras_lado = {
        "Vitória Casa": {"casa": lambda gf, ga: gf > ga,
                         "fora": lambda gf, ga: gf < ga},
        "Vitória Fora": {"casa": lambda gf, ga: gf < ga,
                         "fora": lambda gf, ga: gf > ga},
        "1X (Casa ou Empate)": {"casa": lambda gf, ga: gf >= ga,
                                "fora": lambda gf, ga: gf <= ga},
        "X2 (Empate ou Fora)": {"casa": lambda gf, ga: gf <= ga,
                                "fora": lambda gf, ga: gf >= ga},
    }
    regra = golos.get(mercado) or regras_lado.get(mercado, {}).get(lado)
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
    taxa_casa = _ocorrencias(casa, mercado, "casa")
    taxa_fora = _ocorrencias(fora, mercado, "fora")
    linhas = ["🔎 CRUZAMENTO — V1.2 vs RESULTADOS OBSERVADOS"]
    if taxa_casa is None or taxa_fora is None:
        linhas.append(
            "• Mercado sem comparação estatística direta nesta versão; "
            "consultar o histórico factual abaixo."
        )
        return linhas

    c, n_c = taxa_casa
    f, n_f = taxa_fora
    if mercado in {"Vitória Casa", "Vitória Fora", "1X (Casa ou Empate)", "X2 (Empate ou Fora)"}:
        linhas.append(f"• Indicador de resultados favoráveis, equipa da casa em casa: {c}/{n_c}")
        linhas.append(f"• Indicador complementar, visitantes fora: {f}/{n_f}")
        linhas.append("ℹ️ Em resultados 1X2, os indicadores são proxies de equipas diferentes, NÃO frequências do mesmo mercado.")
    else:
        linhas.append(f"• {mercado}, equipa da casa em casa: {c}/{n_c} jogos")
        linhas.append(f"• {mercado}, visitantes fora: {f}/{n_f} jogos")
    if min(n_c, n_f) < 3:
        linhas.append(
            "⚪ Amostra local insuficiente (<3 jogos) para classificar a concordância."
        )
        return linhas

    p_c = c / n_c
    p_f = f / n_f
    if p_c >= 2/3 and p_f >= 2/3:
        if min(n_c, n_f) < 5:
            linhas.append(
                "🟡 Tendência favorável com evidência limitada: ambos os históricos "
                "mostram frequência elevada, mas pelo menos uma amostra tem menos "
                "de 5 jogos."
            )
        else:
            linhas.append(
                "🟢 Tendência observada favorável em ambas as amostras locais "
                "(mínimo 5 jogos por equipa); não valida a V1.2."
            )
    elif p_c <= 1/3 and p_f <= 1/3:
        linhas.append(
            "🔴 Possível contradição: resultados locais de ambas as equipas "
            "têm baixa frequência do mercado escolhido."
        )
    elif (p_c >= 2/3 and p_f <= 1/3) or (p_f >= 2/3 and p_c <= 1/3):
        linhas.append(
            "🟠 Tendências locais opostas entre equipas; "
            "a previsão merece cautela acrescida."
        )
    elif (p_c >= 2/3 and p_f >= 0.50) or (p_f >= 2/3 and p_c >= 0.50):
        linhas.append(
            "🟡 Tendência parcialmente favorável: uma amostra é forte, "
            "mas a outra apresenta apoio moderado."
        )
    else:
        linhas.append(
            "⚪ Tendência mista ou inconclusiva; sem evidência consistente "
            "nas duas amostras locais."
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


def _nota_preco_historico(previsao):
    """Só descreve a odd inicial já congelada; nunca estima VALUE nem odds atuais."""
    odd = _numero(previsao.get("odd_real"))
    minima = _numero(previsao.get("odd_minima"))
    linhas = ["💰 LEITURA DO PREÇO HISTÓRICO — SEM VALUE NOVO"]
    if odd is None or odd <= 1:
        linhas.append(
            "⚪ Sem odd real histórica registada; não é possível comparar o preço "
            "com o mínimo congelado."
        )
    elif minima is None or minima <= 1:
        linhas.append(
            f"⚪ Odd inicial {_fmt(odd)} registada; mínimo congelado indisponível."
        )
    elif odd < minima:
        linhas.append(
            f"🔴 Odd inicial {_fmt(odd)} abaixo do mínimo congelado {_fmt(minima)}: "
            "não satisfazia o critério de preço no primeiro registo."
        )
    else:
        linhas.append(
            f"🟡 Odd inicial {_fmt(odd)} atingiu o mínimo congelado {_fmt(minima)}; "
            "não demonstra VALUE nem confirma a cotação atual."
        )
    linhas.append("⚠️ Não consultar odds agora; não altera coorte ou decisão comercial.")
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
    # A ficha offline permanece intacta; apenas a composição do modo completo
    # esclarece que este comando também consultou a ESPN.
    base = base.replace(
        "🔒 Estudo apenas leitura: sem consultas externas, sem VALUE novo, sem apostas.",
        "🔒 Snapshot V1.2 apenas leitura; consulta complementar ESPN separada."
    )
    if dados:
        base = base.replace(
            "• Confrontos diretos, ausências, escalações e descanso não são inferidos.",
            "• Confrontos diretos na janela ESPN apresentados abaixo; "
            "ausências, escalações e descanso não verificados."
        )
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
    linhas.extend(_nota_preco_historico(previsao))
    linhas.extend([
        "",
        "──────────",
        "",
        from_espn,
        "",
        "🔐 Relatório exclusivamente informativo: sem novas apostas, sem "
        "VALUE recalculado e sem mudanças à V1.2/SEL1/Platt/V1.3.",
    ])
    return "\n".join(linhas)
