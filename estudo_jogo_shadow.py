"""Estudo explicativo de um snapshot V1.2 já congelado.

Sem HTTP, sem apostas, sem alterar probabilidades/ranking/odds/snapshots.
Os sinais são heurísticas descritivas, NÃO um segundo modelo nem validação VALUE.
"""
from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo


TZ_PT = ZoneInfo("Europe/Lisbon")
MAX_LISTAGEM = 20


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return numero if isfinite(numero) else None


def _inteiro(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError, OverflowError):
        return None


def _fmt(valor, decimais=2):
    numero = _numero(valor)
    return f"{numero:.{decimais}f}".replace(".", ",") if numero is not None else "—"


def _hora(timestamp):
    ts = _numero(timestamp)
    if ts is None:
        return "hora indisponível"
    try:
        return datetime.fromtimestamp(ts, tz=TZ_PT).strftime("%H:%M")
    except (OSError, OverflowError, ValueError):
        return "hora indisponível"


def _sinais(previsao, diag):
    """Apenas observações descritivas; não recalcular probabilidades."""
    mercado = str(previsao.get("mercado") or "")
    ppg_casa = _numero(diag.get("ppg_casa"))
    ppg_fora = _numero(diag.get("ppg_fora"))
    lc = _numero(diag.get("lambda_casa"))
    lf = _numero(diag.get("lambda_fora"))
    total = lc + lf if lc is not None and lf is not None else None

    favoraveis = []
    cautelas = []
    if mercado == "Vitória Casa":
        if lc is not None and lf is not None:
            if lc >= lf + 0.50:
                favoraveis.append("Modelo prevê pelo menos +0,50 golos esperados para a equipa da casa.")
            elif lc <= lf:
                cautelas.append("Golos esperados não favorecem a equipa da casa.")
        if ppg_casa is not None and ppg_fora is not None:
            if ppg_casa >= ppg_fora + 0.50:
                favoraveis.append("PPG recente favorece a equipa da casa em pelo menos 0,50.")
            elif ppg_casa + 0.50 <= ppg_fora:
                cautelas.append("PPG recente favorece a equipa visitante, contra o mercado escolhido.")
    elif mercado == "Vitória Fora":
        if lc is not None and lf is not None:
            if lf >= lc + 0.50:
                favoraveis.append("Modelo prevê pelo menos +0,50 golos esperados para os visitantes.")
            elif lf <= lc:
                cautelas.append("Golos esperados não favorecem os visitantes.")
        if ppg_casa is not None and ppg_fora is not None:
            if ppg_fora >= ppg_casa + 0.50:
                favoraveis.append("PPG recente favorece os visitantes em pelo menos 0,50.")
            elif ppg_fora + 0.50 <= ppg_casa:
                cautelas.append("PPG recente favorece a equipa da casa, contra o mercado escolhido.")
    elif mercado == "Ambas Marcam":
        if lc is not None and lf is not None:
            if min(lc, lf) >= 1.20:
                favoraveis.append("Ambas as equipas têm pelo menos 1,20 golos esperados.")
            elif min(lc, lf) < 0.90:
                cautelas.append("Uma equipa apresenta menos de 0,90 golos esperados.")
    elif mercado.startswith(("Over ", "Under ")):
        partes = mercado.split()
        linha = _numero(partes[1]) if len(partes) > 1 else None
        if total is not None and linha is not None:
            # O total esperado não é a probabilidade de ganhar o mercado.
            if mercado.startswith("Over "):
                if total >= linha + 0.30:
                    favoraveis.append("Total esperado de golos fica acima da linha em pelo menos 0,30.")
                elif total <= linha - 0.30:
                    cautelas.append("Total esperado de golos fica abaixo da linha por pelo menos 0,30.")
            else:
                if total <= linha - 0.30:
                    favoraveis.append("Total esperado de golos fica abaixo da linha por pelo menos 0,30.")
                elif total >= linha + 0.30:
                    cautelas.append("Total esperado de golos fica acima da linha por pelo menos 0,30.")

    # Contraste descritivo, não é um reajuste à probabilidade V1.2.
    media_liga_casa = _numero(diag.get("media_liga_casa"))
    media_liga_fora = _numero(diag.get("media_liga_fora"))
    baseline = (
        media_liga_casa + media_liga_fora
        if media_liga_casa is not None and media_liga_fora is not None
        else None
    )
    if total is not None and baseline is not None and baseline > 0:
        desvio = (total / baseline) - 1.0
        if desvio >= 0.25:
            cautelas.append(
                f"Golos esperados {_fmt(desvio * 100, 1)}% acima da média da liga "
                f"({_fmt(total)} vs {_fmt(baseline)}); validar robustez da projeção."
            )
        elif desvio <= -0.25:
            cautelas.append(
                f"Golos esperados {_fmt(abs(desvio) * 100, 1)}% abaixo da média da liga "
                f"({_fmt(total)} vs {_fmt(baseline)}); validar robustez da projeção."
            )

    local_casa = _inteiro(diag.get("amostra_casa_local"))
    local_fora = _inteiro(diag.get("amostra_fora_local"))
    liga = _inteiro(diag.get("amostra_liga"))
    if local_casa is not None and local_fora is not None and min(local_casa, local_fora) < 3:
        cautelas.append("Amostra específica casa/fora inferior a 3 jogos para pelo menos uma equipa.")
    elif local_casa is not None and local_fora is not None and min(local_casa, local_fora) == 3:
        cautelas.append("Só 3 jogos em casa/fora para pelo menos uma equipa: estimativa local pouco robusta.")
    if liga is not None and liga < 20:
        cautelas.append("A base da liga tem menos de 20 jogos.")
    prob = _numero(previsao.get("probabilidade"))
    if prob is not None and prob >= 0.67:
        cautelas.append("Probabilidade elevada: a V1.2 apresentou excesso de confiança em auditorias anteriores.")
    if not diag:
        cautelas.append("Este snapshot não tem telemetria estatística suficiente para avaliar sinais.")
    return favoraveis[:4], cautelas[:5]


def gerar_estudo_jogo(previsoes, argumento="", agora=None):
    """Mostra lista ou leitura do ranking de hoje; exclusivamente dados guardados."""
    agora = agora or datetime.now(TZ_PT)
    data_iso = agora.astimezone(TZ_PT).date().isoformat()
    dia = agora.astimezone(TZ_PT).strftime("%d/%m/%Y")
    hoje = [
        p for p in (previsoes or [])
        if isinstance(p, dict) and p.get("data_jogo") == data_iso
        and str(p.get("modelo_versao") or "") == "V1.2"
        and _inteiro(p.get("ranking_modelo")) is not None
        and _inteiro(p.get("ranking_modelo")) > 0
    ]
    hoje.sort(key=lambda p: (_inteiro(p.get("ranking_modelo")), str(p.get("chave") or "")))

    if not hoje:
        return (
            f"🧠 ESTUDO DE JOGO — SHADOW\n📅 {dia}\n\n"
            "Ainda não existem previsões V1.2 congeladas para hoje.\n"
            "Este comando não gera jogos nem consulta APIs."
        )

    arg = str(argumento or "").strip()
    if not arg:
        linhas = [
            f"🧠 ESTUDO DE JOGO — SHADOW | {dia}",
            "🔒 Leitura dos snapshots já congelados",
            "",
            f"📚 {len(hoje)} previsões disponíveis:",
        ]
        for p in hoje[:MAX_LISTAGEM]:
            ranking = _inteiro(p.get("ranking_modelo"))
            nome = f"{p.get('casa') or '?'} vs {p.get('fora') or '?'}"
            linhas.append(f"#{ranking} · {_hora(p.get('timestamp_jogo'))} · {nome}")
            linhas.append(f"   {p.get('mercado') or 'Mercado não identificado'}")
        linhas.extend([
            "",
            "Para abrir: /estudo_jogo 1 (substitui 1 pelo ranking).",
            "⚠️ Só estatísticas registadas; não recalcula nem recomenda apostas.",
        ])
        return "\n".join(linhas)

    if not arg.isascii() or not arg.isdecimal():
        return "Formato: /estudo_jogo [RANKING]. Exemplo: /estudo_jogo 1."
    ranking = int(arg)
    correspondentes = [p for p in hoje if _inteiro(p.get("ranking_modelo")) == ranking]
    if not correspondentes:
        return f"Não existe previsão com ranking #{ranking} para {dia}. Usa /estudo_jogo."
    if len(correspondentes) > 1:
        return "Ranking repetido em vários snapshots. Não escolhi um jogo de forma ambígua."

    p = correspondentes[0]
    diag = p.get("diagnostico_modelo")
    diag = diag if isinstance(diag, dict) else {}
    favoraveis, cautelas = _sinais(p, diag)
    prova = _numero(p.get("probabilidade"))
    bruta = _numero(p.get("probabilidade_bruta"))
    inicio = _numero(p.get("timestamp_jogo"))
    estado = "A decorrer / já iniciado" if inicio is not None and inicio <= agora.timestamp() else "Por começar"
    linhas = [
        "🧠 ESTUDO DE JOGO — SHADOW V1.2",
        f"⚽ {p.get('casa') or '?'} vs {p.get('fora') or '?'}",
        f"🏆 {p.get('liga') or 'Competição por identificar'}",
        f"📅 {dia} · 🕒 {_hora(p.get('timestamp_jogo'))} (Portugal) · {estado}",
        "",
        f"🏅 Ranking congelado #{ranking} | {p.get('confianca_modelo') or 'Confiança não indicada'}",
        f"🎯 Mercado: {p.get('mercado') or 'Não indicado'}",
        f"📈 Probabilidade V1.2: {_fmt(prova * 100 if prova is not None else None, 1)}%",
        f"🧮 Probabilidade bruta: {_fmt(bruta * 100 if bruta is not None else None, 1)}%",
        f"↳ Ajuste V1.2 vs bruto: {_fmt((prova - bruta) * 100 if prova is not None and bruta is not None else None, 1)} pp",
        f"📚 Qualidade da base: {_fmt(p.get('qualidade'), 0)}/100 (não é probabilidade de acerto)",
        "",
        "🔬 ESTATÍSTICAS CONGELADAS",
    ]
    lc, lf = _numero(diag.get("lambda_casa")), _numero(diag.get("lambda_fora"))
    if lc is not None and lf is not None:
        linhas.append(
            f"• Golos esperados (Poisson): casa {_fmt(lc)} | fora {_fmt(lf)} | total {_fmt(lc+lf)}"
        )
    else:
        linhas.append("• Golos esperados: não guardados neste snapshot")
    pc, pf = _numero(diag.get("ppg_casa")), _numero(diag.get("ppg_fora"))
    if pc is not None and pf is not None:
        linhas.append(f"• PPG recente (até 6 jogos): casa {_fmt(pc)} | fora {_fmt(pf)}")
    else:
        linhas.append("• PPG recente: indisponível")
    amostras = [
        ("casa", "amostra_casa"), ("fora", "amostra_fora"),
        ("casa local", "amostra_casa_local"), ("fora local", "amostra_fora_local"),
        ("liga", "amostra_liga"),
    ]
    present = [f"{nome} {n}" for nome, campo in amostras
               if (n := _inteiro(diag.get(campo))) is not None]
    linhas.append("• Amostras: " + (" | ".join(present) if present else "não documentadas"))
    media_casa = _numero(diag.get("media_liga_casa"))
    media_fora = _numero(diag.get("media_liga_fora"))
    if media_casa is not None and media_fora is not None:
        linhas.append(f"• Média golos na liga: casa {_fmt(media_casa)} | fora {_fmt(media_fora)}")

    alternativas = diag.get("probabilidades_brutas_mercados")
    if isinstance(alternativas, dict):
        exibidas = 0
        for mercado in ("Ambas Marcam", "Over 2.5 Golos", "Under 3.5 Golos",
                        "Vitória Casa", "Empate", "Vitória Fora"):
            if mercado == p.get("mercado"):
                continue
            v = _numero(alternativas.get(mercado))
            if v is not None and 0 < v < 1:
                if exibidas == 0:
                    linhas.extend(["", "🔀 CENÁRIOS ALTERNATIVOS (PROBABILIDADE BRUTA)"])
                linhas.append(f"• {mercado}: {_fmt(v * 100, 1)}%")
                exibidas += 1
            if exibidas >= 3:
                break
    linhas.extend(["", "✅ SINAIS DESCRITIVOS"])
    linhas.extend(f"• {s}" for s in favoraveis or ["Sem sinal suficientemente forte nos indicadores disponíveis."])
    linhas.extend(["", "⚠️ RISCOS E CONTRADIÇÕES"])
    linhas.extend(f"• {s}" for s in cautelas or ["Sem contradição óbvia nas heurísticas disponíveis; não garante acerto."])

    odd = _numero(p.get("odd_real"))
    minima = _numero(p.get("odd_minima"))
    linhas.extend(["", "💰 ODDS REGISTADAS"])
    linhas.append(f"• Odd mínima congelada: {_fmt(minima)}")
    if odd is not None and odd > 1:
        linhas.append(f"• Primeira odd registada: {_fmt(odd)} (histórica, não cotação atual)")
        linhas.append("• Atingiu a mínima registada: " + ("sim" if minima is not None and odd >= minima else "não"))
    else:
        linhas.append("• Odd real: ainda não registada / indisponível")

    linhas.extend([
        "",
        "🚫 DADOS AINDA NÃO VERIFICADOS",
        "• Confrontos diretos, ausências, escalações e descanso não são inferidos.",
        "• Não existe nova previsão nem recalibração da Platt neste relatório.",
        "",
        "🔒 Estudo apenas leitura: sem consultas externas, sem VALUE novo, sem apostas.",
        "⚠️ Heurísticas explicativas, não prova de vantagem ou rentabilidade.",
    ])
    return "\n".join(linhas)
