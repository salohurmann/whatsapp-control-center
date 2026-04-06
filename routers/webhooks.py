import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from config import settings
from dependencies import get_client_id, require_api_key
from services import client_manager, webhooks


router = APIRouter()
meta_router = APIRouter()


async def _verify_meta_webhook(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token:
        clients = client_manager.list_clients(include_secrets=False)
        if any((client.get("webhook_verify_token") or "").strip() == hub_verify_token for client in clients):
            return PlainTextResponse(str(hub_challenge))
    raise HTTPException(status_code=403, detail="Webhook verify token invalido.")


def _validate_signature(signature_header: str | None, body: bytes) -> None:
    if not settings.META_APP_SECRET.strip():
        return
    if not signature_header:
        raise HTTPException(status_code=403, detail="Assinatura do webhook ausente.")
    expected = "sha256=" + hmac.new(
        settings.META_APP_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature_header.strip()):
        raise HTTPException(status_code=403, detail="Assinatura do webhook invalida.")


async def _receive_meta_webhook(request: Request, x_hub_signature_256: str | None = None):
    body = await request.body()
    _validate_signature(x_hub_signature_256, body)
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Payload de webhook invalido.") from exc
    processed = webhooks.process_payload(payload)
    return {"success": True, **processed}


@router.get("/meta", summary="Verificacao do webhook da Meta")
async def verify_meta_webhook(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    return await _verify_meta_webhook(hub_mode, hub_verify_token, hub_challenge)


@meta_router.get("", include_in_schema=False)
async def verify_meta_webhook_alias(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    return await _verify_meta_webhook(hub_mode, hub_verify_token, hub_challenge)


@router.post("/meta", summary="Receber eventos do webhook da Meta")
async def receive_meta_webhook(request: Request, x_hub_signature_256: str | None = Header(default=None)):
    return await _receive_meta_webhook(request, x_hub_signature_256)


@meta_router.post("", include_in_schema=False)
async def receive_meta_webhook_alias(request: Request, x_hub_signature_256: str | None = Header(default=None)):
    return await _receive_meta_webhook(request, x_hub_signature_256)


@router.get("/events", summary="Listar eventos recentes do webhook")
async def list_recent_events(_: str = Depends(require_api_key), client_id: str = Depends(get_client_id)):
    return webhooks.recent_events(client_id=client_id)
