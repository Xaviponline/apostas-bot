"""Auditoria estatística local do Lambda 1X2: comparação EMPARELHADA SHADOW.

Usa exclusivamente previsões guardadas antes do jogo e resultados ESPN
independentes, conciliados por chave, IDs, liga e kickoff exatos.
Não consulta APIs nem modifica qualquer ficheiro, seleção ou modelo.
"""
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from random import Random
from zoneinfo import ZoneInfo

from lambda_cobertura_shadow import _captura_pre_jogo, _indices_independentes, _vetor
from lambda_resultados_shadow import identidade, ler

MERCADOS = ("Vitória Casa", "Empate", "Vitória Fora")
PORTUGAL = ZoneInfo("Europe/Lisbon")
REPETICOES = 4000
SEMENTE = 20261128


def _jogos_emparelhados(caminho):
    """Registos pré-jogo com um único final ESPN de identidade completa."""
    caminho = Path(caminho)
    finais, conflitos = _indices_independentes(
        caminho.with_name("lambda_prospectivo_resultados.jsonl")
    )
    vistos = set()
    motivos = Counter()
    jogos = []
    for r in ler(caminho):
        if r.get("versao") != 1 or not _vetor(r):
            motivos["vetor_invalido"] += 1
            continue
        try:
            ident = identidade(r["jogo"], r["liga_codigo"])
            chave = r["chave"]
            if ident is None or not isinstance(chave, str) or not chave:
                motivos["identidade_invalida"] += 1
                continue
            par = (chave, ident)
            if par in vistos:
                motivos["duplicado"] += 1
                continue
            vistos.add(par)
            if not _captura_pre_jogo(r, ident):
                motivos["nao_pre_jogo"] += 1
                continue
            if par in conflitos:
                motivos["final_conflitante"] += 1
                continue
            if par not in finais:
                motivos["sem_final_espn"] += 1
                continue
            gc, gf = finais[par]
            y = (1, 0, 0) if gc > gf else ((0, 1, 0) if gc == gf else (0, 0, 1))
            a = [float(r["original_1x2"][m]) for m in MERCADOS]
            b = [float(r["alternativa_1x2"][m]) for m in MERCADOS]
            brier_a = sum((p - t) ** 2 for p, t in zip(a, y)) / 3
            brier_b = sum((p - t) ** 2 for p, t in zip(b, y)) / 3
            jogos.append({
                "chave": chave,
                "liga": str(r["liga_codigo"]),
                "dia": datetime.fromtimestamp(ident[-1], PORTUGAL).date().isoformat(),
                "original": brier_a,
                "alternativa": brier_b,
                "delta": brier_b - brier_a,
            })
        except (KeyError, TypeError, ValueError, OverflowError):
            motivos["registo_invalido"] += 1
    return jogos, motivos


def _percentil(valores_ordenados, q):
    """Percentil linear, sem NumPy ou dependências adicionais."""
    n = len(valores_ordenados)
    k = (n - 1) * q
    baixo = int(k)
    fracao = k - baixo
    return valores_ordenados[baixo] * (1 - fracao) + valores_ordenados[min(baixo + 1, n - 1)] * fracao


def _intervalo_clusters(jogos, chave_grupo, repeticoes=REPETICOES):
    """Bootstrap de clusters com reposição, ponderando pelo número de jogos.

    Cada replicação reamostra o mesmo número de grupos; todos os jogos de
    um grupo são preservados em conjunto. Percentis exploratórios, sem p-value.
    """
    grupos = defaultdict(list)
    for jogo in jogos:
        grupos[chave_grupo(jogo)].append(jogo["delta"])
    agregados = [(sum(v), len(v)) for _, v in sorted(grupos.items())]
    if len(agregados) < 2:
        return None, len(agregados)
    rng = Random(SEMENTE)
    n_grupos = len(agregados)
    simulados = []
    for _ in range(repeticoes):
        total, quantidade = 0.0, 0
        for _ in range(n_grupos):
            soma, n = agregados[rng.randrange(n_grupos)]
            total += soma
            quantidade += n
        simulados.append(total / quantidade)
    simulados.sort()
    return (_percentil(simulados, .025), _percentil(simulados, .975)), n_grupos


def relatorio_lambda_robustez(caminho_snapshots):
    """Relatório independente, determinístico e estritamente de leitura."""
    linhas = [
        "🧪 LAMBDA ROBUSTEZ — 1X2 SHADOW",
        "🔒 Apenas ficheiros locais; zero HTTP, zero escrita, V1.2/V1.3 intactas.",
    ]
    caminho = Path(caminho_snapshots)
    if not caminho.is_file():
        return "\n".join(linhas + ["📭 Sem snapshots Lambda no volume."])
    jogos, motivos = _jogos_emparelhados(caminho)
    n = len(jogos)
    linhas.append(f"📚 Jogos pré-jogo com final ESPN independente exato: {n}")
    if motivos:
        linhas.append("🔎 Excluídos: " + "; ".join(
            f"{k}={v}" for k, v in sorted(motivos.items()) if v
        ))
    if n < 2:
        return "\n".join(linhas + ["⏳ Amostra insuficiente para auditoria emparelhada."])

    original = sum(j["original"] for j in jogos) / n
    alternativa = sum(j["alternativa"] for j in jogos) / n
    delta = alternativa - original
    ganhos = sum(j["delta"] < -1e-12 for j in jogos)
    perdas = sum(j["delta"] > 1e-12 for j in jogos)
    empates = n - ganhos - perdas
    linhas.extend([
        f"📊 Brier original {original:.4f} | alternativa 40% {alternativa:.4f} | Δ {delta:+.4f}",
        f"⚖️ Jogo a jogo: alternativa melhor {ganhos} | pior {perdas} | igual {empates}",
    ])

    ci_grupo, ng = _intervalo_clusters(jogos, lambda j: (j["dia"], j["liga"]))
    ci_dia, nd = _intervalo_clusters(jogos, lambda j: j["dia"])
    if ci_grupo is not None:
        linhas.append(
            f"📐 IC exploratório 95% Δ (bootstrap dia×liga, {ng} grupos): "
            f"[{ci_grupo[0]:+.4f}; {ci_grupo[1]:+.4f}]"
        )
    if ci_dia is not None:
        linhas.append(
            f"📐 Sensibilidade por dia (bootstrap, {nd} dias): "
            f"[{ci_dia[0]:+.4f}; {ci_dia[1]:+.4f}]"
        )
    if ci_grupo is None or ci_dia is None:
        linhas.append("⚠️ Grupos insuficientes para um dos intervalos.")

    ligas = Counter(j["liga"] for j in jogos)
    soma_por_liga = Counter()
    for j in jogos:
        soma_por_liga[j["liga"]] += j["delta"]
    linhas.append("🏆 Retirando uma liga de cada vez (Δ no conjunto restante):")
    invertidas = []
    detalhes = []
    for liga, contagem in sorted(ligas.items(), key=lambda item: (-item[1], item[0])):
        if n == contagem:
            continue
        sem = (sum(j["delta"] for j in jogos) - soma_por_liga[liga]) / (n - contagem)
        detalhes.append((liga, contagem, sem))
        if sem >= 0:
            invertidas.append(liga)
    for liga, contagem, sem in detalhes[:10]:
        linhas.append(f"• sem {liga} (n={contagem}): Δ {sem:+.4f}")
    if len(detalhes) > 10:
        linhas.append(f"• Outras {len(detalhes)-10} ligas analisadas (não apresentadas).")
    linhas.append(
        "⚠️ Inversão de vantagem ao excluir uma liga: "
        + (", ".join(invertidas) if invertidas else "nenhuma")
    )
    linhas.extend([
        "ℹ️ Δ negativo favorece a alternativa. ICs são exploratórios, dependem da amostra",
        "   ESPN disponível e do agrupamento; não comprovam vantagem futura ou ROI.",
        "🔒 Não ajustar os 40% por liga com esta amostra. Sem promoção automática.",
    ])
    return "\n".join(linhas)
