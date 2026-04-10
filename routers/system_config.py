import secrets

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from config import settings
from dependencies import get_client_id, require_api_key, require_local_request
from services import audit, client_manager


router = APIRouter(dependencies=[Depends(require_local_request), Depends(require_api_key)])


class ClientConfigPayload(BaseModel):
    name: str | None = None
    access_token: str = ""
    phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    api_version: str = "v19.0"
    api_key: str = ""
    webhook_verify_token: str = ""
    public_base_url: str | None = None
    meta_app_secret: str | None = None
    simulation_mode: bool = True
    notes: str = ""


@router.get("", summary="Ler configuracao do cliente selecionado")
async def read_config(client_id: str = Depends(get_client_id)):
    client = client_manager.resolve_client(client_id, include_secrets=True)
    public_base_url = settings.PUBLIC_BASE_URL.strip()
    return {
        "client_id": client["id"],
        "name": client["name"],
        "access_token": client.get("access_token", ""),
        "phone_number_id": client.get("phone_number_id", ""),
        "whatsapp_business_account_id": client.get("whatsapp_business_account_id", ""),
        "api_version": client.get("api_version", "v19.0"),
        "api_key": settings.API_KEY,
        "webhook_verify_token": client.get("webhook_verify_token", ""),
        "public_base_url": public_base_url,
        "meta_app_secret": settings.META_APP_SECRET,
        "callback_url": f"{public_base_url.rstrip('/')}/webhook" if public_base_url else "",
        "simulation_mode": bool(client.get("simulation_mode")),
        "notes": client.get("notes", ""),
    }


@router.post("", summary="Salvar configuracao do cliente selecionado")
async def save_config(body: ClientConfigPayload, client_id: str = Depends(get_client_id)):
    current_client = client_manager.resolve_client(client_id, include_secrets=True)
    webhook_verify_token = body.webhook_verify_token.strip() or current_client.get("webhook_verify_token", "").strip()
    if not webhook_verify_token:
        webhook_verify_token = secrets.token_urlsafe(24)

    client = client_manager.update_client(
        client_id,
        name=body.name or current_client["name"],
        access_token=body.access_token,
        phone_number_id=body.phone_number_id,
        whatsapp_business_account_id=body.whatsapp_business_account_id,
        api_version=body.api_version or "v19.0",
        webhook_verify_token=webhook_verify_token,
        simulation_mode=body.simulation_mode,
        notes=body.notes,
    )
    settings_updates = {}
    if body.api_key and body.api_key != settings.API_KEY:
        settings_updates["API_KEY"] = body.api_key
    if body.public_base_url is not None:
        settings_updates["PUBLIC_BASE_URL"] = body.public_base_url.strip()
    if body.meta_app_secret is not None:
        settings_updates["META_APP_SECRET"] = body.meta_app_secret.strip()
    if settings_updates:
        settings.save(settings_updates)
    audit.record_event(
        client_id=client_id,
        event_type="client_config_saved",
        entity_type="client",
        entity_id=client_id,
        details={
            "name": client["name"] if client else body.name,
            "phone_number_id": body.phone_number_id,
            "waba_id": body.whatsapp_business_account_id,
            "api_version": body.api_version,
            "simulation_mode": body.simulation_mode,
            "public_base_url": (body.public_base_url or "").strip(),
        },
    )
    callback_base = settings.PUBLIC_BASE_URL.strip()
    return {
        "success": True,
        "message": "Configuracao do cliente atualizada com sucesso.",
        "webhook_verify_token": webhook_verify_token,
        "callback_url": f"{callback_base.rstrip('/')}/webhook" if callback_base else "",
    }
