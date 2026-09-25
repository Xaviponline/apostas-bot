# PROJECT STATE — Apostas Bot

Última atualização: 2026-09-25

Este ficheiro é a fonte de continuidade do projeto `Xaviponline/apostas-bot`. Não contém chaves, tokens ou outros segredos. As credenciais continuam apenas nas variáveis do Railway.

## Objetivo

Bot Telegram de análise de apostas de futebol com previsões auditáveis, controlo de risco, probabilidades próprias, odds reais quando disponíveis e histórico append-only.

A casa de apostas de referência é a Betano Portugal.

## Infraestrutura

- GitHub: `Xaviponline/apostas-bot`
- Railway: projeto `cheerful-prosperity`
- Serviço principal: `apostas-bot`
- Ambiente de produção: Railway prod
- Volume persistente: `/data`
- Processo: `python main_competicoes.py`
- Pre-deploy: `python -m unittest discover -s tests -v`
- Último estado verificado: Railway SUCCESS
- Suite atual verificada: 127 testes OK

Regra operacional: commits em `main` fazem auto-deploy no Railway. Não usar `accept-deploy` para deployments originados por GitHub.

## Modelo atual

Versão ativa: **V1.2**

A V1.2 está congelada até haver aproximadamente **40 previsões V1.2 liquidadas**. Não alterar fórmulas, thresholds ou lógica de ranking antes disso, salvo correções de bugs que não alterem retroativamente previsões já registadas.

### Mecânica V1.2

Probabilidade conservadora:

```text
p = 0.5 + (p_bruta - 0.5) * 0.80
```

Ranking:
- score = probabilidade ajustada
- desempate por probabilidade bruta
- qualidade dos dados não entra no ranking

Confiança por probabilidade:
- ALTA: >= 0.68
- MÉDIA-ALTA: >= 0.64
- MÉDIA: >= 0.60
- BAIXA: abaixo de 0.60

Qualidade mínima: 55

Thresholds atuais:
- Vitória Casa: 0.56
- Vitória Fora: 0.56
- Ambas Marcam: 0.58
- Over 2.5: 0.57
- Under 2.5: 0.58
- Under 3.5: 0.64
- Over 1.5: 0.70
- 1X: 0.70
- X2: 0.70

Outros:
- margem alvo de value: 5%
- odd mínima de perfil: 1.50
- máximo de 20 seleções por análise

## Estado estatístico global

Último `/performance` confirmado:

- Previsões registadas: 97
- Liquidadas: 97
- Pendentes: 0
- Acertos: 54
- Falhas: 43
- Taxa de acerto: 55.7%
- Brier Score: 0.2590

Por versão:
- V1.0: 29/50 = 58.0% | Brier 0.2457
- V1.1: 11/20 = 55.0% | Brier 0.2595
- V1.2: 14/27 = 51.9% | Brier 0.2834

## V1.2 APENAS — estado atual

Global:
- 14/27 = 51.9%
- Brier 0.2834
- Previsto médio: 66.1%
- Real: 51.9%
- Gap: -14.3 pp

Mercados:
- Ambas Marcam: 2/3 = 66.7% | Brier 0.2180
- Over 2.5: 3/6 = 50.0% | Brier 0.2868
- Under 2.5: 3/6 = 50.0% | Brier 0.2857
- Under 3.5: 3/8 = 37.5% | Brier 0.3269
- Vitória Casa: 3/4 = 75.0% | Brier 0.2367

Probabilidade:
- 55–59%: 3/4 = 75.0%
- 60–64%: 1/1 = 100.0%
- 65–69%: 10/22 = 45.5%

Ranking:
- #1–5: 8/12 = 66.7%
- #6–10: 1/5 = 20.0%
- #11–15: 2/5 = 40.0%
- #16–20: 3/5 = 60.0%

Confiança:
- ALTA: 4/10 = 40.0%
- MÉDIA-ALTA: 6/12 = 50.0%
- MÉDIA: 1/1 = 100.0%
- BAIXA: 3/4 = 75.0%

Qualidade:
- 85–100: 6/15 = 40.0%
- 70–84: 2/5 = 40.0%
- 55–69: 6/7 = 85.7%

Interpretação atual: a V1.2 ainda tem amostra pequena e está sobreconfiante. Os grupos de confiança/qualidade alta continuam a mostrar sinais fracos. Não criar V1.3 antes de chegar a cerca de 40 V1.2 liquidadas, salvo evidência técnica clara de bug.

## Odds / Betano / OddsPapi

Fonte principal de odds:
- OddsPapi
- bookmaker: `betano.pt`

Estado confirmado da conta:
- pedidos usados: 331/250
- restantes: 0
- quota esgotada

Diagnósticos implementados:
- `odds_quota_esgotada`
- `odds_rate_limit_429`

Comando:
- `/odds_status`

`/odds_status` consulta `/v4/account` e mostra quota usada/restante sem consumir a quota mensal de odds.

### Otimizações de quota já implementadas

- consulta de odds em lote com `/odds-by-tournaments`
- cache da descoberta de fixtures por 3 horas
- captura automática reduzida de 30 min para 2 horas
- janela de captura automática reduzida para 4 horas
- antes da captura automática, o bot verifica a quota via `/account`
- se a quota está a 0, a captura automática fica suspensa
- quando `/account` voltar a indicar pedidos disponíveis, a captura pode retomar
- não fazer fuzzy matching de fixtures; usar aliases controlados e hora para desempate

## Auditoria de odds

Último estado:
- previsões liquidadas com odd congelada: 18
- resultado a 1u por previsão: -3.44u
- ROI observado: -19.1%
- EV médio no snapshot: +8.3%

Importante:
- odds reais servem para auditoria
- não alteram previsões já congeladas
- previsões sem odd real contam para acerto/Brier, mas não para ROI

## Regras de persistência e auditoria

Ficheiro principal persistente:
- `/data/previsoes_premium.json`

Chave:
- `event_id|mercado`

Regras:
- histórico append-only
- não reescrever probabilidade, mercado, qualidade, odd justa, odd mínima, versão, ranking, confiança ou odd congelada
- settlement pode preencher apenas o resultado final
- previsão adiada mantém os dados congelados originais
- procurar resultados também em datas adjacentes para jogos adiados
- não aceitar odds pós-kickoff
- a primeira odd real válida pré-jogo é congelada para auditoria

## Cobertura / dados

Fontes:
- ESPN como principal para jogos e estatísticas
- SofaScore como fallback controlado

Competições principais cobertas incluem ligas europeias relevantes, Brasil, Argentina, MLS, UEFA Champions/Europa/Conference e Nations League.

Nations League:
- código: `uefa.nations`
- baseline de competição obtido via SofaScore
- torneio SofaScore usado: 10783
- baseline atual baseado na época concluída anterior 24/25
- forma atual das seleções via ESPN multicompetição
- lógica bienal específica para não usar incorretamente a época 26/27 como base histórica

Princípio:
- não baixar `MIN_JOGOS_BASE=10`
- rótulos genéricos como Group Stage / League Phase / Regular Season não devem ser mapeados sem metadados suficientes
- amigáveis continuam fora

## Comandos relevantes

- `/cobertura` — cobertura de jogos/dados/seleções
- `/analisa` — gera e regista previsões novas
- `/performance` — auditoria global
- `/valor` — compara odd atual com previsão congelada sem alterar snapshot
- `/odds_status` — quota OddsPapi
- `/odds` — inspeção da fonte de odds

`/performance` já contém o bloco **🧬 V1.2 APENAS** com:
- global
- mercados
- probabilidade
- ranking
- confiança
- qualidade

## Fluxo operacional recomendado

1. Correr `/cobertura`.
2. Só correr `/analisa` quando houver jogos com dados suficientes.
3. Não repetir `/analisa` desnecessariamente no mesmo dia.
4. Deixar snapshots congelados.
5. Após os jogos, correr `/performance`.
6. Acompanhar a V1.2 até cerca de 40 liquidadas.
7. Só depois decidir se existe base para V1.3.
8. Enquanto a quota OddsPapi estiver a 0, não insistir com `/valor`.

## Próxima decisão de modelo

Quando V1.2 chegar a ~40 liquidadas, rever:
- calibração global
- Brier
- mercados
- ranking
- confiança
- qualidade
- possível excesso de confiança nos 65–69%
- Under 3.5
- comportamento anormal de rankings #6–15
- relação inversa aparente entre qualidade dos dados e acerto

Qualquer V1.3 deve ser uma alteração controlada, versionada, testada e sem reescrever histórico.

## Segurança operacional

Nunca guardar no repositório:
- `TELEGRAM_TOKEN`
- `ODDS_PAPI_KEY`
- outras credenciais

Esses valores permanecem apenas nas variáveis do Railway.
