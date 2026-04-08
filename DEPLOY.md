# Deploy

## Pronto para hospedar

O projeto agora aceita:

- porta dinamica via `PORT`
- host dinamico via `HOST`
- painel usando o mesmo dominio da API por padrao
- webhook publico em `/webhook`
- configuracao remota habilitada por padrao via `REMOTE_ADMIN_ENABLED=true`
- simulacao desligada por padrao via `SIMULATION_MODE=false`

## Variaveis de ambiente

Defina no provedor:

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
API_KEY=uma_chave_forte
SIMULATION_MODE=false
ALLOWED_ORIGINS=https://seu-dominio.com
BULK_DB_PATH=/data/whatsapp_bulk.db
WEBHOOK_VERIFY_TOKEN=seu_token_de_verificacao
LOG_FILE_PATH=/app/logs/app.log
BACKUP_DIR=/app/backups
REMOTE_ADMIN_ENABLED=true
```

## Docker

Build local:

```bash
docker build -t wa-prod .
```

Run local:

```bash
docker run --env-file .env -p 8000:8000 -v wa_prod_data:/data wa-prod
```

## Render / Railway / Coolify

- comando de start: `python start_server.py`
- ou use o `Dockerfile`
- monte disco persistente para `/data` se quiser manter o SQLite

## Webhook da Meta

Use no painel da Meta:

```text
Callback URL: https://seu-dominio.com/webhook
Verify token: valor de WEBHOOK_VERIFY_TOKEN
```

## Painel

Depois do deploy:

```text
https://seu-dominio.com/painel
```

Se `REMOTE_ADMIN_ENABLED=false`, as configuracoes sensiveis devem ser definidas no painel do provedor.
Se `REMOTE_ADMIN_ENABLED=true`, o painel remoto pode ler e salvar `.env`, desde que voce informe a `API_KEY`.
Use o card de diagnostico no painel para confirmar callback URL, prontidao para campanhas e alertas de configuracao antes de operar.
Para envio real pela Meta, preencha `ACCESS_TOKEN`, `PHONE_NUMBER_ID`, `WHATSAPP_BUSINESS_ACCOUNT_ID`, `WEBHOOK_VERIFY_TOKEN`, `META_APP_SECRET` e `PUBLIC_BASE_URL`.
