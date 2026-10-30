"""Ferramentas de avaliação para o laboratório V2.

Este módulo não é importado pelo bot de produção. Mede apenas qualidade
probabilística; ROI/EV exigem odds históricas reais.
"""
from collections import defaultdict
from math import log


def _clip_probabilidade(p, eps=1e-9):
    p = float(p)
    if not 0.0 <= p <= 1.0:
        raise ValueError("Probabilidade fora de [0,1].")
    return min(1.0 - eps, max(eps, p))


def brier_score(previsoes):
    dados = list(previsoes)
    if not dados:
        return None
    soma = 0.0
    for item in dados:
        p = _clip_probabilidade(item["probabilidade"])
        y = int(item["resultado"])
        if y not in (0, 1):
            raise ValueError("Resultado binário inválido.")
        soma += (p - y) ** 2
    return soma / len(dados)


def log_loss(previsoes):
    dados = list(previsoes)
    if not dados:
        return None
    soma = 0.0
    for item in dados:
        p = _clip_probabilidade(item["probabilidade"])
        y = int(item["resultado"])
        if y not in (0, 1):
            raise ValueError("Resultado binário inválido.")
        soma += -(y * log(p) + (1 - y) * log(1 - p))
    return soma / len(dados)


def taxa_acerto(previsoes, limiar=0.5):
    dados = list(previsoes)
    if not dados:
        return None
    corretas = 0
    for item in dados:
        p = _clip_probabilidade(item["probabilidade"])
        y = int(item["resultado"])
        correta = int(p >= limiar) == y
        corretas += int(correta)
    return corretas / len(dados)


def calibracao(previsoes, largura=0.10):
    """Agrupa previsões por intervalo e compara confiança média com frequência real."""
    if largura <= 0 or largura > 1:
        raise ValueError("Largura de calibração inválida.")
    caixas = defaultdict(list)
    for item in previsoes:
        p = _clip_probabilidade(item["probabilidade"])
        y = int(item["resultado"])
        if y not in (0, 1):
            raise ValueError("Resultado binário inválido.")
        indice = min(int(p / largura), int(1 / largura) - 1)
        caixas[indice].append((p, y))

    saida = []
    for indice in sorted(caixas):
        valores = caixas[indice]
        n = len(valores)
        p_media = sum(p for p, _ in valores) / n
        freq = sum(y for _, y in valores) / n
        saida.append({
            "inicio": round(indice * largura, 4),
            "fim": round(min(1.0, (indice + 1) * largura), 4),
            "n": n,
            "probabilidade_media": p_media,
            "frequencia_real": freq,
            "erro_calibracao": abs(p_media - freq),
        })
    return saida


def resumo(previsoes):
    dados = list(previsoes)
    return {
        "n": len(dados),
        "brier": brier_score(dados),
        "log_loss": log_loss(dados),
        "taxa_acerto": taxa_acerto(dados),
        "calibracao": calibracao(dados) if dados else [],
    }


def resumo_por_mercado(previsoes):
    grupos = defaultdict(list)
    for item in previsoes:
        grupos[str(item.get("mercado") or "desconhecido")].append(item)
    return {mercado: resumo(dados) for mercado, dados in sorted(grupos.items())}


def validar_sem_lookahead(registos):
    """Falha se alguma previsão tiver sido criada no/apos o kickoff."""
    for item in registos:
        criado = item.get("timestamp_previsao")
        kickoff = item.get("timestamp_jogo")
        if criado is None or kickoff is None:
            raise ValueError("Timestamps obrigatórios para validar look-ahead.")
        if float(criado) >= float(kickoff):
            raise ValueError("Look-ahead detetado: previsão criada no/apos kickoff.")
    return True
