# Bot de apostas — versão de manutenção

Esta revisão corrige o registo e as contas. **Não é ainda um analista automático de apostas.**
As recomendações, as consultas SofaScore e as notificações automáticas foram suspensas:
a implementação recebida usava dados inventados e não recolhia odds da Betano.
A revisão é preparada numa branch de manutenção. Só deve ser aplicada em produção depois de salvaguardar o histórico e configurar credenciais e volume.

## Antes de instalar

1. Revoga o token antigo no BotFather e gera um novo. O ZIP original continha o token
   no código e no README. Não o voltes a publicar ou enviar em conversas.
2. Faz uma cópia do `apostas_historico.json` do serviço antigo **antes** de o substituir.
   Esse histórico não vinha no ZIP e não foi possível recuperá-lo ou migrá-lo aqui.
3. Mantém apenas um processo do bot em execução. Esta versão usa um JSON local
   para uma banca privada, com um utilizador e uma conversa autorizados.

## Instalação no Railway

- Coloca estes ficheiros na raiz do projeto usado pelo serviço, ou configura a raiz
  para a pasta `bot-apostas`. Usa Python 3.11 ou superior.
- Dependências: `pip install -r requirements.txt`.
- Comando de arranque: `python main_sofascore.py`. O Procfile já aponta para esse ficheiro.
  Se existir um comando personalizado nas definições do serviço, verifica-o também.
- Configura `TELEGRAM_BOT_TOKEN` com o novo token, nas variáveis do serviço.
  O nome antigo `TELEGRAM_TOKEN` também é aceite. Se ambos existirem, `TELEGRAM_BOT_TOKEN` tem prioridade. O programa não lê automaticamente um `.env` local.
- Liga um volume persistente ao serviço em `/data` e define `DATA_DIR=/data`.
  Apenas definir a variável não cria o volume.
- Para conservar os registos antigos, coloca a cópia do histórico em
  `/data/apostas_historico.json` **antes** de iniciar a nova versão.
- Sem `OWNER_USER_ID` e `ALLOWED_CHAT_ID`, apenas `/id` responde. Inicia o serviço
  com o token novo, envia `/id` ao bot (ou `/id@NomeDoBot` no grupo pretendido),
  e usa os números devolvidos para preencher essas duas variáveis. Reinicia o serviço.
- `OWNER_USER_ID` é o teu ID pessoal; `ALLOWED_CHAT_ID` é a conversa autorizada.
  Num grupo, o ID da conversa pode ser negativo. As respostas nesse grupo são visíveis
  aos membros, mas apenas tu podes consultar o histórico e registar apostas/resultados.
- Se estiver configurado um webhook, o bot interrompe o arranque. Resolver essa
  configuração antes de usar polling; esta versão não elimina webhooks automaticamente.

## Utilização

```
/start
/analisa
/add_aposta "Equipa A vs Equipa B" "Over 2.5 Golos" 1.90 1.00
/resultados
/score 1 ganhou
/score 1 perdeu
/score 1 anulada
/score 1 2-1
/status
```

O exemplo é apenas um formato, não uma sugestão para apostar.
`/add_aposta` regista uma aposta que já fizeste: jogo, mercado, odd decimal e valor em euros.
Aceita vírgula decimal e valores positivos com até duas casas decimais.
Não coloca apostas nem confirma odds na Betano.

`/score` usa o ID real devolvido no registo. Um resultado já registado não é substituído
por outro silenciosamente. A correção de erros de liquidação ainda exige intervenção
no histórico com o bot parado e uma cópia de segurança; não há comando de retificação.

O marcador deve ser final, do tempo regulamentar com compensação, sem prolongamento
ou penáltis. Só é interpretado nos mercados Vitória Casa, Vitória Fora, Ambas Marcam,
Over 2.5 Golos e Over 3.5 Golos. Mercados diferentes, cash-out, meias vitórias/perdas,
handicaps asiáticos e múltiplas não têm liquidação automática implementada.
Uma múltipla pode ser registada como uma única aposta e liquidada manualmente por
resultado, mas não são acompanhadas as suas seleções individualmente.

## Como são feitas as contas

- Vitória: lucro = valor apostado × (odd − 1).
- Derrota: lucro = −valor apostado.
- Anulada: lucro zero; excluída do denominador do ROI e da taxa de acerto.
- ROI = lucro das apostas liquidadas / soma dos valores dessas apostas × 100.
- Apostas pendentes não entram no ROI realizado.
- Registos antigos sem origem manual confirmada ficam preservados e excluídos das
  contas. Não é atribuído um valor fictício de 1 € nem uma confirmação retroativa.
- Valores apresentados arredondados aos cêntimos; o cálculo pode diferir por cêntimos
  de regras de arredondamento da casa. Não inclui promoções, impostos ou cash-out.

Esta versão mostra lucro das apostas registadas, não saldo bancário nem saldo Betano.
Não impõe uma banca inicial de 18,55 € porque esse saldo atual não foi confirmado.

## Validação local

```
python -m unittest discover -s tests -v
```

Os testes usam ficheiros temporários e comunicação simulada. Não enviam mensagens,
não colocam apostas e não usam o token real. Consulta `VALIDACAO.txt`.
A instalação em produção, entrega de mensagens e persistência do volume têm de ser
verificadas no teu serviço após configuração. Não há garantia de rentabilidade.

## Para voltar à análise automática

É necessário integrar uma fonte de jogos/resultados com IDs estáveis e uma fonte de
odds que cubra explicitamente a Betano Portugal, com mercado e hora da recolha.
Depois, avaliar o modelo de probabilidades em jogos históricos separados dos usados
para o ajustar. As sugestões devem ficar separadas das apostas realmente feitas.
O bot deve conseguir não recomendar nenhuma aposta quando não há dados ou valor
suficientes; não deve relaxar filtros para preencher uma quota diária.

## Referências de configuração

- [Telegram Bot API: polling](https://core.telegram.org/bots/api#getupdates)
- [Telegram: comandos e BotFather](https://core.telegram.org/bots/features)
- [Railway: volumes persistentes](https://docs.railway.com/volumes)

O ficheiro legado analista_dinamico_total.py não é usado pelo bot desta revisão.
