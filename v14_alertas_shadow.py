"""V1.4 SHADOW — diagnóstico local de riscos do modelo versus odds.

Apenas lê snapshots V1.2 e a coorte V1.3 fixa. Os limiares são DESCRITIVOS,
escolhidos após analisar casos históricos: não constituem validação prospetiva.
Não seleciona/aposta/promove previsões, nem corrige odds ou CLV históricos.
"""
from collections import Counter
from datetime import datetime, timezone
from math import isfinite
from zoneinfo import ZoneInfo

from odds_identidade_guard import MAX_IDADE_ODD_SEG, MAX_FUTURO_ODD_SEG

MIN_GAP_PROBABILIDADE = 0.15  # 15 pp vs probabilidade implícita bruta 1/odd
MIN_EV_TEO = 0.25            # 25% de EV puramente modelado (não executável)
MIN_AMOSTRA_LOCAL = 3
MAX_DETALHES = 6


def _numero(valor):
    if isinstance(valor, bool):
        return None
    try:
        n = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if isfinite(n) else None


def _odd(valor):
    n = _numero(valor)
    return n if n is not None and 1 < n < 1000 else None


def _instante(valor):
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        dt = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None
    return dt.astimezone(timezone.utc).timestamp()


def _curto(valor, limite=46):
    return str(valor or "?").replace("\r", " ").replace("\n", " ")[:limite]


def _pct(valor, casas=1):
    return f"{100 * valor:+.{casas}f}%".replace(".", ",")


def _avaliar(indice, p):
    """Diagnóstico sem classificação de resultado e sem leitura de fecho CLV."""
    prob = _numero(p.get("probabilidade"))
    if prob is not None and not 0 < prob < 1:
        prob = None
    # Usar a primeira odd confirmada da V1.3, nunca a odd atual ou o fecho.
    confirmada = _odd(p.get("odd_valor_confirmado"))
    inicial = _odd(p.get("odd_real"))
    if confirmada is not None:
        cotacao = confirmada
        estado_preco = "confirmada no snapshot"
        capturada_em = p.get("valor_confirmado_em") or p.get("odds_capturada_em")
    elif inicial is not None:
        cotacao = inicial
        estado_preco = "inicial no snapshot, não confirmada para VALUE"
        capturada_em = p.get("odds_capturada_em")
    else:
        cotacao = None
        estado_preco = "sem cotação"
        capturada_em = None

    gap = (prob - 1.0 / cotacao) if prob is not None and cotacao else None
    ev = (prob * cotacao - 1) if prob is not None and cotacao else None
    alertas = []
    if prob is None:
        alertas.append("PROBABILIDADE_INVÁLIDA")
    if cotacao is None:
        alertas.append("SEM_ODD")
    else:
        if gap is not None and gap >= MIN_GAP_PROBABILIDADE:
            alertas.append("GAP_MODELO_MERCADO_15PP")
        if ev is not None and ev >= MIN_EV_TEO:
            alertas.append("EV_TEÓRICO_25PC")
        if not (p.get("odds_fonte") and p.get("odds_event_id")):
            alertas.append("ORIGEM_PREÇO_INCOMPLETA")

        # "Atualizada" é a hora da última ALTERAÇÃO da cotação no fornecedor,
        # não o timestamp em que a casa aceitou independentemente uma aposta.
        ts_captura = _instante(capturada_em)
        ts_alteracao = _instante(p.get("odds_atualizada_em"))
        if ts_captura is None or ts_alteracao is None:
            alertas.append("FRESCURA_NÃO_AVALIÁVEL")
        else:
            idade = ts_captura - ts_alteracao
            if idade < -MAX_FUTURO_ODD_SEG:
                alertas.append("ALTERAÇÃO_FUTURA")
            elif idade > MAX_IDADE_ODD_SEG:
                alertas.append("ÚLTIMA_ALTERAÇÃO_MAIS_6H")
    diag = p.get("diagnostico_modelo")
    diag = diag if isinstance(diag, dict) else {}
    if diag.get("forma_fonte") == "multicompeticao":
        local = [_numero(diag.get(k)) for k in ("amostra_casa_local", "amostra_fora_local")]
        if all(n is not None and n >= 0 and n.is_integer() for n in local):
            if min(local) < MIN_AMOSTRA_LOCAL:
                alertas.append("AMOSTRA_LOCAL_REDUZIDA")

    return {
        "indice": indice,
        "jogo": f"{_curto(p.get('casa'), 32)} vs {_curto(p.get('fora'), 32)}",
        "data": str(p.get("data_jogo") or "?"),
        "mercado": str(p.get("mercado") or "?"),
        "liga": str(p.get("liga") or "?"),
        "prob": prob,
        "odd": cotacao,
        "estado_preco": estado_preco,
        "p_implied": 1.0 / cotacao if cotacao else None,
        "gap": gap,
        "ev": ev,
        "alertas": alertas,
        "qualidade": _numero(p.get("qualidade")),
        "forma_fonte": diag.get("forma_fonte"),
        "amostra_casa_local": diag.get("amostra_casa_local"),
        "amostra_fora_local": diag.get("amostra_fora_local"),
    }


def _coorte(registo, originais):
    met = registo.metricas_v13_comercial()
    entradas = met.get("coorte")
    if not isinstance(entradas, list):
        raise ValueError("Coorte V1.3 indisponível")
    vistos = set()
    selecionados = []
    for entrada in entradas:
        if not isinstance(entrada, dict):
            raise ValueError("Entrada V1.3 inválida")
        i = entrada.get("snapshot")
        if type(i) is not int or not 1 <= i <= len(originais) or i in vistos:
            raise ValueError("Referência de snapshot inválida/repetida")
        vistos.add(i)
        p = originais[i - 1]
        if (not isinstance(p, dict) or p.get("modelo_versao") != "V1.2"
                or str(p.get("mercado") or "") != str(entrada.get("mercado") or "")):
            raise ValueError("Identidade ou versão V1.3 divergente")
        selecionados.append((i, p))
    return selecionados


def _futuros(originais, agora):
    agora_ts = agora.timestamp()
    saida = []
    for i, p in enumerate(originais, start=1):
        if not isinstance(p, dict) or p.get("modelo_versao") != "V1.2":
            continue
        if p.get("estado") != "pendente":
            continue
        ts = _numero(p.get("timestamp_jogo"))
        criada = _instante(p.get("criada_em"))
        if ts is None or ts <= agora_ts or criada is None or criada >= ts:
            continue
        saida.append((i, p))
    return saida


def _detalhe(a):
    alerta = ", ".join(a["alertas"]) or "sem sinal nos limiares deste diagnóstico"
    linhas = [
        f"#{a['indice']} {a['data']} {_curto(a['jogo'], 68)}",
        f"   {_curto(a['mercado'])} | {_curto(a['liga'])}",
        f"   Prob. {f'{a['prob'] * 100:.1f}'.replace('.', ',') if a['prob'] is not None else '?'}%"
        f" | Odd {f'{a['odd']:.2f}'.replace('.', ',') if a['odd'] is not None else '?'}"
        f" ({a['estado_preco']})",
    ]
    if a["gap"] is not None:
        linhas.append(
            f"   Implícita bruta {f'{a['p_implied'] * 100:.1f}'.replace('.', ',')}%"
            f" | gap {a['gap'] * 100:+.1f}pp"
            f" | EV teórico {_pct(a['ev'])}"
        )
    linhas.append(f"   ⚠️ {alerta}")
    if a["forma_fonte"] == "multicompeticao":
        linhas.append(
            "   📚 Forma multicompetição"
            f" | locais casa/fora: {a['amostra_casa_local'] if a['amostra_casa_local'] is not None else '?'}"
            f"/{a['amostra_fora_local'] if a['amostra_fora_local'] is not None else '?'}"
        )
    return "\n".join(linhas)


def relatorio_v14_alertas(registo, argumento="", agora=None):
    """Comandos: coorte (default), futuros, snapshot N ou N."""
    agora = agora or datetime.now(timezone.utc)
    if agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError("Hora atual necessita de fuso")
    arg = str(argumento or "").strip().lower()
    if not arg:
        arg = "coorte"
    originais = registo.dados.get("previsoes") if isinstance(registo.dados, dict) else None
    if not isinstance(originais, list):
        raise ValueError("Snapshots indisponíveis")
    if arg == "coorte":
        selected = _coorte(registo, originais)
        subtitulo = "mesma coorte fixa V1.3, sem reclassificar entradas"
    elif arg == "futuros":
        selected = _futuros(originais, agora)
        subtitulo = "snapshots V1.2 por iniciar (não é uma coorte prospetiva congelada)"
    else:
        raw = arg[9:].strip() if arg.startswith("snapshot ") else arg
        if not raw.isascii() or not raw.isdecimal() or not 1 <= len(raw) <= 7:
            return ("🔎 Uso: /v14_alertas [coorte|futuros|399|snapshot 399]\n"
                    "🔒 OWNER — SHADOW local, não altera apostas.")
        i = int(raw)
        if i < 1 or i > len(originais) or not isinstance(originais[i - 1], dict):
            return f"⚪ Snapshot #{i} inexistente. Nenhum dado foi alterado."
        p = originais[i - 1]
        if p.get("modelo_versao") != "V1.2":
            return f"⚪ Snapshot #{i} não é V1.2; sem extrapolar versões."
        selected = [(i, p)]
        subtitulo = "snapshot individual, análise ilustrativa sem seleção retrospetiva de filtros"
    avaliados = [_avaliar(i, p) for i, p in selected]
    n = len(avaliados)
    tipos = Counter(x for a in avaliados for x in set(a["alertas"]))
    fortes = [a for a in avaliados if (
        "GAP_MODELO_MERCADO_15PP" in a["alertas"]
        or "EV_TEÓRICO_25PC" in a["alertas"]
    )]
    por_mercado = Counter(a["mercado"] for a in fortes)
    por_liga = Counter(a["liga"] for a in fortes)
    sem_odd = tipos["SEM_ODD"]
    cab = [
        "🛡️ V1.4 SHADOW — ALERTAS DE RISCO (APENAS LEITURA)",
        f"🔒 Universo: {subtitulo}",
        f"📚 Previsões examinadas: {n} | Odds guardadas: {n - sem_odd}"
        f" | Sem odds: {sem_odd}",
        "📏 Limiares diagnósticos fixos: gap ≥15pp ou EV teórico ≥25%",
        f"⚠️ Discrepâncias de preço/probabilidade: {len(fortes)}"
        f" | Alteração >6h: {tipos['ÚLTIMA_ALTERAÇÃO_MAIS_6H']}"
        f" | Sem hora comparável: {tipos['FRESCURA_NÃO_AVALIÁVEL']}",
    ]
    if por_mercado:
        cab.append("⚽ Mercados com discrepâncias: " + "; ".join(
            f"{_curto(k, 24)} ({v})" for k, v in por_mercado.most_common(5)))
    if por_liga:
        cab.append("🏆 Competições com discrepâncias: " + "; ".join(
            f"{_curto(k, 24)} ({v})" for k, v in por_liga.most_common(5)))
    if n == 1:
        amostra = avaliados
    else:
        amostra = sorted(
            fortes, key=lambda a: (
                -max(a["gap"] or 0, (a["ev"] or 0) / 2),
                a["indice"],
            )
        )[:MAX_DETALHES]
    if amostra:
        cab.append("\n🔍 CASOS DE ATENÇÃO (não são recomendações de aposta)")
        cab.extend(_detalhe(a) for a in amostra)
    else:
        cab.append("⚪ Sem discrepâncias acima dos limiares neste universo.")
    cab.extend([
        "",
        "ℹ️ 1/odd é probabilidade implícita BRUTA; não desconta margem da casa.",
        "ℹ️ Odds guardadas/timestamps/ID de fornecedor NÃO comprovam disponibilidade ou execução na Betano.",
        "⚠️ Limiares escolhidos após casos históricos: alerta não comprova erro, edge ou rentabilidade.",
        "🔒 Zero HTTP / zero escrita: sem filtros, aposta, promoção, alteração de V1.2/V1.3, ROI ou CLV.",
    ])
    return "\n".join(cab)
