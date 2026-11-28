"""Acompanhamento PROSPETIVO Lambda V1.4 congelado, SHADOW e só leitura.

A validação começa em 28/11/2026, 00:00 em Portugal. Os jogos anteriores
não contam para a nova amostra, evitando misturar calibração exploratória
com validação posterior. Não modifica a mistura Lambda 60/40 nem o modelo.
"""
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from lambda_cobertura_shadow import _captura_pre_jogo, _indices_independentes, _vetor
from lambda_resultados_shadow import identidade, ler
from lambda_robustez_shadow import _intervalo_clusters

PORTUGAL = ZoneInfo("Europe/Lisbon")
INICIO_LOCAL = datetime(2026, 11, 28, 0, 0, tzinfo=PORTUGAL)
META_JOGOS = 200
META_DIAS = 20
MERCADOS = ("Vitória Casa", "Empate", "Vitória Fora")


def _amostra_nova(caminho):
    """Junta previsões prospectivas e resultados ESPN sem aproximações."""
    fim = Path(caminho).with_name("lambda_prospectivo_resultados.jsonl")
    finais, conflitos = _indices_independentes(fim)
    unicos = set()
    contagens = Counter()
    jogos = []
    dias_captura = set()
    datas_jogos = set()
    ultima_captura = None
    for reg in ler(caminho):
        if reg.get("versao") != 1 or not _vetor(reg):
            contagens["registo_invalido"] += 1
            continue
        try:
            k = identidade(reg["jogo"], reg["liga_codigo"])
            chave = reg["chave"]
            if k is None or not isinstance(chave, str) or not chave:
                contagens["identidade_invalida"] += 1
                continue
            captura = datetime.fromisoformat(str(reg["capturado_em_utc"]).replace("Z", "+00:00"))
            if captura.tzinfo is None or captura.utcoffset() is None:
                contagens["captura_invalida"] += 1
                continue
            inicio = datetime.fromtimestamp(k[-1], PORTUGAL)
            if captura < INICIO_LOCAL or inicio < INICIO_LOCAL:
                contagens["anterior_corte"] += 1
                continue
            par = (chave, k)
            if par in unicos:
                contagens["duplicado"] += 1
                continue
            unicos.add(par)
            if not _captura_pre_jogo(reg, k):
                contagens["captura_nao_prejogo"] += 1
                continue
            contagens["prejogo"] += 1
            dia = inicio.date().isoformat()
            datas_jogos.add(dia)
            dias_captura.add(captura.astimezone(PORTUGAL).date().isoformat())
            if ultima_captura is None or captura > ultima_captura:
                ultima_captura = captura
            if par in conflitos:
                contagens["final_conflitante"] += 1
                continue
            if par not in finais:
                contagens["sem_final_espn"] += 1
                continue
            gc, gf = finais[par]
            verdade = (1, 0, 0) if gc > gf else ((0, 1, 0) if gc == gf else (0, 0, 1))
            p = [float(reg["original_1x2"][m]) for m in MERCADOS]
            q = [float(reg["alternativa_1x2"][m]) for m in MERCADOS]
            a = sum((x-y)**2 for x, y in zip(p, verdade)) / 3
            b = sum((x-y)**2 for x, y in zip(q, verdade)) / 3
            jogos.append({"liga": str(reg["liga_codigo"]), "dia": dia,
                          "original": a, "alternativa": b, "delta": b-a})
        except (KeyError, ValueError, TypeError, OverflowError):
            contagens["registo_invalido"] += 1
    return jogos, contagens, datas_jogos, dias_captura, ultima_captura


def relatorio_lambda_validacao(caminho_snapshots):
    """Gate de ACOMPANHAMENTO, jamais aprovação ou promoção automática."""
    linhas = [
        "🧪 LAMBDA VALIDAÇÃO FUTURA — V1.4 SHADOW",
        "🔒 Apenas leitura; zero APIs, zero escrita, V1.2/V1.3 intactas.",
        "🔐 Mistura Lambda 60/40 congelada. Corte: 28/11/2026 00:00 (Portugal).",
        "ℹ️ Os 87 jogos da investigação anterior NÃO entram nesta amostra nova.",
    ]
    caminho = Path(caminho_snapshots)
    if not caminho.is_file():
        return "\n".join(linhas + ["📭 Ainda sem snapshots no volume."])
    jogos, cnt, datas_jogos, dias_captura, ultima = _amostra_nova(caminho)
    n = len(jogos)
    dias_finais = len({j["dia"] for j in jogos})
    linhas.extend([
        f"📚 Novos snapshots pré-jogo: {cnt['prejogo']} | finais ESPN exatos: {n} | sem final: {cnt['sem_final_espn']}",
        f"📅 Dias com snapshots: {len(datas_jogos)} | dias com resultados: {dias_finais}",
        f"🎯 Meta de observação: {n}/{META_JOGOS} resultados e {dias_finais}/{META_DIAS} dias com resultados",
    ])
    if ultima is not None:
        linhas.append(f"🕒 Última captura pré-jogo: {ultima.astimezone(PORTUGAL):%d/%m/%Y %H:%M} (Portugal)")
    if cnt["final_conflitante"]:
        linhas.append(f"⚠️ Finais ESPN contraditórios excluídos: {cnt['final_conflitante']}")
    if cnt["captura_nao_prejogo"]:
        linhas.append(f"⚠️ Capturas tardias excluídas: {cnt['captura_nao_prejogo']}")
    if n:
        a = sum(j["original"] for j in jogos) / n
        b = sum(j["alternativa"] for j in jogos) / n
        linhas.append(f"📊 Brier nova amostra: original {a:.4f} | alternativa 40% {b:.4f} | Δ {b-a:+.4f}")
        ganhos = sum(j["delta"] < -1e-12 for j in jogos)
        perdas = sum(j["delta"] > 1e-12 for j in jogos)
        linhas.append(f"⚖️ Jogo a jogo: melhora {ganhos} | piora {perdas} | igual {n-ganhos-perdas}")
    else:
        linhas.append("⏳ Ainda não há resultados ESPN confirmados nesta amostra futura.")

    # O número de dias, não só a quantidade de jogos, limita a confiança.
    if n >= META_JOGOS and dias_finais >= META_DIAS:
        ci_dia, nd = _intervalo_clusters(jogos, lambda j: j["dia"])
        ci_grupo, ng = _intervalo_clusters(jogos, lambda j: (j["dia"], j["liga"]))
        if ci_dia is not None and ci_grupo is not None:
            linhas.append(f"📐 IC exploratório 95% Δ (por dia; {nd} dias): [{ci_dia[0]:+.4f}; {ci_dia[1]:+.4f}]")
            linhas.append(f"📐 IC exploratório 95% Δ (dia×liga; {ng} grupos): [{ci_grupo[0]:+.4f}; {ci_grupo[1]:+.4f}]")
            if ci_dia[1] < 0 and ci_grupo[1] < 0:
                linhas.append("🔎 Sinal de menor Brier nas duas análises; requer revisão humana e nova validação.")
            else:
                linhas.append("🔎 Superioridade não confirmada em ambos os intervalos; continuar observação.")
        else:
            linhas.append("⚠️ Grupos insuficientes para os intervalos.")
    else:
        linhas.append("🛡️ RECOLHA: amostra/dias insuficientes. IC e decisão de promoção bloqueados.")
    linhas.extend([
        "⚠️ Metas operacionais, não prova estatística nem garantia de rentabilidade.",
        "🔒 Nunca promove automaticamente variantes nem ajusta pesos por liga.",
    ])
    return "\n".join(linhas)
