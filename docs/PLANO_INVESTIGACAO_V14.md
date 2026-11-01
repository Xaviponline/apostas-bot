# Plano de investigação para uma possível V1.4 — bot de apostas

**Estado:** documento de investigação, não uma versão aprovada nem um novo teste.  
**Data de elaboração:** 01/11/2026.  
**Âmbito:** diagnóstico técnico e estatístico, **sem alterações ao motor, aos filtros, às odds, ao SEL1, ao Champion V1.2, à V1.3 Comercial, ao Platt prospetivo, à quota OddsPapi, aos snapshots ou ao gate**.

## 1. Ponto de partida — última fotografia comunicada

Os números seguintes vêm dos relatórios Telegram fornecidos pelo proprietário em 01/11/2026; não são uma nova extração da base de dados.

| Experiência | Situação | Resultado intermédio |
|---|---|---|
| V1.3 Top5 + VALUE | 28/50 entradas; 27 liquidadas; 15/20 dias | 12 ganhos/15 perdas; -5,27u; ROI -19,5%; drawdown máx. 7,81u |
| CLV oficial da V1.3 | 21/28 fechos; 7 definitivamente em falta | CLV médio +0,1%; 8/21 positivos; faltam 19 fechos para 40/50 |
| Platt Top5 SHADOW | 66/100 inscritas; 61 liquidadas; 14/20 dias | Brier Champion 0,2264 versus Platt 0,2326; Platt pior neste checkpoint |
| Qualidade de odds | sinais de mercados/fixtures não encontrados e odds com última alteração antiga | Não comprovam preço executável nem erro da casa de apostas |

**Limitação importante:** o Brier do Platt é de uma amostra Top5 de jogos futuros e o ROI da V1.3 refere-se apenas a VALUE elegíveis; não são o mesmo universo. Não atribuir causalidade ao filtro VALUE comparando apenas percentagens agregadas destas duas experiências.

O código oficial em `previsoes_premium.py::metricas_v13_comercial` confirma que a coorte mantém as **primeiras 50** entradas elegíveis ordenadas por hora de confirmação, com desempate pelo snapshot; não se podem substituir nem estender entradas. Verificar sempre o código e os relatórios oficiais antes de uma decisão.

## 2. Objetivo e perguntas falsificáveis

**Objetivo:** apurar se existe uma oportunidade reprodutível de melhorar a calibração, a verificação das odds e a seleção de VALUE, sem usar os resultados da própria experiência para otimizar retroativamente a seleção.

| Hipótese | O que medir, sem mudar o modelo atual | O que a enfraquece ou refuta |
|---|---|---|
| H1. Probabilidades demasiado otimistas nos VALUE | Brier, log-loss, gap e curvas de calibração no *mesmo subconjunto de VALUE*, com p e resultado congelados antes do início | Diferença não consistente após estratificação e intervalos de incerteza amplos |
| H2. Viés de seleção do filtro VALUE | Funil com Top5 monitorizadas, odds realmente identificadas, VALIDs, VALUE elegíveis e liquidadas; comparação ajustada por mercado, competição, data e probabilidade | Distribuições e desempenho compatíveis entre elegíveis e comparadores adequados |
| H3. Qualidade/executabilidade insuficiente das odds | Identidade do fixture, período, mercado, linha, timestamp de captura, origem e prova de presença na Betano | Falhas pouco frequentes e sem associação consistente às perdas; ausência de prova permanece desconhecida, não «boa» |
| H4. CLV ausente de forma não aleatória | Falhas por mercado, liga, jogo, fase horária, catálogo vazio, mercado sem alias, incompatibilidade de linha; comparar cobertura por grupos | Taxas de falha semelhantes e mecanismos identificados sem efeito aparente; manter cenário pessimista se persistir incerteza |
| H5. A melhoria Platt generaliza ou não | Comparação emparelhada Champion vs Platt nos mesmos jogos futuros, Brier/intervalos e calibração | Platt não melhora consistentemente; manter Champion |
| H6. Resultado negativo é dominado por variância/concentração | ROI, P/L, drawdown, sequências, dias, mercados e bootstrap por dia, com dependência explícita | Sem evidência robusta de edge; não converter ausência de significância em prova de rentabilidade |

**Aviso:** estes testes são *exploratórios* até ao congelamento de um protocolo V1.4 posterior; não escolher a hipótese mais favorável para proclamar vitória.

## 3. Inventário de dados e integridade antes de qualquer estudo

Fontes internas existentes:
- `previsoes_premium.py`: coorte oficial, resultados, probabilidade inicial, primeira cotação confirmada, CLV oficial e gate;
- `auditoria_qualidade_v13_shadow.py`: sinais de integridade/identidade/idade de preço;
- `auditoria_impacto_frescura_v13_shadow.py`: associação **observacional** entre hora da última alteração do preço e ROI;
- `odds_auditoria.py`, `odds_catalogo_clv_shadow.py`, `clv_tentativas.py` e `clv_observatorio.py`: motivos documentados de falha de matching e CLV;
- Research Lab: resultados já congelados do comparador Champion/Platt.

Controlos obrigatórios:
1. Usar somente snapshots já existentes e cópias sanitizadas. Validar hashes/digests e índices únicos da coorte; documentar falhas de correspondência, dados ausentes e alterações indevidas.
2. Exigir resultados finais válidos e probabilidades **criadas antes do jogo**; não misturar pendentes com perdas ou invalidar perdas para elevar ROI.
3. Separar odds da primeira confirmação, odds observadas posteriormente, CLV T-30m e observação T-10m. **Nunca** preencher o CLV T-30m com preços T-10m, pós-jogo, retrospectivos ou de outro bookmaker.
4. Distinguir horário de última alteração de preço de disponibilidade real da cotação no bookmaker; ambas as variáveis não são equivalentes.
5. Registar o grau de confirmação de mercado (fixture, full-time vs 1.ª parte, handicap 2.5/3.5, seleção Under/Over e identidade), sem normalização fuzzy que aceite mercados diferentes.
6. Respeitar quotas, limites de pedidos e segredos. Análises deste plano devem ser offline/read-only: **zero HTTP adicional** e zero escrita no histórico oficial.
7. Analisar a cobertura CLV e as ausências: o CLV médio só representa os casos com fecho. As falhas podem estar correlacionadas com condições de mercado; medir sensibilidade e não imputar cotações inexistentes.

## 4. Sequência de trabalho pós-fecho — com resultados verificáveis

### A. Fechar formalmente as experiências atuais

- **V1.3:** 50 primeiras entradas elegíveis, todas liquidadas, pelo menos 20 dias, 40/50 CLV oficial; gate já fixo = **ROI > 0% e CLV médio > 0%**, sem promoção automática.
- Se a cobertura CLV ficar abaixo de 40/50, o gate não passa, mesmo com ROI positivo. Registar separadamente «evidência insuficiente por cobertura» versus «indicadores económicos negativos», sem mudar o estado oficial.
- **Platt:** aguardar 100 **liquidadas**, 20 dias distintos e avaliação emparelhada predefinida, sem substituir o Champion por checkpoint intermédio.
- Congelar artefactos de avaliação: identificação de snapshots, digest, número de jogos/dias, cobertura, métricas e limitações. Nunca recalcular a coorte com critérios novos.

### B. Auditoria do funil de VALUE

Definir uma **base comum observável**: todas Top5 monitorizadas no período, separando (a) sem evento validado, (b) sem mercado/odd válida, (c) com odd mas sem atingir mínima, (d) VALUE confirmado e (e) elegível liquidado. Para cada transição, contagem, mercado, liga, horário, probabilidades e qualidade. Só comparar ROI se **ambos** os grupos tiverem odds contemporâneas e comparáveis; caso contrário comparar apenas hit rate/calibração e declarar os limites.

Revisões exploratórias, com amostras e IC explícitos:
- Brier/gap por mercado, especialmente Under 2.5, e por faixas de probabilidade, liga e janela temporal;
- diferença entre probabilidades nominais e frequências observadas, ponderando tamanho do grupo;
- possível efeito de seleção de odds aparentemente elevadas à custa de mercados pouco fiáveis;
- efeito da idade da **última alteração** das odds sem confundi-la com prova de preço disponível;
- associação dos sete fechos antigos ausentes com categoria de mercado/fixture e disponibilidade de catálogo.

**Critérios de cautela:** grupos pequenos não autorizam mudança de filtro; ausência de dados não equivale a evento inexistente; escolher grupos depois de observar as perdas gera viés.

### C. Testar potenciais abordagens V1.4 apenas como candidatas

Candidatas a estudar separadamente (não combiná-las sem evidência):
1. Recalibração mais simples/regularizada por grandes famílias de mercado, se houver amostra suficiente, ou manter Champion;
2. Identificação mais rigorosa de fixture/mercado/linha e prova de executabilidade de odds sem bloquear por timestamp de última alteração;
3. Critérios VALUE ajustados **apenas** após análise da cobertura e provas de preços e com novos limiares pré-registados;
4. Eventuais regras explícitas de abstenção por incerteza/qualidade de dados, com quantificação do custo em cobertura.

Cada candidata precisa de definição implementável, custos/API, riscos de leakage, regressões offline, estudo de sensibilidade e previsão falsificável. Nenhuma é automaticamente aceite.

### D. Protocolo V1.4 prospetivo a aprovar antes da primeira previsão

Antes de iniciar, escrever e congelar noutro documento:
- universo de jogos e horários, mercados, versão exata de modelo, features disponíveis antes do jogo e tratamento de dados ausentes;
- comparador Champion **sobre os mesmos fixtures/mercados**; regras de elegibilidade, stake virtual, política de odds, métricas primárias e secundárias e ponderação;
- tamanho da amostra e dias mínimos justificados **antes** da recolha, intervalos de incerteza/ajuste a comparações múltiplas e checkpoints sem *optional stopping*;
- identificador/digest do calibrador e do protocolo, teste de integridade, estratégia de deploy SHADOW e rollback;
- regra de sucesso, de falha e de **NO-GO por dados insuficientes**, incluindo cobertura CLV e odds executáveis; nenhuma auto-promoção;
- qualquer piloto de venda só depois de avaliação adicional prospectiva, de viabilidade operacional/legal e da necessidade de divulgação transparente de resultados e riscos.

## 5. Árvore de decisão após resultados finais

| Resultado | Decisão |
|---|---|
| V1.3 não passa gate ROI/CLV | Não lançar nem prolongar V1.3; guardar resultado e estudar V1.4 |
| Falha apenas cobertura/qualidade de dados | Não declarar edge; corrigir método de recolha para futuras experiências; não reconstruir fechos antigos |
| V1.3 passa gate | Não lançar automaticamente; auditoria independente, mais dados prospetivos e verificação de executabilidade |
| Platt tem Brier pior ou resultado incerto | Manter Champion; Platt continua arquivo experimental |
| Platt melhora Brier no protocolo | Considerar *candidato* em SHADOW, não mudar ROI/mercados/gate existentes |
| Evidência V1.4 fraca ou instável | Não promover; documentar resultado negativo e reavaliar pressupostos |

## 6. Entregáveis de investigação (sem alterar produção)

- **D1 — Relatório de integridade e disponibilidade:** coorte, dados ausentes, identidade do evento/mercado, idades de preço e fechos CLV, com denominadores.
- **D2 — Funil de seleção VALUE:** contagem por etapa e comparação adequada com o Top5, com ressalvas de seleção.
- **D3 — Relatório de calibração:** Champion e Platt nos mesmos jogos, e V1.3 separadamente; Brier, gap, amostras e incerteza.
- **D4 — Relatório de risco:** P/L, ROI, drawdown, bootstrap por dias, concentração por mercados e explicação de por que o IC não garante lucro.
- **D5 — Proposta pré-registada V1.4:** *apenas* se D1–D4 justificarem uma hipótese testável. O proprietário aprova antes da implementação.

**Não fazer agora:** mudar limiares ou odds mínimas, trocar modelos, alterar o matching de preços em produção, procurar fechos antigos através de novas consultas, reclassificar entradas V1.3, acrescentar entradas além das 50, colocar apostas reais nem anunciar lucratividade.

## 7. Revisão operacional enquanto as experiências recolhem

- Consultar de forma espaçada `/v13_comercial`, `/lab_platt_prospectivo` e `/clv_diagnostico`, sem comandos de sincronização adicionais desnecessários.
- Quando aparecer nova falha de catálogo, verificar os nomes/períodos/handicaps **sanitizados** guardados pelo novo SHADOW, sem assumir que o preço era negociável.
- Abrir trabalho de código separado **somente** para anomalia com prova, testes de regressão, plano de reversão e nenhuma alteração silenciosa da coorte.

---

**Este ficheiro é apenas um plano e não constitui pré-registo definitivo da V1.4.** O pré-registo prospetivo exigirá decisão explícita, versão imutável e início posterior. Os resultados de apostas são incertos; CLV ou Brier favoráveis não demonstram, isoladamente, ROI positivo nem lucros futuros.
