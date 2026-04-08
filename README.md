# WhatsApp API - Console Operacional

API em FastAPI para operacao com WhatsApp Business Cloud API, com painel web, webhook publico e estrutura pronta para hospedagem.

## O que o projeto entrega

- envio de texto, midia e templates
- campanhas em fila com persistencia SQLite
- painel web para operacao
- webhook publico da Meta em `/webhook`
- backups, auditoria e lista de supressao
- diagnostico visual por cliente no painel
- deploy pronto com `Dockerfile`, `Procfile` e `start_server.py`

## Arquivos importantes

- `main.py`: sobe a API e registra as rotas
- `start_server.py`: entrada pronta para hospedagem
- `routers/webhooks.py`: validacao e recebimento do webhook da Meta
- `routers/bulk.py`: fila e campanhas
- `services/bulk_manager.py`: processamento da fila
- `services/storage.py`: schema SQLite
- `painel.html`: painel web
- `DEPLOY.md`: guia curto de deploy

## Variaveis de ambiente

Exemplo base:

```env
APP_ENV=production
HOST=0.0.0.0
PORT=8000
PUBLIC_BASE_URL=https://seu-dominio.com
META_APP_SECRET=seu_app_secret_meta
ACCESS_TOKEN=seu_token_permanente
PHONE_NUMBER_ID=seu_phone_number_id
WHATSAPP_BUSINESS_ACCOUNT_ID=seu_waba_id
API_VERSION=v19.0
API_KEY=sua_chave_forte
SIMULATION_MODE=false
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,https://seu-dominio.com
BULK_DB_PATH=/data/whatsapp_bulk.db
WEBHOOK_VERIFY_TOKEN=seu_token_de_webhook
LOG_FILE_PATH=/app/logs/app.log
BACKUP_DIR=/app/backups
REMOTE_ADMIN_ENABLED=false
```

## Desenvolvimento local

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Painel:

```text
http://localhost:8000/painel
```

## Hospedagem

Comando de start:

```bash
python start_server.py
```

Docker:

```bash
docker build -t wa-prod .
docker run --env-file .env -p 8000:8000 -v wa_prod_data:/data wa-prod
```

Detalhes:

- [DEPLOY.md](DEPLOY.md)

## Webhook da Meta

Configure no app da Meta:

```text
Callback URL: https://SEU_HOST/webhook
Verify token: valor de WEBHOOK_VERIFY_TOKEN
```

O endpoint legado `/webhooks/meta` continua funcionando.

## Painel hospedado

- acesso em `https://seu-dominio.com/painel`
- o painel usa o mesmo dominio da API por padrao
- em hospedagem, o projeto agora assume `SIMULATION_MODE=false` por padrao
- em hospedagem, o projeto agora assume `REMOTE_ADMIN_ENABLED=true` por padrao
- use a `API_KEY` no painel para ler e salvar configuracoes sensiveis
- o painel mostra um diagnostico do cliente com callback URL, segredos mascarados e alertas de prontidao

## Para operar com a Meta de verdade

Preencha no painel hospedado ou nas variaveis do provedor:

- `ACCESS_TOKEN`
- `PHONE_NUMBER_ID`
- `WHATSAPP_BUSINESS_ACCOUNT_ID`
- `WEBHOOK_VERIFY_TOKEN`
- `META_APP_SECRET`
- `PUBLIC_BASE_URL`

Sem esses valores, o app sobe hospedado, mas nao consegue enviar mensagens reais pela Meta.

## Observacoes operacionais

- use apenas contatos com opt-in
- em SQLite hospedado, prefira um disco persistente montado em `/data`
- se for distribuir para muitos clientes, o proximo passo natural e separar dados por conta/tenant
