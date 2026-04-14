import re
import uuid
from datetime import datetime
from typing import Any

from config import settings
from services.storage import get_db

PLACEHOLDER_PREFIXES = ("COLE_SEU_", "SEU_", "YOUR_", "CHANGE_ME")


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return normalized or f"cliente-{uuid.uuid4().hex[:6]}"


def unique_slug(base_slug: str, excluding_client_id: str | None = None) -> str:
    candidate = base_slug or f"cliente-{uuid.uuid4().hex[:6]}"
    counter = 2
    while True:
        with get_db() as conn:
            row = conn.execute(
                "SELECT id FROM clients WHERE slug = ?",
                (candidate,),
            ).fetchone()
        if not row or row["id"] == excluding_client_id:
            return candidate
        candidate = f"{base_slug}-{counter}"
        counter += 1


def build_client_payload(
    *,
    client_id: str,
    name: str,
    access_token: str = "",
    phone_number_id: str = "",
    whatsapp_business_account_id: str = "",
    api_version: str = "v19.0",
    webhook_verify_token: str = "",
    simulation_mode: bool = True,
    status: str = "active",
    notes: str = "",
) -> dict[str, Any]:
    return {
        "id": client_id,
        "name": name.strip() or client_id,
        "slug": unique_slug(slugify(name or client_id), excluding_client_id=client_id),
        "access_token": access_token.strip(),
        "phone_number_id": phone_number_id.strip(),
        "whatsapp_business_account_id": whatsapp_business_account_id.strip(),
        "api_version": (api_version or "v19.0").strip(),
        "webhook_verify_token": webhook_verify_token.strip(),
        "simulation_mode": 1 if simulation_mode else 0,
        "status": (status or "active").strip(),
        "notes": notes.strip(),
    }


def ensure_default_client() -> None:
    with get_db() as conn:
        row = conn.execute("SELECT id FROM clients LIMIT 1").fetchone()
        if row:
            return
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO clients (
                id, name, slug, access_token, phone_number_id,
                whatsapp_business_account_id, api_version, webhook_verify_token,
                simulation_mode, status, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "default",
                "Operacao Principal",
                "operacao-principal",
                settings.ACCESS_TOKEN,
                settings.PHONE_NUMBER_ID,
                settings.WHATSAPP_BUSINESS_ACCOUNT_ID,
                settings.API_VERSION,
                settings.WEBHOOK_VERIFY_TOKEN,
                1 if settings.SIMULATION_MODE_ENABLED else 0,
                "active",
                "Cliente inicial criado automaticamente a partir do .env.",
                now,
                now,
            ),
        )


def list_clients(include_secrets: bool = False) -> list[dict[str, Any]]:
    columns = """
        id, name, slug, phone_number_id, whatsapp_business_account_id,
        api_version, webhook_verify_token, simulation_mode, status, notes,
        created_at, updated_at
    """
    if include_secrets:
        columns = "access_token, " + columns
    with get_db() as conn:
        rows = conn.execute(f"SELECT {columns} FROM clients ORDER BY updated_at DESC, name ASC").fetchall()
    return [dict(row) for row in rows]


def get_client(client_id: str, include_secrets: bool = False) -> dict[str, Any] | None:
    columns = """
        id, name, slug, phone_number_id, whatsapp_business_account_id,
        api_version, webhook_verify_token, simulation_mode, status, notes,
        created_at, updated_at
    """
    if include_secrets:
        columns = "access_token, " + columns
    with get_db() as conn:
        row = conn.execute(f"SELECT {columns} FROM clients WHERE id = ?", (client_id,)).fetchone()
    return dict(row) if row else None


def get_first_client(include_secrets: bool = False) -> dict[str, Any] | None:
    default_client = get_client("default", include_secrets=include_secrets)
    if default_client:
        return default_client
    clients = list_clients(include_secrets=include_secrets)
    return clients[0] if clients else None


def resolve_client(client_id: str | None = None, include_secrets: bool = True) -> dict[str, Any]:
    if client_id:
        client = get_client(client_id, include_secrets=include_secrets)
        if client:
            return client
    client = get_first_client(include_secrets=include_secrets)
    if not client:
        raise ValueError("Nenhum cliente cadastrado.")
    return client


def mask_secret(value: str, *, keep_start: int = 4, keep_end: int = 4) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    if len(clean) <= keep_start + keep_end:
        return "*" * len(clean)
    middle = "*" * max(len(clean) - (keep_start + keep_end), 4)
    return f"{clean[:keep_start]}{middle}{clean[-keep_end:]}"


def looks_like_placeholder(value: str) -> bool:
    clean = str(value or "").strip().upper()
    return any(clean.startswith(prefix) for prefix in PLACEHOLDER_PREFIXES)


def build_client_diagnostics(client_id: str) -> dict[str, Any]:
    client = resolve_client(client_id, include_secrets=True)
    simulation_mode = bool(client.get("simulation_mode"))
    access_token = str(client.get("access_token") or "").strip()
    phone_number_id = str(client.get("phone_number_id") or "").strip()
    waba_id = str(client.get("whatsapp_business_account_id") or "").strip()
    webhook_verify_token = str(client.get("webhook_verify_token") or "").strip()

    warnings: list[str] = []
    recommendations: list[str] = []

    if simulation_mode:
        recommendations.append("Cliente em simulacao local. Envios reais e status reais da Meta nao serao recebidos.")
    else:
        if not access_token:
            warnings.append("Access Token nao configurado.")
        elif looks_like_placeholder(access_token):
            warnings.append("Access Token ainda parece ser um valor de exemplo/place-holder.")
        if not phone_number_id:
            warnings.append("Phone Number ID nao configurado.")
        elif looks_like_placeholder(phone_number_id):
            warnings.append("Phone Number ID ainda parece ser um valor de exemplo/place-holder.")
        if not waba_id:
            warnings.append("WABA ID nao configurado.")
        if not webhook_verify_token:
            warnings.append("Webhook Verify Token nao configurado.")
        elif looks_like_placeholder(webhook_verify_token):
            warnings.append("Webhook Verify Token ainda parece ser um valor de exemplo/place-holder.")
        recommendations.append("Para disparo inicial em massa, prefira template aprovado na Meta.")

    public_base_url = ""
    callback_url = ""
    if settings.PUBLIC_BASE_URL.strip():
        public_base_url = settings.PUBLIC_BASE_URL.strip().rstrip("/")
        callback_url = f"{public_base_url}/webhook"
    else:
        warnings.append("PUBLIC_BASE_URL nao configurada. Defina uma URL publica HTTPS para o webhook em hospedagem.")

    if settings.META_APP_SECRET.strip():
        recommendations.append("Assinatura do webhook habilitada com META_APP_SECRET.")
    else:
        warnings.append("META_APP_SECRET nao configurado. O webhook nao valida assinatura da Meta.")

    ready_for_live = not simulation_mode and bool(
        access_token
        and phone_number_id
        and webhook_verify_token
        and not looks_like_placeholder(access_token)
        and not looks_like_placeholder(phone_number_id)
        and not looks_like_placeholder(webhook_verify_token)
    )
    return {
        "client_id": client["id"],
        "name": client["name"],
        "status": client.get("status", "active"),
        "simulation_mode": simulation_mode,
        "meta_configured": bool(access_token and phone_number_id),
        "webhook_ready": bool(webhook_verify_token and callback_url),
        "ready_for_live": ready_for_live,
        "ready_for_text_campaign": ready_for_live,
        "ready_for_template_campaign": ready_for_live and bool(waba_id),
        "api_version": client.get("api_version", "v19.0"),
        "phone_number_id": phone_number_id,
        "waba_id": waba_id,
        "access_token_masked": mask_secret(access_token),
        "webhook_verify_token_masked": mask_secret(webhook_verify_token),
        "public_base_url": public_base_url,
        "callback_url": callback_url,
        "warnings": warnings,
        "recommendations": recommendations,
    }


def find_client_by_phone_number_id(phone_number_id: str) -> dict[str, Any] | None:
    if not phone_number_id:
        return None
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT access_token, id, name, slug, phone_number_id, whatsapp_business_account_id,
                   api_version, webhook_verify_token, simulation_mode, status, notes, created_at, updated_at
            FROM clients
            WHERE phone_number_id = ?
            LIMIT 1
            """,
            (str(phone_number_id).strip(),),
        ).fetchone()
    return dict(row) if row else None


def create_client(
    *,
    name: str,
    access_token: str = "",
    phone_number_id: str = "",
    whatsapp_business_account_id: str = "",
    api_version: str = "v19.0",
    webhook_verify_token: str = "",
    simulation_mode: bool = True,
    status: str = "active",
    notes: str = "",
) -> dict[str, Any]:
    client_id = f"cli_{uuid.uuid4().hex[:10]}"
    payload = build_client_payload(
        client_id=client_id,
        name=name,
        access_token=access_token,
        phone_number_id=phone_number_id,
        whatsapp_business_account_id=whatsapp_business_account_id,
        api_version=api_version,
        webhook_verify_token=webhook_verify_token,
        simulation_mode=simulation_mode,
        status=status,
        notes=notes,
    )
    now = utc_now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO clients (
                id, name, slug, access_token, phone_number_id,
                whatsapp_business_account_id, api_version, webhook_verify_token,
                simulation_mode, status, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["name"],
                payload["slug"],
                payload["access_token"],
                payload["phone_number_id"],
                payload["whatsapp_business_account_id"],
                payload["api_version"],
                payload["webhook_verify_token"],
                payload["simulation_mode"],
                payload["status"],
                payload["notes"],
                now,
                now,
            ),
        )
    return get_client(client_id, include_secrets=True)


def update_client(client_id: str, **fields: Any) -> dict[str, Any] | None:
    current = get_client(client_id, include_secrets=True)
    if not current:
        return None
    clean_fields = {key: value for key, value in fields.items() if value is not None}
    payload = build_client_payload(
        client_id=client_id,
        name=clean_fields.get("name", current["name"]),
        access_token=clean_fields.get("access_token", current.get("access_token", "")),
        phone_number_id=clean_fields.get("phone_number_id", current.get("phone_number_id", "")),
        whatsapp_business_account_id=clean_fields.get(
            "whatsapp_business_account_id",
            current.get("whatsapp_business_account_id", ""),
        ),
        api_version=clean_fields.get("api_version", current.get("api_version", "v19.0")),
        webhook_verify_token=clean_fields.get("webhook_verify_token", current.get("webhook_verify_token", "")),
        simulation_mode=clean_fields.get("simulation_mode", bool(current.get("simulation_mode"))),
        status=clean_fields.get("status", current.get("status", "active")),
        notes=clean_fields.get("notes", current.get("notes", "")),
    )
    with get_db() as conn:
        conn.execute(
            """
            UPDATE clients
            SET name = ?, slug = ?, access_token = ?, phone_number_id = ?,
                whatsapp_business_account_id = ?, api_version = ?, webhook_verify_token = ?,
                simulation_mode = ?, status = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload["name"],
                payload["slug"],
                payload["access_token"],
                payload["phone_number_id"],
                payload["whatsapp_business_account_id"],
                payload["api_version"],
                payload["webhook_verify_token"],
                payload["simulation_mode"],
                payload["status"],
                payload["notes"],
                utc_now_iso(),
                client_id,
            ),
        )
    return get_client(client_id, include_secrets=True)
