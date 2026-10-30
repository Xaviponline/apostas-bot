"""Motor genérico de backtesting walk-forward para o laboratório V2.

O predictor recebe apenas jogos anteriores ao kickoff do jogo alvo. Este ficheiro
não conhece a implementação da V1/V2 e não é usado pelo bot de produção.
"""
from collections import defaultdict


def executar_walk_forward(jogos, predictor, resolver_resultado, min_historico=10):
    """Executa previsões cronologicamente sem disponibilizar o futuro ao predictor.

    `jogos` deve conter dicts com `timestamp`, `liga` e os campos necessários ao
    predictor/resolver. `predictor(historico, jogo)` devolve uma lista de dicts com
    pelo menos `mercado` e `probabilidade`. `resolver_resultado(jogo, mercado)`
    devolve 0/1 ou None quando o mercado não puder ser liquidado.
    """
    ordenados = sorted(
        [j for j in jogos if isinstance(j, dict) and isinstance(j.get("timestamp"), (int, float))],
        key=lambda j: j["timestamp"],
    )
    historico_por_liga = defaultdict(list)
    saida = []

    for jogo in ordenados:
        liga = str(jogo.get("liga") or "")
        historico = list(historico_por_liga[liga])

        if len(historico) >= int(min_historico):
            previsoes = predictor(historico, dict(jogo)) or []
            for previsao in previsoes:
                if not isinstance(previsao, dict):
                    continue
                mercado = previsao.get("mercado")
                prob = previsao.get("probabilidade")
                if mercado is None or prob is None:
                    continue
                resultado = resolver_resultado(jogo, mercado)
                if resultado not in (0, 1):
                    continue
                saida.append({
                    "event_id": jogo.get("id"),
                    "liga": liga,
                    "timestamp_jogo": jogo["timestamp"],
                    "mercado": str(mercado),
                    "probabilidade": float(prob),
                    "resultado": int(resultado),
                    "historico_disponivel": len(historico),
                })

        # Só depois de prever o jogo atual é que este entra no histórico.
        historico_por_liga[liga].append(dict(jogo))

    return saida
