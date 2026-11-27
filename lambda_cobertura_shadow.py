"""Cobertura dos resultados Lambda 1X2 — auditoria estritamente local.

Compara associações oficiais por ID e confirmações independentes por
identidade completa, sem APIs, escritura, reconstrução ou recomputar apostas.
Não altera nem corrige o relatório /lambda_prospectivo original.
"""
from collections import Counter
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path

from lambda_resultados_shadow import identidade, ler

MERCADOS = ("Vitória Casa", "Empate", "Vitória Fora")


def _placar(reg):
    try:
        gc, gf = reg["golos_casa"], reg["golos_fora"]
        if isinstance(gc, bool) or isinstance(gf, bool):
            return None
        a, b = int(gc), int(gf)
        if min(a, b) < 0 or float(gc) != a or float(gf) != b:
            return None
        return (a, b)
    except (TypeError, ValueError, KeyError, OverflowError):
        return None


def _vetor(reg):
    for campo in ("original_1x2", "alternativa_1x2"):
        probs = reg.get(campo)
        if not isinstance(probs, dict):
            return False
        try:
            valores = [float(probs[m]) for m in MERCADOS]
        except (ValueError, TypeError, KeyError, OverflowError):
            return False
        if any(not isfinite(x) or not 0 <= x <= 1 for x in valores):
            return False
        if abs(sum(valores) - 1) > .02:
            return False
    return True


def _captura_pre_jogo(reg, ident):
    try:
        data = datetime.fromisoformat(str(reg["capturado_em_utc"]).replace("Z", "+00:00"))
        return data.tzinfo is not None and data.utcoffset() is not None and data.timestamp() < ident[-1]
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _indices_oficiais(dados):
    """Segue a junção histórica por event ID, identificando conflitos de placar."""
    finais, conflitos = {}, set()
    for p in (dados or {}).get("previsoes", []):
        if not isinstance(p, dict) or p.get("resultado_binario") not in (0, 1):
            continue
        placar = _placar(p)
        if placar is None:
            continue
        try:
            eid = int(p["event_id"])
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
        if eid in finais and finais[eid] != placar:
            conflitos.add(eid)
        finais[eid] = placar
    return finais, conflitos


def _indices_independentes(destino):
    """Exige fonte ESPN_STATUS_FINAL, identidade completa e placar único."""
    finais, conflitos = {}, set()
    for reg in ler(destino):
        try:
            if reg.get("fonte") != "ESPN_STATUS_FINAL":
                continue
            k = identidade(reg["jogo"], reg["liga_codigo"])
            chave = reg["chave"]
            placar = _placar(reg)
            if k is None or not isinstance(chave, str) or not chave or placar is None:
                continue
            par = (chave, k)
            if par in finais and finais[par] != placar:
                conflitos.add(par)
            finais[par] = placar
        except (TypeError, ValueError, KeyError, OverflowError):
            continue
    return finais, conflitos


def relatorio_lambda_cobertura(caminho_snapshots, dados, agora=None):
    """Separação explícita: ID oficial vs identidade estrita ESPN, pré-jogo."""
    agora = agora or datetime.now(timezone.utc)
    if agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError("É necessário um relógio com fuso horário")
    caminho = Path(caminho_snapshots)
    linhas = [
        "🔎 LAMBDA COBERTURA — AUDITORIA DE RESULTADOS (SHADOW)",
        "🔒 Apenas ficheiros locais; sem pedidos ESPN/OddsPapi.",
    ]
    if not caminho.is_file():
        return "\n".join(linhas + ["📭 Ficheiro prospetivo não disponível."])

    oficiais, conflitos_of = _indices_oficiais(dados)
    independentes, conflitos_ind = _indices_independentes(
        caminho.with_name("lambda_prospectivo_resultados.jsonl")
    )
    contagem = Counter()
    faltas_espn = Counter()
    repetidos = set()
    agora_ts = agora.timestamp()
    for r in ler(caminho):
        if r.get("versao") != 1 or not _vetor(r):
            contagem["invalido"] += 1
            continue
        contagem["validos"] += 1
        try:
            k = identidade(r["jogo"], r["liga_codigo"])
            chave = r["chave"]
            if k is None or not isinstance(chave, str) or not chave:
                contagem["identidade_invalida"] += 1
                continue
            par = (chave, k)
            if par in repetidos:
                contagem["duplicados"] += 1
                continue
            repetidos.add(par)
            if not _captura_pre_jogo(r, k):
                contagem["captura_nao_prejogo"] += 1
                continue
            contagem["pre_jogo"] += 1
            if k[-1] > agora_ts:
                contagem["jogos_futuros"] += 1
            else:
                contagem["jogos_iniciados"] += 1

            eid = k[1]
            tem_of = eid in oficiais and eid not in conflitos_of
            tem_ind = par in independentes and par not in conflitos_ind
            if tem_of:
                contagem["oficial_id"] += 1
            if tem_ind:
                contagem["independente_exata"] += 1
            if tem_of and tem_ind:
                contagem["sobreposicao"] += 1
                if oficiais[eid] != independentes[par]:
                    contagem["placar_divergente"] += 1
            if not tem_of and not tem_ind:
                contagem["sem_resultado"] += 1
            if k[-1] <= agora_ts and not tem_ind:
                faltas_espn[str(r["liga_codigo"] or "desconhecida")] += 1
        except (KeyError, TypeError, ValueError, OverflowError):
            contagem["identidade_invalida"] += 1

    linhas.extend([
        f"📚 Registos V1 com vetores 1X2 válidos: {contagem['validos']}",
        f"⚠️ Linhas inválidas/sem vetor: {contagem['invalido']}"
        f" | identidade incompleta: {contagem['identidade_invalida']}"
        f" | duplicadas: {contagem['duplicados']}",
        f"🕒 Captura pré-jogo comprovada: {contagem['pre_jogo']}"
        f" | não comprovada/fora do prazo: {contagem['captura_nao_prejogo']}",
        f"⚽ Dessas capturas pré-jogo: {contagem['jogos_iniciados']} jogos já iniciados"
        f" | {contagem['jogos_futuros']} por iniciar",
        "",
        "📊 ASSOCIAÇÃO DOS RESULTADOS (só snapshots com captura pré-jogo comprovada)",
        f"• Placar no histórico oficial por ID do evento: {contagem['oficial_id']}",
        f"• Placar ESPN independente por IDs+liga+horário+chave: {contagem['independente_exata']}",
        f"• Sobreposição entre ambos: {contagem['sobreposicao']}",
        f"• Placares discordantes na sobreposição: {contagem['placar_divergente']}",
        f"• Sem resultado em nenhuma das duas fontes: {contagem['sem_resultado']}",
    ])
    if faltas_espn:
        linhas.append("🏆 Mais snapshots antigos/iniciados sem confirmação ESPN exata: "
                      + "; ".join(f"{liga} ({n})" for liga, n in faltas_espn.most_common(7)))
    linhas.extend([
        "",
        "ℹ️ O resultado oficial é associado só pelo ID, tal como o relatório Lambda original;"
        " a confirmação independente exige identidade completa.",
        "ℹ️ A análise não prova que partidas sem resultado estejam pendentes;"
        " podem simplesmente não ter sido reconciliadas com a ESPN.",
        "ℹ️ Contagens aqui podem diferir do /lambda_prospectivo porque este diagnóstico"
        " exige captura anterior ao início e validação de identidade.",
        "🔒 Zero HTTP / zero escrita: sem alterar snapshots, previsões, resultados,"
        " odds, V1.2, V1.3, ROI ou CLV.",
    ])
    return "\n".join(linhas)
