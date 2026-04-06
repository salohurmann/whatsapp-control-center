from contextlib import asynccontextmanager
import asyncio
import os

import httpx
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from config import settings
from dependencies import get_client_id
from models.responses import HealthResponse
from routers import admin, bulk, clients, media, messages, system_config, templates, webhooks
from services import bulk_manager, client_manager
from services.ops import setup_logging
from services.storage import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    setup_logging()
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    app.state.bulk_worker = asyncio.create_task(bulk_manager.worker_loop(app))
    app.state.last_worker_error = None
    yield
    app.state.bulk_worker.cancel()
    try:
        await app.state.bulk_worker
    except asyncio.CancelledError:
        pass
    await app.state.http_client.aclose()


app = FastAPI(
    title="WhatsApp Business API",
    description=(
        "API para envio de mensagens via WhatsApp Business Cloud API.\n\n"
        "Fluxo recomendado:\n"
        "1. Cadastre um ou mais clientes no painel\n"
        "2. Configure as credenciais Meta por cliente\n"
        "3. Opere envios unitarios ou campanhas em massa\n"
        "4. Receba status em /webhook"
    ),
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/painel", include_in_schema=False, summary="Painel visual de operacoes")
async def painel():
    painel_path = os.path.join(os.path.dirname(__file__), "painel.html")
    return FileResponse(painel_path)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/painel", status_code=307)


app.include_router(messages.router, prefix="/messages", tags=["Mensagens"])
app.include_router(media.router, prefix="/media", tags=["Midia"])
app.include_router(templates.router, prefix="/templates", tags=["Templates"])
app.include_router(bulk.router, prefix="/bulk", tags=["Disparo em Massa"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
app.include_router(webhooks.meta_router, prefix="/webhook")
app.include_router(clients.router, prefix="/clients", tags=["Clientes"])
app.include_router(system_config.router, prefix="/system/config", tags=["Configuracao"])
app.include_router(admin.router, prefix="/admin", tags=["Administracao"])


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Sistema"],
    summary="Verificar status do servidor",
)
async def health(client_id: str = Depends(get_client_id)):
    client = client_manager.resolve_client(client_id, include_secrets=True)
    return HealthResponse(
        status="ok",
        version="3.0.0",
        phone_number_id=client.get("phone_number_id") or "NAO CONFIGURADO",
        simulation_mode=bool(client.get("simulation_mode", settings.SIMULATION_MODE_ENABLED)),
        meta_configured=bool(client.get("access_token") and client.get("phone_number_id")),
    )
