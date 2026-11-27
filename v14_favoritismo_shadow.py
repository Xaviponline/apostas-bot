"""V1.4 SHADOW — divergência PPG geral vs golos esperados em vitórias.

Ferramenta de diagnóstico local. As regras foram escolhidas após o caso #631,
não têm validação prospetiva e não alteram probabilidades, filtros, coortes,
apostas, CLV ou snapshots. PPG e lambdas são medidas DIFERENTES.
"""
from collections import Counter
from math import isfinite

from v14_alertas_shadow import _coorte

MIN_PPG_INVERSAO = 1.0   # pontos/jogo na direção oposta ao favorito do modelo
MIN_LAMBDA_FAVORITO = 0.75
MAX_CASOS = 8
MERCADOS = {"Vitória Casa": 1, "Vitória Fora": -1}


def _n(valor):
    if type(valor) not in (int, float):
        return None
    numero = float(valor)
    return numero if isfinite(numero) else None


def _txt(valor, maxlen=46):
    return str(valor or "?").replace("\n", " ").replace("\r", " ")[:maxlen]


def avaliar_snapshot(numero, p):
    """Só lê inputs do modelo congelados, nunca resultado nem CLV."""
    diag = p.get("diagnostico_modelo")
    diag = diag if isinstance(diag, dict) else {}
    lado = MERCADOS.get(p.get("mercado"))
    if lado is None:
        return None
    prob = _n(p.get("probabilidade"))
    pc = _n(diag.get("ppg_casa"))
    pf = _n(diag.get("ppg_fora"))
    lc = _n(diag.get("lambda_casa"))
    lf = _n(diag.get("lambda_fora"))
    dados_completos = (
        prob is not None and 0 < prob < 1 and
        pc is not None and pf is not None and
        0 <= pc <= 3 and 0 <= pf <= 3 and
        lc is not None and lf is not None and
        0 < lc < 10 and 0 < lf < 10
    )
    if not dados_completos:
        return {
            "indice": numero, "jogo": f"{_txt(p.get('casa'), 32)} vs {_txt(p.get('fora'), 32)}",
            "data": _txt(p.get("data_jogo"), 12), "liga": _txt(p.get("liga"), 44),
            "mercado": p.get("mercado"), "completo": False,
        }
    # Positivo => PPG favorece adversário da pick do modelo.
    inversao_ppg = lado * (pf - pc)
    # Positivo => lambda favorece o vencedor escolhido pelo modelo.
    vantagem_lambda = lado * (lc - lf)
    alerta = inversao_ppg >= MIN_PPG_INVERSAO and vantagem_lambda >= MIN_LAMBDA_FAVORITO
    return {
        "indice": numero,
        "jogo": f"{_txt(p.get('casa'), 32)} vs {_txt(p.get('fora'), 32)}",
        "data": _txt(p.get("data_jogo"), 12),
        "liga": _txt(p.get("liga"), 44),
        "mercado": p.get("mercado"),
        "completo": True,
        "prob": prob, "qualidade": _n(p.get("qualidade")),
        "ppg_casa": pc, "ppg_fora": pf,
        "lambda_casa": lc, "lambda_fora": lf,
        "inversao_ppg": inversao_ppg,
        "vantagem_lambda": vantagem_lambda,
        "alerta": alerta,
        "amostra_casa_local": diag.get("amostra_casa_local"),
        "amostra_fora_local": diag.get("amostra_fora_local"),
        "forma_fonte": diag.get("forma_fonte"),
    }


def relatorio_v14_favoritismo(registo, argumento=""):
    """V1.3 fixa, ou snapshot individual (mesmo fora da coorte)."""
    arg = str(argumento or "").strip().lower() or "coorte"
    dados = registo.dados.get("previsoes") if isinstance(registo.dados, dict) else None
    if not isinstance(dados, list):
        raise ValueError("Histórico indisponível")
    if arg == "coorte":
        selected = _coorte(registo, dados)
        universo = "coorte oficial V1.3, sem reclassificar entradas"
    else:
        numero_txt = arg[9:].strip() if arg.startswith("snapshot ") else arg
        if not numero_txt.isascii() or not numero_txt.isdecimal() or not 1 <= len(numero_txt) <= 7:
            return ("🔎 Uso: /v14_favoritismo [coorte|631|snapshot 631]\n"
                    "🔒 Apenas OWNER, sem consultas nem alterações.")
        i = int(numero_txt)
        if i < 1:
            return ("🔎 Uso: /v14_favoritismo [coorte|631|snapshot 631]\n"
                    "🔒 Apenas OWNER, sem consultas nem alterações.")
        if i > len(dados) or not isinstance(dados[i-1], dict):
            return f"⚪ Snapshot #{i} inexistente. Nenhum dado foi alterado."
        if dados[i-1].get("modelo_versao") != "V1.2":
            return f"⚪ Snapshot #{i} não é V1.2. Nenhuma versão foi alterada."
        selected = [(i, dados[i-1])]
        universo = "snapshot individual (auditoria exploratória)"

    avaliados = [a for i, p in selected if (a := avaliar_snapshot(i, p)) is not None]
    completos = [a for a in avaliados if a["completo"]]
    alertas = [a for a in completos if a["alerta"]]
    mercados = Counter(a["mercado"] for a in alertas)
    ligas = Counter(a["liga"] for a in alertas)
    linhas = [
        "🔬 V1.4 SHADOW — PPG × GOLOS ESPERADOS (READ-ONLY)",
        f"🔒 Universo: {universo}",
        f"📚 Previsões totais: {len(selected)} | Mercados de vitória: {len(avaliados)}",
        f"📊 Com PPG e lambdas: {len(completos)} | Dados incompletos: {len(avaliados) - len(completos)}",
        f"⚠️ Inversão expressiva: {len(alertas)}/{len(completos)}"
        if completos else "⚠️ Inversão expressiva: sem base avaliável",
        "📏 Critério diagnóstico: PPG do adversário ≥1,0 ponto superior;"
        " lambda do favorito do modelo ≥0,75 golo superior",
    ]
    if mercados:
        linhas.append("⚽ Mercados: " + "; ".join(f"{m} ({n})" for m, n in mercados.most_common()))
        linhas.append("🏆 Competições: " + "; ".join(f"{m} ({n})" for m, n in ligas.most_common(5)))
    mostra = avaliados if len(selected) == 1 else sorted(
        alertas, key=lambda a: (-a["inversao_ppg"], -a["vantagem_lambda"], a["indice"])
    )[:MAX_CASOS]
    for a in mostra:
        linhas.extend(["", "━━━━━━━━━━━━━━━━━━━━",
                      f"#{a['indice']} {a['data']} {_txt(a['jogo'], 72)}",
                      f"🎯 {a['mercado']} | {_txt(a['liga'])}"])
        if not a["completo"]:
            linhas.append("⚪ Sem telemetria original suficiente. Não reconstruir PPG/lambdas.")
            continue
        linhas.extend([
            f"📈 Prob. modelo {a['prob']*100:.1f}% | Qualidade {a['qualidade'] if a['qualidade'] is not None else '?'}",
            f"📉 PPG casa {a['ppg_casa']:.3f} | fora {a['ppg_fora']:.3f}"
            f" | oposição {a['inversao_ppg']:+.3f}",
            f"⚽ Lambda casa {a['lambda_casa']:.3f} | fora {a['lambda_fora']:.3f}"
            f" | vantagem pick {a['vantagem_lambda']:+.3f}",
            f"📡 Forma: {_txt(a['forma_fonte'])}"
            f" | locais casa/fora: {a['amostra_casa_local'] if a['amostra_casa_local'] is not None else '?'}"
            f"/{a['amostra_fora_local'] if a['amostra_fora_local'] is not None else '?'}",
            "⚠️ Divergência expressiva" if a["alerta"] else "ℹ️ Sem inversão acima dos limiares",
        ])
    if not mostra:
        linhas.append("⚪ Nenhum caso com inversão acima dos limiares neste universo.")
    linhas.extend([
        "",
        "ℹ️ PPG usa forma geral recente; lambdas usam GF/GA por casa/fora e médias da competição. São medidas distintas.",
        "ℹ️ Qualidade 100 mede cobertura, não garante previsões calibradas.",
        "⚠️ Limiares definidos depois de analisar #631: NÃO demonstram erro, edge ou rentabilidade.",
        "🔒 Zero HTTP / zero escrita / sem tocar a V1.2, V1.3, apostas, odds, ROI ou CLV.",
    ])
    return "\n".join(linhas)
