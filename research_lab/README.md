# Research Lab v1

Laboratório isolado do motor de produção. A V1.2/SEL1 continua a ser o **Champion**;
nenhum resultado deste pacote altera previsões, thresholds, mercados ou snapshots.

## Fluxo

1. O bot de produção cria uma cópia sanitizada e hashada dos snapshots.
2. A cópia é enviada por rede privada para `research-lab`.
3. O serviço guarda o dataset em Railway Object Storage.
4. Os challengers são avaliados apenas com previsões **walk-forward/out-of-sample**.
5. Optuna só afina hiperparâmetros dentro do passado de cada fold.
6. Métricas e artefactos são registados em MLflow persistente no volume isolado do `research-lab`.
7. Mesmo um challenger vencedor fica em shadow. Promoção exige um novo teste
   prospetivo pré-registado.

## Challengers iniciais

- `platt_calibration_v1`: recalibração logística da probabilidade V1.2.
- `meta_logit_v1`: meta-modelo logístico com probabilidades congeladas,
  ranking, qualidade e telemetria (lambdas, PPG, amostra e margem).

O objetivo inicial é construir disciplina experimental e detectar calibração,
drift e melhorias reproduzíveis. Modelos mais complexos (CatBoost/LightGBM,
ensembles e dados externos) só devem entrar depois desta infraestrutura estar
estável e com amostra suficiente.

## Serviços Railway

- `research-lab`: API privada, walk-forward, Optuna e MLflow persistente num volume próprio.
- `research-data`: Object Storage para datasets e relatórios.

O MLflow usa SQLite + artefactos locais no volume `/lab`, evitando um servidor
MLflow adicional e reduzindo consumo de memória/custo no Railway.

Nenhum destes serviços recebe ficheiros de acessos Premium, tokens Telegram ou
outros dados de clientes.
