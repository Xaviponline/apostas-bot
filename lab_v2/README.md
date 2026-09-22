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

## Ideias futuras já aprovadas

### Alertas automáticos pré-jogo

- Cerca de 1 hora antes do kickoff, verificar se o jogo já tinha sido selecionado pelo modelo do dia.
- Enviar no Telegram apenas o cartão desse jogo, com mercado recomendado, probabilidade, odd justa, odd mínima e nível de confiança.
- Garantir que o mesmo jogo não gera alertas duplicados.
- Este módulo não altera a previsão original; apenas relembra uma seleção que já existia antes do jogo.

### Motor Live separado

- Desenvolver apenas depois de existir uma fonte live suficientemente rica, estável e licenciada.
- Usar minuto, marcador, remates, remates à baliza, cantos, cartões, pressão/forma ofensiva recente, xG quando disponível e outras métricas verificadas.
- Procurar oportunidades como Over 0.5/1.5, próximo golo e outros mercados live apenas quando houver validação histórica.
- Não assumir que "muito ataque" implica automaticamente aposta; o sinal live deve ter modelo e backtesting próprios.
- O motor Live deve ser totalmente separado da V1 pré-jogo e ter auditoria/performance próprias.

## Critério de promoção

A V2 não substitui a V1 por parecer melhor num dia. Deve apresentar melhoria consistente em amostra fora do treino, sobretudo em Brier Score/calibração e, quando houver odds históricas, ROI/CLV por mercado.