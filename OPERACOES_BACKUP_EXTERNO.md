# Backups externos e vigilância independente (preparado, desativado por defeito)

**Não usar este documento para colocar chaves ou tokens no GitHub, em issues ou em mensagens.**
A implementação é opcional e não é ativada apenas por fazer merge: necessita de configuração no Railway e no fornecedor escolhido. A proteção local `/backup_status` continua independente.

## 1 — Backups fora do Railway

Criar um **bucket privado** de armazenamento compatível com S3 **noutro fornecedor** (por exemplo Cloudflare R2, Backblaze B2 ou AWS S3). O bucket *research-data* já existente no Railway não constitui cópia fora desse fornecedor. Criar credenciais para esse bucket com as permissões mínimas de leitura, escrita e leitura de metadados. Não autorizar eliminações públicas nem partilha anónima.

No serviço **apostas-bot** do Railway, definir as seis variáveis:

- `BACKUP_S3_ENDPOINT_URL`: URL HTTPS S3 do fornecedor, como `https://ACCOUNT_ID.r2.cloudflarestorage.com` (substituir pelo valor fornecido)
- `BACKUP_S3_REGION`: região S3 (na Cloudflare R2 é normalmente `auto`)
- `BACKUP_S3_BUCKET`: nome do bucket privado
- `BACKUP_S3_ACCESS_KEY_ID`: ID de acesso restrito ao bucket
- `BACKUP_S3_SECRET_ACCESS_KEY`: chave secreta de acesso
- `BACKUP_AES256_KEY_B64`: chave de 32 bytes codificada em Base64 (**não é a chave S3**)

Opcional: `BACKUP_S3_PREFIX` (por defeito `apostas-bot-offsite`).

Gerar a chave AES com um Python local confiável:

```bash
python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Guardar esta chave **fora** do Railway, num gestor de palavras-passe seguro, com acesso de recuperação. Se a chave se perder, não será possível decifrar os backups. Não enviar a chave para chats.

O bot usa a cópia local diária validada em `/data/backups_locais/<data>`, cria ZIP em memória, cifra com **AES-256-GCM antes do upload**, envia por HTTPS para `prefixo/AAAA-MM-DD/estado.abk`, volta a descarregar, decifra e confirma os hashes SHA-256 e o manifesto. Só então escreve `/data/backup_externo_estado.json` como sucesso. Não guarda plaintext no bucket nem tem função automática de restauro. Se um objeto remoto já existir, verifica a sua autenticidade e **não o substitui**.

**Janela:** depois das 09h30 e antes das 18h (Portugal), tentativa de hora a hora. Evita transferências grandes na janela de CLV. **Não elimina ficheiros remotos.** Configurar uma política de ciclo de vida, por exemplo 90 dias, no fornecedor depois de definir os requisitos de retenção e legais. O custo do serviço externo é adicional ao Railway.

Comando privado: `/backup_externo_status` (apenas leitura, sem chamadas de rede). Depois da ativação confirmar que aparece «Upload e recuperacao testados» e realizar um ensaio de recuperação **fora de produção** antes de considerar o plano de recuperação de desastre completo.

## 2 — Vigilância externa que deteta paragens totais

Criar duas verificações no serviço externo **Healthchecks.io** (`https://healthchecks.io`), com alertas email (ou outro canal) configurados e testados:

1. **Bot principal:** período **5 minutos** e tolerância **15–20 minutos**, a monitorizar disponibilidade do polling Telegram. O bot envia um ping HTTPS apenas após um ciclo `getUpdates` bem-sucedido, de cinco em cinco minutos. Definir `HEALTHCHECKS_PING_URL` no Railway.
2. **Backup externo (opcional):** período **24 horas** e tolerância sugerida **8 horas**, a monitorizar um backup completo. Definir `BACKUP_HEALTHCHECKS_PING_URL` no Railway. O ping só é enviado **após** upload, download e validação do arquivo cifrado.

Utilizar os URLs privados com formato `https://hc-ping.com/<identificador>`. Não partilhar URLs: funcionam como credenciais e são omitidos dos relatórios. **Confirmar manualmente, no Healthchecks, que os avisos de ausência de ping chegam ao destino desejado.**

O Healthchecks.io (fora do Railway) deteta a ausência de pings se o container morrer. Um ping indica que o processo conseguiu consultar Telegram, **não** garante por si só que as odds ou o CLV estejam disponíveis.

Comando privado: `/vigilancia_externa_status`. O estado é apenas local: a confirmação independente faz-se no painel do Healthchecks.io.

## Segurança / protocolo de validação

- Não mexer na V1.2, SEL1, V1.3, odds congeladas, carteira ou CLV.
- Não colocar credenciais em código, PR, ações GitHub nem logs. Adicionar as variáveis **diretamente ao Railway** durante uma janela segura, sem interromper recolhas.
- Configuração parcial mantém o backup externo desativado; falhas de rede não param as previsões.
- A validação end-to-end por download **não substitui** um exercício de restauro real fora de produção.
- O próximo deploy após merge é independente e só deve ser autorizado **após** as recolhas CLV relevantes de 13/10/2026.
