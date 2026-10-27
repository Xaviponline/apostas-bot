# Diagnóstico de mercados — SHADOW (26/10/2026)

Este ramo contém apenas **instrumentação passiva e testes sintéticos**. Não altera o motor, a escolha de mercados, a V1.3 Comercial, a coorte dos 50, a carteira, o CLV, os agendamentos, nem qualquer fonte de odds.

## Conteúdo

- `mercados_diagnostico_shadow.py` — validador puramente em memória de tipo de mercado, período, lado Over/Under, linha, handicap e texto de seleção. Em caso de dúvida, rejeita. O resultado de `diagnose_payload` é apenas agregado: contagens por motivo sem guardar payloads.
- `tests/test_mercados_diagnostico_shadow_20261026.py` — 18 testes sintéticos, incluindo regressões para as confusões 2.5/12.5, períodos errados, handicap/seleção contraditórios e associações ambíguas.

Executar **apenas os testes isolados**:

```bash
python -m unittest discover -s tests -p 'test_mercados_diagnostico_shadow_20261026.py' -v
```

**Estado:** os 18 testes foram executados num ambiente Python local, todos aprovados. O replay privado das 133 capturas válidas de outubro foi executado separadamente e todas foram aceites pelo validador quanto aos campos efetivamente disponíveis. Esta última verificação não prova que o fixture ou a competição sejam corretos, nem que as cotações eram executáveis na casa.

## Limites e riscos

1. Não existem payloads completos para as tentativas `mercado_nao_disponivel` no rastreio histórico disponível. O diagnóstico atual não demonstra se o mercado não existia ou se o parser original não o reconheceu.
2. Não se deve executar este protótipo automaticamente em produção nem usá-lo como fonte alternativa de odds. Antes de eventual integração será necessário rever formatos reais, casos sem período e condições de compatibilidade.
3. Diagnóstico passivo futuramente integrado teria de operar **só sobre respostas já recebidas** (zero novas consultas), com limitação do conteúdo e da retenção; isso exige uma alteração e deploy separados, depois de terminar ou isolar a experiência.
4. Não guardar dados de produção, tokens nem histórico privado num GitHub público.

**Sem PR, sem merge, sem deploy e sem consumo de quota.**
