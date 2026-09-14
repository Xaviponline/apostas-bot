# Laboratório V2

Este diretório existe para desenvolver e validar a próxima geração do modelo sem alterar o comportamento do `/analisa` em produção.

## Regras

- A V1 em `main` continua congelada para acumular previsões auditáveis.
- Nada neste diretório é importado pelo bot de produção.
- Qualquer melhoria só pode chegar à produção depois de backtesting walk-forward e comparação objetiva com a V1.
- Nunca usar dados posteriores ao kickoff para prever um jogo histórico.
- Nunca calcular ROI sem odds históricas reais.

## Ordem de trabalho

1. Backtesting walk-forward da qualidade probabilística.
2. Métricas por mercado: Brier Score, log loss, taxa de acerto e calibração.
3. Recência e força dos adversários/Elo.
4. Testar Dixon-Coles como alternativa ao Poisson independente.
5. Acrescentar fontes licenciadas de estatísticas avançadas: remates, remates à baliza, cantos, cartões e xG quando disponível.
6. Odds multi-casa e EV apenas quando existirem odds reais.
7. Comparar V1 vs V2 em amostra fora do treino antes de promover a V2.

## Critério de promoção

A V2 não substitui a V1 por parecer melhor num dia. Deve apresentar melhoria consistente em amostra fora do treino, sobretudo em Brier Score/calibração e, quando houver odds históricas, ROI/CLV por mercado.