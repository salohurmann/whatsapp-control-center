import asyncio
import csv
import io
import json
import re
import uuid
from datetime import datetime
from typing import Any

import httpx
from fastapi import HTTPException

from services import suppression, whatsapp
from services.client_manager import get_client
from services.storage import get_db


TERMINAL_CONTACT_STATUSES = {"sent", "failed_permanent", "canceled"}
ACTIVE_JOB_STATUSES = {"queued", "running", "pause_requested", "cancel_requested"}
PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _row_to_dict(row) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def render_message(template: str, contact: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = contact.get(key, "")
        if value in ("", None):
            if key == "nome":
                value = contact.get("nome") or contact.get("name", "")
            elif key == "name":
                value = contact.get("name") or contact.get("nome", "")
        return str(value) if value is not None else ""

    return PLACEHOLDER_PATTERN.sub(replace, template)


def render_template_components(components: list[dict[str, Any]], contact: dict[str, Any]) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    for component in components:
        parameters = []
        for param in component.get("parameters", []):
            item = dict(param)
            if item.get("type") == "text":
                item["text"] = render_message(str(item.get("text", "")), contact)
            parameters.append(item)
        rendered.append(
            {
                "type": component.get("type"),
                **({"sub_type": component.get("sub_type")} if component.get("sub_type") else {}),
                **({"index": component.get("index")} if component.get("index") is not None else {}),
                "parameters": parameters,
            }
        )
    return rendered


def create_job(
    client_id: str,
    message: str,
    delay_seconds: float,
    contacts: list[dict[str, str]],
    *,
    send_mode: str = "text",
    template_name: str = "",
    language_code: str = "pt_BR",
    template_components: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    job_id = str(uuid.uuid4())[:8]
    created_at = utc_now_iso()
    deduplicated_contacts: list[dict[str, str]] = []
    seen: set[str] = set()
    removed = 0
    suppressed_removed = 0

    for contact in contacts:
        phone = contact["phone"]
        if phone in seen:
            removed += 1
            continue
        if suppression.is_suppressed(phone, client_id=client_id):
            suppressed_removed += 1
            continue
        seen.add(phone)
        personalized = render_message(message, contact)
        deduplicated_contacts.append(
            {
                "phone": phone,
                "name": contact.get("name", "").strip(),
                "personalized_message": personalized,
            }
        )

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO bulk_jobs (
                id, client_id, send_mode, message, template_name, language_code, template_components_json,
                delay_seconds, status, total, deduplicated,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)
            """,
            (
                job_id,
                client_id,
                send_mode,
                message,
                template_name,
                language_code,
                json.dumps(template_components or [], ensure_ascii=False),
                delay_seconds,
                len(deduplicated_contacts),
                removed + suppressed_removed,
                created_at,
                created_at,
            ),
        )
        conn.executemany(
            """
            INSERT INTO bulk_contacts (
                client_id, job_id, phone, name, personalized_message,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    client_id,
                    job_id,
                    contact["phone"],
                    contact["name"],
                    contact["personalized_message"],
                    created_at,
                    created_at,
                )
                for contact in deduplicated_contacts
            ],
        )

    return get_job(job_id, client_id=client_id)


def get_job(job_id: str, client_id: str | None = None) -> dict[str, Any] | None:
    with get_db() as conn:
        if client_id:
            row = conn.execute(
                """
                SELECT
                    id, client_id, send_mode, message, template_name, language_code, template_components_json,
                    status, delay_seconds, total, sent, failed,
                    temporary_failures, deduplicated, created_at, started_at,
                    finished_at, updated_at, last_error
                FROM bulk_jobs
                WHERE id = ? AND client_id = ?
                """,
                (job_id, client_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT
                    id, client_id, send_mode, message, template_name, language_code, template_components_json,
                    status, delay_seconds, total, sent, failed,
                    temporary_failures, deduplicated, created_at, started_at,
                    finished_at, updated_at, last_error
                FROM bulk_jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
    return _row_to_dict(row) or None


def list_jobs(client_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    query = """
        SELECT
            id, client_id, send_mode, template_name, language_code, status, total, sent, failed, temporary_failures, deduplicated,
            created_at, started_at, finished_at, updated_at, last_error
        FROM bulk_jobs
    """
    params: list[Any] = []
    if client_id:
        query += " WHERE client_id = ?"
        params.append(client_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_contacts(
    client_id: str | None = None,
    job_id: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    query = """
        SELECT
            client_id, job_id, phone, name, status, attempts, retryable,
            personalized_message, message_id, error, updated_at,
            delivery_status, delivery_error, delivery_updated_at
        FROM bulk_contacts
    """
    clauses = []
    params: list[Any] = []
    if client_id:
        clauses.append("client_id = ?")
        params.append(client_id)
    if job_id:
        clauses.append("job_id = ?")
        params.append(job_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if q:
        clauses.append("(phone LIKE ? OR name LIKE ? OR message_id LIKE ?)")
        wildcard = f"%{q}%"
        params.extend([wildcard, wildcard, wildcard])
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_job_contacts(client_id: str, job_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                phone, name, status, attempts, retryable, message_id, error, updated_at,
                delivery_status, delivery_error, delivery_updated_at
            FROM bulk_contacts
            WHERE client_id = ? AND job_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (client_id, job_id, limit),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_job_status(job_id: str, client_id: str | None = None) -> dict[str, Any] | None:
    job = get_job(job_id, client_id=client_id)
    if not job:
        return None
    processed = job["sent"] + job["failed"]
    pct = round(processed / job["total"] * 100, 1) if job["total"] else 0.0
    job["processed"] = processed
    job["progress_percent"] = pct
    job["progress_text"] = f"{processed}/{job['total']} ({pct}%)"
    job["recent_contacts"] = get_job_contacts(job["client_id"], job_id)
    job["delivery"] = get_delivery_summary(job["client_id"], job_id)
    return job


def get_dashboard_stats(client_id: str | None = None) -> dict[str, Any]:
    params: list[Any] = []
    where_jobs = ""
    where_contacts = ""
    if client_id:
        where_jobs = " WHERE client_id = ?"
        where_contacts = " WHERE client_id = ?"
        params.append(client_id)
    with get_db() as conn:
        totals = conn.execute(
            f"""
            SELECT
                COUNT(*) AS jobs,
                COALESCE(SUM(sent), 0) AS sent,
                COALESCE(SUM(failed), 0) AS failed,
                COALESCE(SUM(temporary_failures), 0) AS temporary_failures,
                COALESCE(SUM(deduplicated), 0) AS deduplicated
            FROM bulk_jobs
            {where_jobs}
            """,
            params,
        ).fetchone()
        active = conn.execute(
            f"""
            SELECT COUNT(*) AS active
            FROM bulk_jobs
            {where_jobs} {"AND" if where_jobs else "WHERE"} status IN ('queued', 'running', 'pause_requested', 'cancel_requested')
            """,
            params,
        ).fetchone()
        delivery = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN delivery_status = 'sent' THEN 1 ELSE 0 END), 0) AS sent_to_meta,
                COALESCE(SUM(CASE WHEN delivery_status IN ('delivered', 'read') THEN 1 ELSE 0 END), 0) AS delivered,
                COALESCE(SUM(CASE WHEN delivery_status = 'read' THEN 1 ELSE 0 END), 0) AS read_count,
                COALESCE(SUM(CASE WHEN delivery_status IN ('failed', 'undelivered') THEN 1 ELSE 0 END), 0) AS delivery_failed
            FROM bulk_contacts
            {where_contacts}
            """,
            params,
        ).fetchone()
    return {
        "jobs": totals["jobs"],
        "sent": totals["sent"],
        "failed": totals["failed"],
        "temporary_failures": totals["temporary_failures"],
        "deduplicated": totals["deduplicated"],
        "active_jobs": active["active"],
        "delivery": dict(delivery),
    }


def get_delivery_summary(client_id: str, job_id: str) -> dict[str, int]:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN delivery_status = 'sent' THEN 1 ELSE 0 END), 0) AS sent_to_meta,
                COALESCE(SUM(CASE WHEN delivery_status IN ('delivered', 'read') THEN 1 ELSE 0 END), 0) AS delivered,
                COALESCE(SUM(CASE WHEN delivery_status = 'read' THEN 1 ELSE 0 END), 0) AS read_count,
                COALESCE(SUM(CASE WHEN delivery_status IN ('failed', 'undelivered') THEN 1 ELSE 0 END), 0) AS delivery_failed
            FROM bulk_contacts
            WHERE client_id = ? AND job_id = ?
            """,
            (client_id, job_id),
        ).fetchone()
    return dict(row)


def update_job_status(job_id: str, status: str, *, last_error: str | None = None, finished: bool = False) -> dict[str, Any]:
    updated_at = utc_now_iso()
    finished_at = updated_at if finished else None
    with get_db() as conn:
        conn.execute(
            """
            UPDATE bulk_jobs
            SET status = ?, updated_at = ?, finished_at = COALESCE(?, finished_at), last_error = COALESCE(?, last_error)
            WHERE id = ?
            """,
            (status, updated_at, finished_at, last_error, job_id),
        )
    return get_job(job_id)


def request_pause(job_id: str, client_id: str) -> dict[str, Any] | None:
    job = get_job(job_id, client_id=client_id)
    if not job:
        return None
    next_status = "pause_requested" if job["status"] == "running" else "paused"
    return update_job_status(job_id, next_status)


def request_resume(job_id: str, client_id: str) -> dict[str, Any] | None:
    job = get_job(job_id, client_id=client_id)
    if not job:
        return None
    return update_job_status(job_id, "queued", finished=False, last_error=None)


def request_cancel(job_id: str, client_id: str) -> dict[str, Any] | None:
    job = get_job(job_id, client_id=client_id)
    if not job:
        return None
    next_status = "cancel_requested" if job["status"] in {"running", "pause_requested"} else "canceled"
    if next_status == "canceled":
        _cancel_pending_contacts(job_id, client_id)
    return update_job_status(job_id, next_status, finished=next_status == "canceled")


def _cancel_pending_contacts(job_id: str, client_id: str) -> None:
    now = utc_now_iso()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE bulk_contacts
            SET status = 'canceled', retryable = 0, updated_at = ?
            WHERE client_id = ? AND job_id = ? AND status IN ('pending', 'retry_pending', 'processing')
            """,
            (now, client_id, job_id),
        )
        _recount_job(conn, job_id)


def _recount_job(conn, job_id: str) -> None:
    totals = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END), 0) AS sent,
            COALESCE(SUM(CASE WHEN status IN ('failed_temporary', 'failed_permanent') THEN 1 ELSE 0 END), 0) AS failed,
            COALESCE(SUM(CASE WHEN status = 'failed_temporary' THEN 1 ELSE 0 END), 0) AS temporary_failures
        FROM bulk_contacts
        WHERE job_id = ?
        """,
        (job_id,),
    ).fetchone()
    conn.execute(
        """
        UPDATE bulk_jobs
        SET sent = ?, failed = ?, temporary_failures = ?, updated_at = ?
        WHERE id = ?
        """,
        (totals["sent"], totals["failed"], totals["temporary_failures"], utc_now_iso(), job_id),
    )


def claim_next_job() -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM bulk_jobs
            WHERE status IN ('queued', 'running', 'pause_requested', 'cancel_requested')
            ORDER BY CASE status
                WHEN 'running' THEN 0
                WHEN 'cancel_requested' THEN 1
                WHEN 'pause_requested' THEN 2
                ELSE 3
            END, created_at ASC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        job_id = row["id"]
        current = conn.execute("SELECT status, started_at FROM bulk_jobs WHERE id = ?", (job_id,)).fetchone()
        if current["status"] == "queued":
            now = utc_now_iso()
            conn.execute(
                """
                UPDATE bulk_jobs
                SET status = 'running', started_at = COALESCE(started_at, ?), updated_at = ?
                WHERE id = ?
                """,
                (now, now, job_id),
            )
    return get_job(job_id)


def claim_next_contact(job_id: str, client_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT id, phone, name, personalized_message, attempts
            FROM bulk_contacts
            WHERE client_id = ? AND job_id = ? AND status IN ('pending', 'retry_pending')
            ORDER BY id ASC
            LIMIT 1
            """,
            (client_id, job_id),
        ).fetchone()
        if not row:
            return None
        now = utc_now_iso()
        conn.execute(
            """
            UPDATE bulk_contacts
            SET status = 'processing', attempts = attempts + 1, last_attempt_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, row["id"]),
        )
    claimed = dict(row)
    claimed["attempts"] = row["attempts"] + 1
    return claimed


def mark_contact_sent(job_id: str, contact_id: int, message_id: str) -> None:
    now = utc_now_iso()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE bulk_contacts
            SET status = 'sent', retryable = 0, message_id = ?, error = '',
                sent_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (message_id, now, now, contact_id),
        )
        _recount_job(conn, job_id)


def mark_contact_failed(
    job_id: str,
    contact_id: int,
    *,
    error: str,
    temporary: bool,
    can_retry: bool,
) -> None:
    now = utc_now_iso()
    status = "retry_pending" if temporary and can_retry else ("failed_temporary" if temporary else "failed_permanent")
    with get_db() as conn:
        conn.execute(
            """
            UPDATE bulk_contacts
            SET status = ?, retryable = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, 1 if temporary and can_retry else 0, error[:500], now, contact_id),
        )
        _recount_job(conn, job_id)
        conn.execute(
            "UPDATE bulk_jobs SET last_error = ?, updated_at = ? WHERE id = ?",
            (error[:500], now, job_id),
        )


def finalize_job(job_id: str, status: str) -> None:
    now = utc_now_iso()
    with get_db() as conn:
        _recount_job(conn, job_id)
        conn.execute(
            """
            UPDATE bulk_jobs
            SET status = ?, finished_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, now, now, job_id),
        )


def reset_temporary_failures(job_id: str, client_id: str) -> int:
    now = utc_now_iso()
    with get_db() as conn:
        result = conn.execute(
            """
            UPDATE bulk_contacts
            SET status = 'retry_pending', retryable = 1, error = '', updated_at = ?
            WHERE client_id = ? AND job_id = ? AND status = 'failed_temporary'
            """,
            (now, client_id, job_id),
        )
        conn.execute(
            """
            UPDATE bulk_jobs
            SET status = 'queued', finished_at = NULL, updated_at = ?
            WHERE id = ? AND client_id = ?
            """,
            (now, job_id, client_id),
        )
    return result.rowcount


def get_report_csv(job_id: str, client_id: str) -> io.StringIO | None:
    job = get_job(job_id, client_id=client_id)
    if not job:
        return None
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "client_id", "phone", "name", "status", "attempts", "retryable",
            "personalized_message", "message_id", "error", "updated_at",
            "delivery_status", "delivery_error", "delivery_updated_at",
        ],
    )
    writer.writeheader()
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                client_id, phone, name, status, attempts, retryable,
                personalized_message, message_id, error, updated_at,
                delivery_status, delivery_error, delivery_updated_at
            FROM bulk_contacts
            WHERE client_id = ? AND job_id = ?
            ORDER BY id ASC
            """,
            (client_id, job_id),
        ).fetchall()
    writer.writerows([dict(row) for row in rows])
    output.seek(0)
    return output


def _is_retryable_http(status_code: int) -> bool:
    return status_code in {408, 409, 429, 500, 502, 503, 504}


def classify_error(exc: Exception) -> tuple[bool, str]:
    if isinstance(exc, HTTPException):
        detail = str(exc.detail)
        return _is_retryable_http(exc.status_code), detail
    if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.RequestError)):
        return True, str(exc)
    return False, str(exc)


def update_delivery_status(message_id: str, delivery_status: str, delivery_error: str = "") -> bool:
    if not message_id:
        return False
    now = utc_now_iso()
    with get_db() as conn:
        result = conn.execute(
            """
            UPDATE bulk_contacts
            SET delivery_status = ?, delivery_error = ?, delivery_updated_at = ?, updated_at = ?
            WHERE message_id = ?
            """,
            (delivery_status, delivery_error[:500], now, now, message_id),
        )
    return result.rowcount > 0


async def process_job(job_id: str, client: httpx.AsyncClient, simulate: bool | None = None) -> None:
    while True:
        job = get_job(job_id)
        if not job:
            return
        client_config = get_client(job["client_id"], include_secrets=True)
        if not client_config:
            update_job_status(job_id, "failed", last_error="Cliente nao encontrado.", finished=True)
            return

        if job["status"] == "pause_requested":
            update_job_status(job_id, "paused")
            return
        if job["status"] == "cancel_requested":
            _cancel_pending_contacts(job_id, job["client_id"])
            finalize_job(job_id, "canceled")
            return
        if job["status"] in {"paused", "finished", "canceled", "failed"}:
            return

        contact = claim_next_contact(job_id, job["client_id"])
        if not contact:
            finalize_job(job_id, "finished")
            return

        backoff = min(2 ** max(contact["attempts"] - 1, 0), 30)
        try:
            if job.get("send_mode") == "template":
                components = json.loads(job.get("template_components_json") or "[]")
                result = await whatsapp.send_template(
                    client=client,
                    client_config=client_config,
                    to=contact["phone"],
                    template_name=job.get("template_name") or "",
                    language_code=job.get("language_code") or "pt_BR",
                    components=render_template_components(components, contact),
                    simulate=simulate,
                )
            else:
                result = await whatsapp.send_text(
                    client=client,
                    client_config=client_config,
                    to=contact["phone"],
                    message=contact["personalized_message"],
                    simulate=simulate,
                )
            message_id = result.get("messages", [{}])[0].get("id", "")
            mark_contact_sent(job_id, contact["id"], message_id)
            if whatsapp.should_simulate(client_config, simulate):
                update_delivery_status(message_id, "delivered")
            await asyncio.sleep(job["delay_seconds"])
        except Exception as exc:
            retryable, error_message = classify_error(exc)
            can_retry = retryable and contact["attempts"] < 4
            mark_contact_failed(
                job_id,
                contact["id"],
                error=error_message,
                temporary=retryable,
                can_retry=can_retry,
            )
            if can_retry:
                await asyncio.sleep(backoff)
            else:
                await asyncio.sleep(min(job["delay_seconds"], 1.5))


async def worker_loop(app) -> None:
    client = app.state.http_client
    while True:
        try:
            job = claim_next_job()
            if not job:
                await asyncio.sleep(1.0)
                continue
            await process_job(job["id"], client)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            app.state.last_worker_error = str(exc)
            await asyncio.sleep(2.0)
