# Pré-integração: validação de linhas Over/Under (SHADOW, 27/10/2026)

## Estado
- A V2 isolada está em `validacao_linhas_v2_shadow.py`.
- 24 testes unitários da V2 passaram localmente com `python -m unittest -q test_validacao_linhas_v2_shadow.py` em ambiente isolado. O teste local não substitui CI nem a suite integral do bot.
- Nenhum ficheiro de produção foi alterado; sem PR, merge, deploy ou chamadas OddsPapi.
- O ramo contém outros protótipos SHADOW que **não devem** ser integrados em bloco.

## Patch mínimo proposto (não aplicado)
Em `odds_auditoria.py`, dentro de `AuditoriaOdds._item_compativel`, apenas no ramo Over/Under, após validação do mercado e sem mudar a lógica de seleção:
1. Importar `validar_linha_totais` de um módulo próprio e estável.
2. Substituir a comparação textual de linha e a comparação de handicap por `return validar_linha_totais(mercado_modelo, mercado, odd)[0]`.
3. Não alterar `_mercado_compativel`, `_periodo_compativel`, `_extrair_odd_diagnostico`, classificação VALUE, preços mínimos, odds ou critérios de aposta.
4. Manter `main` e V1.3 intactos até aprovação explícita.

## Gate obrigatório antes de qualquer merge
- Executar `python -m unittest discover -s tests -v` com dependências e ambiente do projeto; documentar falhas e eventuais testes externos.
- Comparar parser atual vs V2 em fixtures já existentes (incluindo `tests/test_odds_linhas_papi.py`): Under 2.5 e 3.5, Betano, handicap, período e timestamp.
- Testar seleção contraditória, linha 12.5 vs 2.5, nome com ano 2026, IDs numéricos e linhas ausentes.
- Rever divergências de casos sem handicap, e verificar o tratamento de períodos ausentes: esta V2 não modifica a regra de períodos.
- Se possível, executar replay offline com payloads reais previamente guardados e medir: aceites atuais, aceites V2, rejeições novas, rejeições justificadas e regressões.
- Confirmar com dados reais que não há falsas rejeições; se não existirem payloads, assinalar limitação e exigir fase SHADOW observacional antes de integração.
- Rever o código e os resultados, pedir autorização específica antes de PR/merge/deploy.

## Limitações conhecidas
- Esta função só valida a linha; **não** valida identidade do fixture, bookmaker, período, tipo de mercado, frescura ou disponibilidade.
- Linhas decimais são detetadas em texto livre; números inteiros só contam como linha quando introduzidos por `line`, `linha` ou `handicap`. A cobertura de formatos reais deve ser confirmada.
- Não há evidência de que as 323 ocorrências históricas `mercado_nao_disponivel` resultem desta falha.
- Os testes unitários SHADOW não provam ROI nem CLV.
