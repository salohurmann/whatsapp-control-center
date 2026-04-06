import uuid

import httpx
from fastapi import HTTPException


def _client_value(client: dict, key: str, default: str = "") -> str:
    return str(client.get(key) or default).strip()


def should_simulate(client: dict, simulate: bool | None = None) -> bool:
    if simulate is not None:
        return simulate
    return bool(client.get("simulation_mode"))


def ensure_meta_configured(client: dict) -> None:
    access_token = _client_value(client, "access_token")
    phone_number_id = _client_value(client, "phone_number_id")
    if not access_token or not phone_number_id:
        raise HTTPException(
            status_code=400,
            detail=f"Cliente '{client.get('name', client.get('id', ''))}' sem Meta configurada. Defina ACCESS_TOKEN e PHONE_NUMBER_ID antes de enviar mensagens.",
        )


def _meta_base_url(client: dict) -> str:
    return f"https://graph.facebook.com/{_client_value(client, 'api_version', 'v19.0')}"


def _messages_url(client: dict) -> str:
    return f"{_meta_base_url(client)}/{_client_value(client, 'phone_number_id')}/messages"


def _media_url(client: dict) -> str:
    return f"{_meta_base_url(client)}/{_client_value(client, 'phone_number_id')}/media"


def _auth_headers(client: dict) -> dict:
    return {
        "Authorization": f"Bearer {_client_value(client, 'access_token')}",
        "Content-Type": "application/json",
    }


def _simulated_message_response(to: str, status: str = "accepted") -> dict:
    return {
        "contacts": [{"wa_id": to}],
        "messages": [{"id": f"sim-{uuid.uuid4().hex[:18]}", "message_status": status}],
    }


def _normalize_template_components(components: list | None) -> list[dict]:
    normalized: list[dict] = []
    for component in components or []:
        if hasattr(component, "model_dump"):
            raw = component.model_dump(exclude_none=True)
        elif isinstance(component, dict):
            raw = dict(component)
        else:
            raw = {
                "type": getattr(component, "type", None),
                "sub_type": getattr(component, "sub_type", None),
                "index": getattr(component, "index", None),
                "parameters": getattr(component, "parameters", []),
            }

        item = {
            "type": raw.get("type"),
            "parameters": list(raw.get("parameters") or []),
        }
        if raw.get("sub_type"):
            item["sub_type"] = raw["sub_type"]
        if raw.get("index") is not None:
            item["index"] = raw["index"]
        normalized.append(item)
    return normalized


def _raise_for_meta_error(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text}

    if response.is_error:
        error_msg = body.get("error", {}).get("message", "Erro desconhecido da Meta API")
        raise HTTPException(status_code=response.status_code, detail=error_msg)

    return body


async def send_text(
    client: httpx.AsyncClient,
    client_config: dict,
    to: str,
    message: str,
    preview_url: bool = False,
    simulate: bool | None = None,
) -> dict:
    if should_simulate(client_config, simulate):
        return _simulated_message_response(to)
    ensure_meta_configured(client_config)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": preview_url,
            "body": message,
        },
    }
    resp = await client.post(_messages_url(client_config), json=payload, headers=_auth_headers(client_config))
    return _raise_for_meta_error(resp)


async def send_media(
    client: httpx.AsyncClient,
    client_config: dict,
    to: str,
    media_type: str,
    media_id: str | None = None,
    media_url: str | None = None,
    caption: str | None = None,
    filename: str | None = None,
    simulate: bool | None = None,
) -> dict:
    if should_simulate(client_config, simulate):
        return _simulated_message_response(to)
    ensure_meta_configured(client_config)

    media_obj: dict = {}
    if media_id:
        media_obj["id"] = media_id
    else:
        media_obj["link"] = media_url

    if caption and media_type in ("image", "video", "document"):
        media_obj["caption"] = caption

    if filename and media_type == "document":
        media_obj["filename"] = filename

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": media_type,
        media_type: media_obj,
    }
    resp = await client.post(_messages_url(client_config), json=payload, headers=_auth_headers(client_config))
    return _raise_for_meta_error(resp)


async def upload_media(
    client: httpx.AsyncClient,
    client_config: dict,
    file_bytes: bytes,
    mime_type: str,
    filename: str,
    simulate: bool | None = None,
) -> dict:
    if should_simulate(client_config, simulate):
        return {"id": f"sim-media-{uuid.uuid4().hex[:12]}"}
    ensure_meta_configured(client_config)
    headers = {"Authorization": f"Bearer {_client_value(client_config, 'access_token')}"}
    files = {
        "file": (filename, file_bytes, mime_type),
        "type": (None, mime_type),
        "messaging_product": (None, "whatsapp"),
    }
    resp = await client.post(_media_url(client_config), headers=headers, files=files)
    return _raise_for_meta_error(resp)


async def send_template(
    client: httpx.AsyncClient,
    client_config: dict,
    to: str,
    template_name: str,
    language_code: str,
    components: list | None = None,
    simulate: bool | None = None,
) -> dict:
    if should_simulate(client_config, simulate):
        return _simulated_message_response(to)
    ensure_meta_configured(client_config)

    template_obj: dict = {
        "name": template_name,
        "language": {"code": language_code},
    }

    normalized_components = _normalize_template_components(components)
    if normalized_components:
        template_obj["components"] = normalized_components

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": template_obj,
    }
    resp = await client.post(_messages_url(client_config), json=payload, headers=_auth_headers(client_config))
    return _raise_for_meta_error(resp)
