import json
from datetime import datetime
from typing import Any

from services.storage import get_db


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def record_event(
    *,
    client_id: str = "default",
    event_type: str,
    entity_type: str,
    entity_id: str = "",
    operator: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO audit_events (client_id, event_type, entity_type, entity_id, operator, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                event_type,
                entity_type,
                entity_id,
                operator.strip(),
                json.dumps(details or {}, ensure_ascii=False),
                utc_now_iso(),
            ),
        )


def list_events(
    client_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    query = """
        SELECT id, client_id, event_type, entity_type, entity_id, operator, details, created_at
        FROM audit_events
    """
    clauses = []
    params: list[Any] = []
    if client_id:
        clauses.append("client_id = ?")
        params.append(client_id)
    if entity_type:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    if entity_id:
        clauses.append("entity_id = ?")
        params.append(entity_id)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]
