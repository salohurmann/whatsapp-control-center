from datetime import datetime

from services.storage import get_db


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def normalize_phone(phone: str) -> str:
    return "".join(ch for ch in str(phone or "") if ch.isdigit())


def is_suppressed(phone: str, client_id: str = "default") -> bool:
    normalized = normalize_phone(phone)
    if not normalized:
        return False
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM suppression_list WHERE client_id = ? AND phone = ?",
            (client_id, normalized),
        ).fetchone()
    return row is not None


def add_phone(phone: str, client_id: str = "default", reason: str = "", source: str = "manual") -> dict:
    normalized = normalize_phone(phone)
    if len(normalized) < 10 or len(normalized) > 15:
        raise ValueError("Telefone invalido para supressao.")

    now = utc_now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO suppression_list (client_id, phone, reason, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(client_id, phone) DO UPDATE SET
                reason = excluded.reason,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (client_id, normalized, reason.strip(), source.strip() or "manual", now, now),
        )
    return {"client_id": client_id, "phone": normalized, "reason": reason.strip(), "source": source.strip() or "manual"}


def remove_phone(phone: str, client_id: str = "default") -> bool:
    normalized = normalize_phone(phone)
    with get_db() as conn:
        result = conn.execute(
            "DELETE FROM suppression_list WHERE client_id = ? AND phone = ?",
            (client_id, normalized),
        )
    return result.rowcount > 0


def list_phones(client_id: str = "default", limit: int = 200) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT client_id, phone, reason, source, created_at, updated_at
            FROM suppression_list
            WHERE client_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (client_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]
