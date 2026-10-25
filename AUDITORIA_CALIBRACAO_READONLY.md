# Auditoria de calibração e cobertura — ONLY READ
**Data:** 25/10/2026 (Portugal). **Ramo isolado:** \`audit/calibracao-offline-20261025\`.
**Não integrar em main; não fazer deploy; não consultar OddsPapi; não alterar o histórico.**

## 1. Estado dos dados / evidência disponível
A conexão GitHub permite inspecionar o código; a conexão Railway confirma o volume \`/data\`, mas **não lê o seu conteúdo**. Não foi disponibilizada uma cópia de \`/data/previsoes_premium.json\` nesta auditoria. Portanto, **não é possível apresentar de forma factual linhas individuais de todas as previsões ou taxas por faixa, mercado e liga** até executar o script sobre uma cópia.

Únicas estatísticas verificadas por relatório Telegram:
- V1.3 comercial: **16/50** entradas VALUE, **16 liquidadas**, **5 vitórias/11 derrotas**, **9/20 dias**.
- Previsão média **67,1%**, acertos reais **31,25%**, esperados **10,73**, desvio **−35,8 pontos percentuais**, Brier **0,3403**.
- P/L **−7,81u**; ROI **−48,8%**; CLV **11/16**, média **+0,7%** (apenas 4/11 positivos).
- Mercados na coorte: Under 2.5 (6), Under 3.5 (5), Vitória Casa (3), Over 2.5 (2). **Vitórias em cada mercado ainda não fornecidas.**
- Não atribuir estas métricas da coorte de 16 ao histórico completo V1.2.

## 2. Script reproduzível / saída

\`\`\`bash
python scripts/auditoria_calibracao_offline.py \
  --previsoes /copia-privada/previsoes_premium.json \
  --rastreio /copia-privada/odds_rastreio.jsonl \
  --tentativas /copia-privada/clv_tentativas.json \
  --saida /copia-privada/auditoria-2026-10-25
\`\`\`

Os 2 ficheiros opcionais, rastreio e tentativas, só enriquecem a tabela de mercados/falhas. Nunca os pedir à rede. Executar **apenas numa cópia privada** do ficheiro persistente, preferivelmente fora de produção. Não colocar esses JSON nem os CSV resultantes no GitHub público.

Saídas CSV:
1. \`previsoes_todas.csv\` — todas as entradas, incluindo pendentes, data, jogo, mercado, liga, probabilidade, odd inicial congelada, odd VALUE confirmada, odd de fecho, resultado, IDs e versão.
2. \`calibracao_global.csv\`, \`calibracao_faixas.csv\` — acertos realizados e esperados, Brier, n e discrepância.
3. \`calibracao_mercados.csv\`, \`calibracao_ligas.csv\`, \`calibracao_mercado_liga.csv\` — subdivisões por faixa sem mistura de ligas.
4. \`calibracao_por_versao.csv\` — evita confundir V1.0/V1.1/V1.2.
5. \`nomes_mercados_observados.csv\` e \`falhas_mercado_historico.csv\` — só evidência local existente, sem reconstrução.
6. \`avisos_dados.csv\` e \`LEIA_ME.txt\` — valores inválidos, regras de recorte e hashes SHA-256 da fonte antes/depois.

Faixas: [50%,55%), [55%,60%), [60%,65%), [65%,70%), [70%,100%]; previsões abaixo de 50% identificadas em grupo separado. Pendentes e previsões de probabilidade inválida **não** entram no denominador da taxa de acerto; são contabilizadas no total. Grupos de n baixo são descritivos, não conclusões estatísticas.

## 3. Origem das probabilidades — motor V1.2 usado pela V1.3 Comercial
\`main_competicoes.py\` (função \`main\`) instancia \`AnalisadorInteligenteEnriquecido\` com \`EstatisticasFormaWeb\`. Este herda cálculos de \`EstatisticasESPN\`; em provas configuradas usa forma multicompetição; a Copa Argentina \`arg.copa\` tem regra específica de campo neutro.

Dados:
- Base de média de golos da competição \`liga_home = mean(golos_casa)\` e \`liga_away = mean(golos_fora)\`, mínimo 10 jogos, recorte da fonte conforme competição.
- Últimos 8 jogos gerais de cada equipa, mínimo 4 por equipa; 6 últimos em casa para a equipa anfitriã e 6 últimos fora para a visitante; usar componente local com pelo menos 3, senão geral.
- Golos marcados/sofridos de cada lado. Médias de equipa ajustadas a um prior da liga por \`(total_golos + 3*media_liga)/(n+3)\`; peso efetivo da equipa = n/(n+3) e prior = 3/(n+3).
- \`lambda_casa = casa_gf * fora_ga / liga_home\`; \`lambda_fora = fora_gf * casa_ga / liga_away\`; ambos limitados a [0,20,3,80].
- Poisson independente por equipa, matriz de resultados 0–10 golos por lado, normalizada para a massa coberta.
- Vitória Casa = soma P(i>j); Vitória Fora = soma P(i<j); empate = P(i=j); ambas marcam = soma P(i>0 e j>0); Over 1.5 = P(i+j≥2); Over 2.5 = P(i+j≥3); Over 3.5 = P(i+j≥4).
- **Under 2.5 = 1 − Over 2.5; Under 3.5 = 1 − Over 3.5. NÃO são modelos independentes.**
- V1.2: \`prob_ajustada = 0.50 + (prob_bruta - 0.50)*0.80\`, limitado a [0,01,0,99]; coeficiente 0,80 fixo, não aprendido por mercado/liga.
- Qualidade \`Q=round(100*(0.40*amostra+0.35*local+0.25*liga))\`, gate Q≥55; não multiplica a probabilidade. No caminho \`arg.copa\` neutro, Q usa pesos 0,75 amostra + 0,25 liga.
- Limiar por mercado: Vitória Casa/Fora 56%, BTTS 58%, Over 2.5 57%, Under 2.5 58%, Under 3.5 64%, Over 1.5 70%, 1X/X2 70%.
- Odd justa = 1/p; mínima VALUE = 1,05/p; rejeita se odd mínima <1,50. Portanto **p>70% é filtrada automaticamente**, e mercados com threshold 70% só passam praticamente se p for exatamente 70%. É limitação estrutural **confirmada no código**, não uma correção proposta para a coorte.
- Por jogo seleciona candidato aprovado com maior p; ranking global ordena pela probabilidade ajustada e em desempate probabilidade bruta. A V1.3 Comercial usa primeiras 50 VALUE elegíveis com ranking 1–5 desde #207.

Pressupostos/riscos do método (hipóteses a investigar, não erros comprovados): independência Poisson entre golos, drift de golos da competição, recortes curtos, viés de seleção para p elevado e descalibração por liga/mercado. A correlação Under/Over acima explica por que uma subestimação do total esperado pode sobrevalorizar Under.

## 4. Mapeamento de mercados — código atual
O mapeamento está implementado em \`odds_auditoria.py\` (\`_mercado_compativel\` e \`_item_compativel\`). Os nomes abaixo são **padrões aceites pelo código, não o catálogo exaustivo recebido da API**.

| Mercado do modelo | Nomes/famílias aceites do fornecedor | Identidade da seleção |
|---|---|---|
| Vitória Casa/Fora | \`full time result\`, \`match result\`, \`1x2\` | Casa=\`1\`/\`home\`/equipa; Fora=\`2\`/\`away\`/equipa |
| Ambas Marcam | \`both teams to score\`, \`both teams score\`, \`btts\` | \`yes\`/\`sim\` |
| Over/Under 1,5/2,5/3,5 | \`over under full time\`, \`total goals\`, \`goals over under\`, \`match goals\` | Lado Over/Under + linha numérica do mercado, ou linha inequívoca no texto |
| 1X/X2 | \`double chance\` | \`1x\`/\`x2\` |

Períodos aceites: \`fulltime\`, \`ft\`, \`match\`, \`regulartime\` (período ausente também é atualmente aceite). São excluídos cantos, cartões, jogadores, remates, períodos de primeira/segunda parte, totais de equipa e mercados indevidamente etiquetados. Associar o mercado não dispensa verificar fixture/hora e seleção.

Provedores no código:
- Principal: \`OddsPapi / Betano PT\` com catálogo \`/markets\`, onde IDs são convertidos em \`marketName\`/outcomeName; sem metadados cai no nome \`Market ID\`.
- Legado: \`Odds-API.io / Betano\` em estrutura própria, sem catálogo histórico neste relatório.
- Fonte alternativa em SHADOW: \`The Odds API\`, famílias \`h2h\` e \`totals\`; não atribui automaticamente odds Betano à V1.3.
- ESPN e SofaScore dão jogos/históricos/resultados, não são fontes de preços Betano.

Nomes realmente observados no rastreio disponível na conversa: \`Over Under Full Time\`, ID de mercado \`1010\`, linha 2,5 e seleção \`Under\`. Para enumerar **TODOS os nomes realmente devolvidos por fonte** é indispensável o rastreio local ou os payloads já preservados: nenhuma consulta OddsPapi foi realizada nesta auditoria.

## 5. Mercados pedidos ausentes — eventos com evidência
| # | Jogo | Mercado pedido | Observado | Causa |
|---|---|---|---|---|
| 408 | Lincoln Red Imps × FC Twente | Under 3.5 | 2 tentativas | \`mercado_nao_disponivel\` |
| 364 | Viborg FF × FC Midtjylland | Under 3.5 | 2 tentativas | \`mercado_nao_disponivel\` |
| 365 | Degerfors IF × Kalmar FF | Under 2.5 | 2 tentativas | \`mercado_nao_disponivel\` |
| 249 | Aberdeen × St Johnstone | Under 2.5 | Sem telemetria histórica | Causa desconhecida |
| 207 | Waasland-Beveren × Lommel SK | Vitória Casa | Sem telemetria histórica | Causa desconhecida |

O código devolve \`mercado_nao_disponivel\` quando *nenhum mercado compatível é encontrado na resposta normalizada*. Isto não permite distinguir, sem mais campos, falta efetiva do mercado, mercado presente mas com nome \`Market ID\`, suspensão ou omissão. O PR #103 regista **apenas para falhas futuras**, sem novo HTTP: total de mercados normalizados, compatíveis e sem catálogo, quando disponíveis. Não atribuir causas antigas não verificáveis.

Outros motivos distintos: \`linha_ou_selecao_nao_disponivel\`, \`betano_sem_odds_no_evento\`, \`fixture_omitido_no_lote\`, \`evento_nao_encontrado\`, \`horario_recuperacao_nao_validado\`, \`odds_payload_evento_divergente\`. Não misturar estes códigos nem assumir que preço histórico era executável.

## 6. Conclusão e limites
A prova principal de má calibração na atual coorte V1.3 continua a ser **5 acertos em 16, quando a soma das probabilidades previa 10,73**, Brier 0,3403. Há sinais de sobreconfiança da seleção comercial, mas a amostra não prova causalidade e ainda não é possível separar efeitos de liga, mercado, data e qualidade de dados.

**Próximo passo de dados**: executar o script OFFLINE sobre uma cópia do JSON persistente; guardar os CSV fora do GitHub e analisar os denominadores reais por faixa/mercado/liga. Não mudar fórmula, odds, filtros, threshold, seleção, coorte nem dados históricos durante este processo.
