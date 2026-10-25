# Auditoria SHADOW — segurança da associação de mercados
**Data:** 25-10-2026  
**Ramo:** audit/seguranca-mercados-shadow-20261025  
**Base:** main  
**Modo:** somente leitura da produção; dados de teste inteiramente sintéticos.

## Âmbito e garantias
- Nenhuma alteração a main, V1.2, V1.3, coorte comercial de 50, snapshots, odds, CLV, ROI, thresholds ou Railway.
- Nenhuma chamada a OddsPapi, ESPN, Betano ou qualquer API de futebol.
- Nenhum PR, merge, deploy, reinício ou promoção automática.
- O único ficheiro de código novo é um teste de diagnóstico no ramo isolado: tests/test_seguranca_mercados_shadow_20261025.py.
- Não é apresentada qualquer inferência de ganhos, perdas ou frequência real dos erros.

## Constatações de código (main)

### C1 — Correspondência parcial entre linhas numéricas (risco de integridade)
Em odds_auditoria.py, o método _item_compativel compara a linha alvo convertida pela normalização com os textos usando substring:

    return linha_texto in escolha or linha_texto in nome_mercado

_normalizar transforma "2.5" em "2 5" e "12.5" em "12 5"; a primeira sequência aparece dentro da segunda.

**Caso sintético:** pedido Under 2.5; fornecedor com mercado "Total Goals", sem handicap, e seleção "Under 12.5". A lógica atual pode aceitar esta seleção em vez de rejeitá-la.

Também ocorre quando o número só figura no nome do mercado, como "Total Goals 12.5", e a seleção se chama apenas "Under".

O diagnóstico é determinístico para esses payloads sintéticos. A existência desses formatos e o seu impacto em odds históricas **não estão demonstrados**.

### C2 — Contradição entre handicap e seleção
Se mercado.handicap for um número, _item_compativel verifica apenas a igualdade com a linha pedida, após confirmar que o lado "under"/"over" consta do texto. Não cruza esse número com eventual linha escrita na seleção.

**Caso sintético:** handicap=2.5 e seleção "Under 3.5" pode ser aceite como Under 2.5.

Esta condição só cria risco quando o feed contém dados contraditórios.

### C3 — Ranking escolhe uma seleção antes da verificação das odds
Em analisador_inteligente.py, _melhor_selecao escolhe o mercado de maior probabilidade ajustada (score=prob). A componente OddsPapi/Betano atua a seguir sobre a seleção escolhida.

**Exemplo fictício:** Ambas Marcam p=63.44%, odd=1.60 (abaixo da mínima); Over 2.5 p=62.80%, odd=1.80 (acima da mínima). A seleção anterior pode ser mantida embora a segunda tivesse VALUE.

Isto é uma característica comprovada da arquitetura atual, **não uma prova de perda sistemática de oportunidades reais**.

### C4 — Corte implícito de probabilidade
A condição odd_minima=1.05/p, seguida de rejeição se odd_minima<1.50, implica p<=0.70 (salvo arredondamentos), impedindo selecionar probabilidades ajustadas acima de 70%. O parâmetro qualidade funciona como filtro, sem modular diretamente o valor de p.

### C5 — Complementaridade correta de Under/Over
As distribuições de Poisson em estatisticas_espn.py satisfazem Under 2.5 = 1 - Over 2.5 e Under 3.5 = 1 - Over 3.5. Não foi identificado erro algébrico óbvio nessa propriedade.

## Testes de diagnóstico
Ficheiro: tests/test_seguranca_mercados_shadow_20261025.py

São 12 casos:
- 9 verificações positivas de comportamentos seguros ou atuais: linha correta, linha explícita diferente, período incompatível, duplicidade ambígua, não mutação do payload, ranking pré-odds, corte de 70%, qualidade como filtro e complementaridade Poisson.
- 3 casos de regressão anotados com @unittest.expectedFailure: falso match Under 12.5→Under 2.5 por nome da seleção; falso match por nome de mercado; handicap 2.5 acompanhado de seleção textual Under 3.5.

**Execução em 25-10-2026:** os 12 casos foram executados *apenas num ambiente local com reprodução isolada das funções relevantes*, não diretamente no projeto original: **9 OK, 3 expected failures**.

**Limitação:** a suite oficial completa ainda não foi executada com os módulos reais do repositório. Os testes foram adicionados ao ramo para execução futura com o projeto completo. Os @expectedFailure registam comportamentos conhecidos; um resultado geral "OK" não significa que os três defeitos foram resolvidos.

Comando, quando o código do ramo estiver disponível num ambiente seguro e isolado:

    python -m unittest discover -s tests -p 'test_seguranca_mercados_shadow_20261025.py' -v

Não usar esse comando num procedimento de deploy automático sem avaliar previamente o workflow.

## Plano de mitigação FUTURO (não implementado)
1. Extrair linhas numéricas com análise de tokens delimitados, sem substring parcial; comparar com igualdade numérica exata dentro de tolerância.
2. Quando handicap e seleção incluírem ambos linha numérica, validar que concordam; caso contrário, rejeitar e explicar a razão.
3. Quando a linha for desconhecida, preferir não capturar odds, em vez de inferir por substring.
4. Testar também 1.5, 2.5, 3.5, 12.5, seleções Over, palavras "Over/Under" e mercados com linhas explícitas.
5. Medir impacto potencial em snapshots e dados históricos preservados — nunca alterar retroativamente esses registos.
6. Executar suite oficial e comparar alternativas estritamente em SHADOW antes de sugerir qualquer alteração ao comportamento de produção.
7. Reavaliar a escolha de mercados por probabilidade versus VALUE só depois do teste V1.3 ou mediante estudo pré-registado independente, sem mudar a coorte original.

## Estado e decisão
**Auditoria concluída ao nível de código e demonstração sintética.** Três fragilidades potenciais identificadas; nenhum erro real em captura histórica comprovado. Não foi feita correção, PR, merge ou deploy. A V1.3 mantém-se inalterada a recolher dados.