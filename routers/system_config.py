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
    simulation_mode: bool = True
    notes: str = ""


@router.get("", summary="Ler configuracao do cliente selecionado")
async def read_config(client_id: str = Depends(get_client_id)):
    client = client_manager.resolve_client(client_id, include_secrets=True)
    return {
        "client_id": client["id"],
        "name": client["name"],
        "access_token": client.get("access_token", ""),
        "phone_number_id": client.get("phone_number_id", ""),
        "whatsapp_business_account_id": client.get("whatsapp_business_account_id", ""),
        "api_version": client.get("api_version", "v19.0"),
        "api_key": settings.API_KEY,
        "webhook_verify_token": client.get("webhook_verify_token", ""),
        "simulation_mode": bool(client.get("simulation_mode")),
        "notes": client.get("notes", ""),
    }


@router.post("", summary="Salvar configuracao do cliente selecionado")
async def save_config(body: ClientConfigPayload, client_id: str = Depends(get_client_id)):
    client = client_manager.update_client(
        client_id,
        name=body.name or client_manager.resolve_client(client_id, include_secrets=False)["name"],
        access_token=body.access_token,
        phone_number_id=body.phone_number_id,
        whatsapp_business_account_id=body.whatsapp_business_account_id,
        api_version=body.api_version or "v19.0",
        webhook_verify_token=body.webhook_verify_token,
        simulation_mode=body.simulation_mode,
        notes=body.notes,
    )
    if body.api_key and body.api_key != settings.API_KEY:
        settings.save({"API_KEY": body.api_key})
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
        },
    )
    return {"success": True, "message": "Configuracao do cliente atualizada com sucesso."}
