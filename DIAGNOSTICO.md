# Revisão do código recebido — 14/09/2026

Conclusões obtidas por leitura do ZIP original; a ligação ao repositório foi verificada depois. Não foi usado o token nele incluído
nem consultado o serviço de produção. O relatório PDF não comprova os testes aí declarados.

| Problema confirmado | Local original | Tratamento nesta revisão |
| --- | --- | --- |
| Token escrito diretamente no código e repetido na documentação | main_sofascore.py; README_PROJETO.md | Removido do pacote; leitura por variável. Revogação depende do titular. |
| Arranque aponta para main.py, ausente do ZIP | Procfile | Corrigido para main_sofascore.py. |
| Jogos e horários fictícios se não há resposta | BuscadorJogosReais._gerar_jogos_fallback | Conector suspenso; sem dados de substituição. |
| IDs aleatórios usados para consultar equipas | AnalisadorInteligente.gerar_aposta | Gerador antigo removido da versão de manutenção. |
| Probabilidades e odds com random.uniform | Métodos de probabilidade e _prob_para_odds | Recomendações suspensas; sem ligação Betano implementada. |
| Vitória fora calculada como 1 − vitória casa, ignorando empate | gerar_aposta | Modelo retirado até substituição validada. |
| Totais de golos usados como médias | calcular_probabilidade_over; calcular_probabilidade_ambas_marcam | Modelo retirado. |
| hash(dict) lança TypeError quando falta forma; erros são ocultados | calcular_probabilidade_vitoria; gerar_apostas_jogo | Caminho removido com o modelo antigo. |
| Filtros relaxados até aceitar todas as sugestões | gerar_todas_apostas | Sem quota de 15 nem relaxamento. |
| Consultar /analisa grava sugestões como apostas e repete registos | processar_comando | Só /add_aposta grava apostas confirmadas pelo utilizador. |
| Numeração mostrada começa em 1 a cada análise, diferente do histórico | processar_comando | É devolvido o ID persistido. |
| Lucro igual a número de ganhas menos perdidas; sem stake | calcular_estatisticas | Lucro por odd e stake; ROI ponderado. |
| Qualquer remetente pode consultar e alterar o histórico global | processar_comando | Um utilizador e uma conversa autorizados. |
| Comandos com sufixo @bot não são reconhecidos | processar_comando | Reconhecimento do nome verificado por getMe. |
| /status afirma SofaScore online sem confirmação | processar_comando | Estado explícito: ligação não validada. |
| JSON inválido é substituído em memória por histórico vazio | carregar_ou_criar | Arranque interrompido, sem sobrescrever ficheiro. |
| Escrita direta pode deixar ficheiro incompleto | guardar | Ficheiro temporário, fsync e substituição atómica. |
| Token e dados pessoais podem aparecer em logs de pedidos/erros | main_sofascore.py | Sem impressão do texto de comandos, URLs ou exceções de rede. |
| Rastreio automático anunciado não é invocado pelo ciclo do bot | rastreador_resultados.py; main_sofascore.py | Liquidação manual explicitamente identificada. |
| Alertas dependem da hora do servidor e de subscritores só em memória | analise_automatica | Agendamento suspenso com as recomendações. |

O buscador original também não propaga IDs de equipas nos jogos recebidos pela rede
e compara `status` diretamente com texto. Não há amostras de respostas no ZIP para
validar o contrato real do fornecedor. Não foi afirmado que qualquer endpoint SofaScore
está funcional, bloqueado ou corrigido. A próxima integração tem de validar esse contrato.

Ficheiros de execução foram revistos para uma versão de manutenção limitada, não uma
substituição completa do produto automático pretendido. O PDF histórico não foi incluído
no pacote revisto para não apresentar a conclusão antiga de “90%” como estado atual.

## Verificação posterior no GitHub e Railway

O repositório contém main.py: a inconsistência de arranque era do ZIP, não do repositório ativo. Nesta revisão main.py passa a encaminhar para main_sofascore.py. O Railway usa TELEGRAM_TOKEN; a revisão aceita esse nome além de TELEGRAM_BOT_TOKEN. O serviço ativo não tem volume persistente. A publicação em produção aguarda salvaguarda do histórico e rotação do token.
