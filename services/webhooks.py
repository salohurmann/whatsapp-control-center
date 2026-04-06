import json
from datetime import datetime
from typing import Any

from services import bulk_manager, suppression
from services.client_manager import find_client_by_phone_number_id
from services.storage import get_db


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def record_event(
    event_type: str,
    payload: dict[str, Any],
    *,
    client_id: str = "default",
    message_id: str = "",
    wa_id: str = "",
    metadata_phone_number_id: str = "",
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO webhook_events (client_id, event_type, message_id, wa_id, metadata_phone_number_id, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                event_type,
                message_id,
                wa_id,
                metadata_phone_number_id,
                json.dumps(payload, ensure_ascii=False),
                utc_now_iso(),
            ),
        )


def process_payload(payload: dict[str, Any]) -> dict[str, int]:
    statuses = 0
    messages = 0
    opt_outs = 0

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            metadata = value.get("metadata", {}) or {}
            metadata_phone_number_id = str(metadata.get("phone_number_id") or "").strip()
            client = find_client_by_phone_number_id(metadata_phone_number_id) if metadata_phone_number_id else None
            client_id = client["id"] if client else "default"
            metadata_wrapper = {"metadata": metadata}

            for status_item in value.get("statuses", []):
                statuses += 1
                error_message = ""
                if status_item.get("errors"):
                    error_message = "; ".join(
                        str(item.get("title") or item.get("message") or item)
                        for item in status_item["errors"]
                    )
                bulk_manager.update_delivery_status(
                    message_id=status_item.get("id", ""),
                    delivery_status=status_item.get("status", "unknown"),
                    delivery_error=error_message,
                )
                record_event(
                    event_type=f"status:{status_item.get('status', 'unknown')}",
                    payload={"status": status_item, **metadata_wrapper},
                    client_id=client_id,
                    message_id=status_item.get("id", ""),
                    wa_id=status_item.get("recipient_id", ""),
                    metadata_phone_number_id=metadata_phone_number_id,
                )

            for message in value.get("messages", []):
                messages += 1
                record_event(
                    event_type=f"message:{message.get('type', 'unknown')}",
                    payload={"message": message, **metadata_wrapper},
                    client_id=client_id,
                    message_id=message.get("id", ""),
                    wa_id=message.get("from", ""),
                    metadata_phone_number_id=metadata_phone_number_id,
                )

                text_body = (((message.get("text") or {}).get("body")) or "").strip().lower()
                if text_body in {"sair", "stop", "parar", "cancelar"}:
                    suppression.add_phone(
                        message.get("from", ""),
                        client_id=client_id,
                        reason="Opt-out recebido via webhook",
                        source="webhook",
                    )
                    opt_outs += 1

    return {"statuses": statuses, "messages": messages, "opt_outs": opt_outs}


def recent_events(client_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    query = """
        SELECT id, client_id, event_type, message_id, wa_id, metadata_phone_number_id, payload, created_at
        FROM webhook_events
    """
    params: list[Any] = []
    if client_id:
        query += " WHERE client_id = ?"
        params.append(client_id)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]
