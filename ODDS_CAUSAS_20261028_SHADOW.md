# Diagnóstico de cobertura OddsPapi / Betano — 28/10/2026 (SHADOW)

## Evidência da execução real das 09:00 (Railway)
- 20 seleções; 16 fixtures associados; 11 cotações; 4 sem fixture validado; 9 sem cotação no total.
- O endpoint de lote devolveu **16/16 fixtures** e bookmaker Betano presente em **16/16**. Isto **não** prova que cada mercado/linha existe.
- 4 `evento_nao_encontrado`: Degerfors IF–Västerås SK; Toronto FC–D.C. United; New England Revolution–Red Bull New York; Venezia–Internazionale.
- 3 `mercado_nao_disponivel` em Under: Heart of Midlothian–Rangers, Aberdeen–Falkirk, St Johnstone–Motherwell.
- 1 `mercado_nao_disponivel` em Ambas Marcam: St Mirren–Hibernian.
- 1 `linha_ou_selecao_nao_disponivel`: Celtic–Dundee United (Over 2.5).
- 15:19: uma recuperação sem `statusId` continuou sem encontrar 2 de 2 fixtures desta ronda.
- Eventos identificados em calendários independentes: a ausência num catálogo da OddsPapi não prova jogo inexistente.

## O que o patch #105 faz
Guarda apenas contagens passivas já recebidas: `total`, `compativeis`, `sem_catalogo`, tanto em `mercado_nao_disponivel` como em `linha_ou_selecao_nao_disponivel`. Estas passam a ser visíveis em `/odds_rastreio_detalhe <equipa>` após recolhas futuras. Não reescreve snapshots nem entra em seleção/odds. Não acrescenta pedidos HTTP.

Interpretação:
- `total=0`: a resposta não trouxe mercados ativos com preço; não se infere o que a Betano oferece fora desse instante.
- `compativeis=0, sem_catalogo>0`: catálogo incompleto possível; não concluir que o mercado está realmente ausente.
- `compativeis>0` mas sem preço: linha/outcome exato não foi confirmado; não associar preço de outra linha.
- `evento_nao_encontrado`: investigar cobertura/nome/horário/identificadores do fornecedor, nunca associar por aproximação aberta.

## Observações de integração
- A fonte principal de jogos do bot é **ESPN**, com IDs ESPN. A OddsPapi expõe `externalProviders.sofascoreId` opcional, mas **não** se pode comparar diretamente um ID ESPN com um ID SofaScore.
- A documentação da OddsPapi mostra `/v4/markets` e separação entre `bookmakerOdds`, mercados e outcomes. A presença do bookmaker não garante a presença da linha pretendida.
- Exemplos de nomes diferentes requerem prova em payloads reais (não inferir aliases só de semelhanças).
- O validador de linhas V2 está noutra investigação SHADOW e não foi ativado por este patch.

## Critérios antes de alterar a produção
1. Verificar casos com payloads sanitizados, contagens e hora/competição comprovados.
2. Testes de rejeição de jogos homónimos, jovens, mercados errados, linhas erradas, horas divergentes e odds antigas.
3. Medir em SHADOW cobertura correta e falsos positivos em mesmas seleções, com teto rígido de quota.
4. Manter a V1.3 comercial de 50 entradas congelada e exigir aprovação explícita para merge/deploy.
5. Não prometer cobertura 100%: ausência de oferta no fornecedor não é defeito do parser.

## Referências oficiais públicas
- https://oddspapi.io/us/docs/get-fixtures
- https://oddspapi.io/us/docs/get-markets
- https://oddspapi.io/us/docs/get-odds-by-tournaments
