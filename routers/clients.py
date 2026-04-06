from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import get_client_id, require_api_key, require_local_request
from services import audit, client_manager


router = APIRouter(dependencies=[Depends(require_local_request), Depends(require_api_key)])


class ClientCreatePayload(BaseModel):
    name: str
    simulation_mode: bool = True
    notes: str = ""


class ClientUpdatePayload(BaseModel):
    name: str | None = None
    status: str | None = None
    notes: str | None = None


@router.get("", summary="Listar clientes operados")
async def list_clients():
    return client_manager.list_clients(include_secrets=False)


@router.post("", summary="Criar cliente")
async def create_client(body: ClientCreatePayload):
    client = client_manager.create_client(
        name=body.name,
        simulation_mode=body.simulation_mode,
        notes=body.notes,
    )
    audit.record_event(
        client_id=client["id"],
        event_type="client_created",
        entity_type="client",
        entity_id=client["id"],
        details={"name": client["name"]},
    )
    return client


@router.get("/current", summary="Ler cliente selecionado")
async def get_current_client(client_id: str = Depends(get_client_id)):
    client = client_manager.get_client(client_id, include_secrets=False)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado.")
    return client


@router.get("/current/diagnostics", summary="Diagnostico operacional do cliente selecionado")
async def get_current_client_diagnostics(client_id: str = Depends(get_client_id)):
    return client_manager.build_client_diagnostics(client_id)


@router.patch("/{client_id}", summary="Atualizar dados basicos do cliente")
async def update_client(client_id: str, body: ClientUpdatePayload):
    client = client_manager.update_client(
        client_id,
        name=body.name if body.name is not None else None,
        status=body.status if body.status is not None else None,
        notes=body.notes if body.notes is not None else None,
    )
    if not client:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado.")
    audit.record_event(
        client_id=client_id,
        event_type="client_updated",
        entity_type="client",
        entity_id=client_id,
        details={"name": client["name"], "status": client["status"]},
    )
    return client
