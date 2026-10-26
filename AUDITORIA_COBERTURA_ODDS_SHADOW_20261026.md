# Diagnóstico SHADOW de cobertura de odds — 26/10/2026

## Estado da experiência (cópias privadas 26/10)
- 495 previsões no ficheiro `previsoes_premium.json`.
- 754 observações no `odds_rastreio.jsonl`; não são 754 jogos únicos.
- A partir do snapshot #207: 86 previsões Top5, sendo 46 sem odd inicial guardada, 24 com odd inicial abaixo da mínima e 16 com VALUE confirmado.
- Das 46 sem odd, 37 têm registos de rastreio e 9 não têm registos; para as 37, foram identificadas 129 observações anteriores à hora de início.
- Diagnósticos não exclusivos entre as 46 sem odd: `mercado_nao_disponivel` 18; `fixture_omitido_no_lote` 11; `betano_sem_odds_no_evento` 10; `evento_nao_encontrado` 7; `linha_ou_selecao_nao_disponivel` 3; `fixture_u19_confirmado_tff` 1. Não somar.
- No rastreio completo existem 133 observações com cotação e 27 em que a última atualização do preço tem mais de seis horas. Um timestamp antigo não prova que a odd fosse inválida.

## Problema técnico mais importante
Quando o diagnóstico guardado é `mercado_nao_disponivel`, o rastreio não conserva a lista de mercados/seleções que a OddsPapi devolveu. O nome e linha de origem aparecem sobretudo em capturas bem-sucedidas. Logo, **não é possível demonstrar retroativamente** se o mercado estava ausente na casa, se a designação era incompatível ou se a resposta foi insuficiente.

## Código neste ramo (apenas pesquisa)
- `scripts/diagnostico_payload_mercados_shadow.py`: função pura `inspect(mercado_modelo, payload)` para diagnóstico de **payload já recebido**, limitada a Over/Under Golos. Não usa HTTP, não guarda, não altera as odds e não fornece cotações ao bot.
- `tests/test_diagnostico_payload_mercados_shadow.py`: regressões para linhas numéricas 2.5/12.5, seleções contraditórias, mercados de cantos, períodos não comprovados, IDs numéricos de outcome, múltiplas odds e ausência de IDs/valores de odds no resultado.

Os nove cenários do protótipo foram executados localmente com sucesso. A suite completa do projeto não foi executada neste ramo, e **os resultados do protótipo não foram comparados contra payloads brutos reais de falhas**, porque esses payloads não existem nos ficheiros históricos fornecidos.

## Limites operacionais
- **Não integrar na produção durante a experiência V1.3 congelada.** Sem merge, PR, deploy, rollback ou alteração ao modelo/comercial.
- Nenhum pedido novo à OddsPapi ou a outro fornecedor.
- Os ficheiros JSON/JSONL e os relatórios por jogo são privados. **Não carregar os dados reais no GitHub público.**

## Para uma futura validação completa
1. Passar ao protótipo um payload de mercado previamente recebido em ambiente isolado ou por uma captura normal autorizada e disponível em cache (sem gerar consultas adicionais).
2. Contar razões exatas de exclusão por período, família, linha, seleção e catálogo, sem guardar odds/identificadores sensíveis.
3. Comparar a nova telemetria com a classificação atual, mantendo o motor e as previsões imutáveis.
4. Só após testes de regressão e autorização expressa estudar integração passiva de telemetria de produção. A V1.3 precisa de concluir 50 entradas e os gates originais antes de uma decisão comercial.
