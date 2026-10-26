# Auditoria SHADOW — porque existem poucas entradas VALUE?

**Data:** 26/10/2026  
**Ramo:** audit/funil-value-pt-20261026  
**Política:** nenhuma alteração à produção, aos critérios V1.2/V1.3, ao teste de 50 entradas ou às odds históricas.

## Contexto verificado
Na última resposta do Telegram, a V1.3 apresentava:
- 81 seleções Top5 monitorizadas desde snapshot #207;
- 16 entradas VALUE confirmadas, 16 liquidadas;
- 65 seleções Top5 que não preencheram as condições oficiais de entrada (81-16);
- 5 vitórias, 11 derrotas, ROI -48,8%, CLV médio +0,7% nas 11 amostras com fecho.

Os 65 casos não têm causa comprovada individualmente a partir do relatório agregado. Não dizer "65 sem odd" nem "65 com odd baixa".

No Railway, os logs de 25/10/2026 registaram:
- Na análise inicial das 09:00 UTC, 20 seleções e só 1 odd compatível; 19 sem cotação compatível nessa passagem;
- Houve uma recuperação separada com 3 cotações em 4 seleções;
- As rondas adicionais podem observar jogos repetidos; não somar contagens como se fossem seleções únicas;
- Algumas falhas "mercado_nao_disponivel", sem prova de ausência do mercado real na Betano.

## O que a V1.3 faz REALMENTE
Em previsoes_premium.py:
- só os registos V1.2 a partir do snapshot #207 com ranking #1–5;
- odd de entrada = odd_valor_confirmado válida; em alternativa odd_real >= odd_minima;
- a coorte usa as primeiras 50 confirmações, ordenadas pela data/hora;
- a coorte é imutável. Sem substituição e sem promoção automática.
Em analisador_inteligente.py:
- odd mínima = 1.05 / probabilidade ajustada;
- a regra de perfil rejeita odd_minima < 1.50;
- a seleção de mercado é anterior à verificação da odd de mercado.

### Regra teórica: exemplos
| Probabilidade | Odd justa | Odd mínima exigida |
|---:|---:|---:|
| 58% | 1,72 | 1,81 |
| 60% | 1,67 | 1,75 |
| 65% | 1,54 | 1,62 |
| 67% | 1,49 | 1,57 |
| 70% | 1,43 | 1,50 |

VALUE depende de **probabilidade estimada bem calibrada** E odd compatível. Se o p estiver demasiado alto, a aparente margem de 5% não é real. Maior odd, isoladamente, não demonstra melhor aposta.

## Mercados e operadores portugueses
A lista oficial do SRIJ, consultada em 26/10/2026, inclui Betano, Betclic, Bwin, ESCOnline, Placard, LeBull, entre outros, mas não inclui bet365.
Fonte: https://www.srij.turismodeportugal.pt/pt/jogos-e-apostas-online/entidades-licenciadas

Não assumir que a bet365 tem odds superiores, nem usar preços internacionais como se fossem executáveis em Portugal. Uma eventual comparação futura, puramente SHADOW, só deve tratar como executáveis cotações de operadores licenciados, com jogo, identidade do mercado, linha, período, hora, estado, e preço confirmados. A origem e os termos de utilização dos dados devem ser respeitados.

## Ferramenta offline criada
Ficheiros no ramo isolado:
- scripts/auditoria_funil_value_offline.py
- tests/test_auditoria_funil_value_offline.py

Um script para executar **numa cópia privada** de /data/previsoes_premium.json:

    python scripts/auditoria_funil_value_offline.py \
      --previsoes /copia-privada/previsoes_premium.json \
      --saida /copia-privada/diagnostico-value-20261026

A saída deve ser uma pasta inexistente e diferente da origem. São criados:
- top5_funil_detalhe.csv — 1 linha por seleção Top5 desde #207;
- funil_motivos.csv — contagens por categoria;
- funil_por_mercado.csv — motivos por mercado;
- funil_por_liga.csv — motivos por competição;
- RESUMO.json — totais, SHA-256 da fonte e confirmação de que ficou intacta;
- LEIA_ME.txt — limites de interpretação.

Categorias:
- VALUE_confirmado: a lógica oficial identifica uma entrada elegível;
- sem_odd_guardada: nenhum campo relevante contém odd válida nos snapshots guardados; **não prova** que a casa não tivesse mercado;
- odds_guardadas_abaixo_minimo: odd(s) guardadas válidas mas inferiores ao mínimo;
- limiar_ausente: não foi possível recuperar uma odd mínima válida;
- inconsistencia_metadados_ou_tempos: há uma cotação guardada acima do mínimo mas sem entrada oficial, o que exige inspeção temporal/manual.

Classificações são baseadas apenas em informação persistida: não recuperam todas as tentativas ou todos os mercados do fornecedor. O valor atual de odds depois da entrada não substitui a primeira odd congelada. As contagens por mercado e liga não demonstram desempenho por si próprias.

### Testes
Oito testes sintéticos foram executados localmente com sucesso sobre a lógica offline. Foi adicionada uma versão para o repositório; a suite completa do GitHub ainda não foi executada neste ramo. Nenhum uso de API externa.

Para executar isoladamente no repositório:

    python -m unittest discover -s tests -p 'test_auditoria_funil_value_offline.py' -v

**Não colocar cópias do JSON histórico, credenciais ou tokens no repositório público.**

## Decisões
1. Não baixar odd mínima ou alterar o filtro de VALUE antes de auditar a calibração e os preços.
2. Não trocar unilateralmente a fonte de odds oficial; V1.3 continua na Betano PT.
3. Só estudar comparações com casas licenciadas em PT se houver cotações fiáveis, legalmente acessíveis, sem usar quota adicional.
4. Validar a contagem offline com o Telegram: Top5 81, VALUE 16 no momento do snapshot; diferenças por atualização temporal dos dados devem ser registadas, não corrigidas retroativamente.
5. Analisar como investigação separada a falha de identificação de linhas de golos já documentada no ramo audit/seguranca-mercados-shadow-20261025.
6. A decisão comercial exige coorte fixa 50, 20 dias, 40 CLV, ROI>0%, CLV médio>0%. Sem mudança na experiência original.

**Conclusão:** uma baixa taxa de confirmação VALUE pode refletir cotações ausentes, odds insuficientes, seleção de mercado anterior ao preço, ou uma combinação desses fatores. Só a exportação privada da história permite quantificar as componentes observáveis de modo rigoroso.