import sqlite3
from contextlib import contextmanager
from pathlib import Path

from config import settings


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.BULK_DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> Path:
    from services import client_manager

    db_path = settings.BULK_DB_FILE
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                access_token TEXT DEFAULT '',
                phone_number_id TEXT DEFAULT '',
                whatsapp_business_account_id TEXT DEFAULT '',
                api_version TEXT NOT NULL DEFAULT 'v19.0',
                webhook_verify_token TEXT DEFAULT '',
                simulation_mode INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_slug
            ON clients(slug);

            CREATE INDEX IF NOT EXISTS idx_clients_phone_number
            ON clients(phone_number_id);

            CREATE TABLE IF NOT EXISTS bulk_jobs (
                id TEXT PRIMARY KEY,
                client_id TEXT NOT NULL DEFAULT 'default',
                send_mode TEXT NOT NULL DEFAULT 'text',
                message TEXT NOT NULL,
                template_name TEXT DEFAULT '',
                language_code TEXT DEFAULT 'pt_BR',
                template_components_json TEXT DEFAULT '[]',
                delay_seconds REAL NOT NULL,
                status TEXT NOT NULL,
                total INTEGER NOT NULL DEFAULT 0,
                sent INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                temporary_failures INTEGER NOT NULL DEFAULT 0,
                deduplicated INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                updated_at TEXT NOT NULL,
                last_error TEXT
            );

            CREATE TABLE IF NOT EXISTS bulk_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL DEFAULT 'default',
                job_id TEXT NOT NULL,
                phone TEXT NOT NULL,
                name TEXT DEFAULT '',
                personalized_message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                retryable INTEGER NOT NULL DEFAULT 1,
                message_id TEXT DEFAULT '',
                error TEXT DEFAULT '',
                last_attempt_at TEXT,
                sent_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES bulk_jobs(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_bulk_contacts_job_status
            ON bulk_contacts(job_id, status);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_bulk_contacts_unique_phone_per_job
            ON bulk_contacts(job_id, phone);

            CREATE TABLE IF NOT EXISTS suppression_list (
                phone TEXT PRIMARY KEY,
                reason TEXT DEFAULT '',
                source TEXT DEFAULT 'manual',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS webhook_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                message_id TEXT DEFAULT '',
                wa_id TEXT DEFAULT '',
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT DEFAULT '',
                operator TEXT DEFAULT '',
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        _ensure_column(conn, "bulk_jobs", "client_id", "TEXT NOT NULL DEFAULT 'default'")
        _ensure_column(conn, "bulk_jobs", "send_mode", "TEXT NOT NULL DEFAULT 'text'")
        _ensure_column(conn, "bulk_jobs", "template_name", "TEXT DEFAULT ''")
        _ensure_column(conn, "bulk_jobs", "language_code", "TEXT DEFAULT 'pt_BR'")
        _ensure_column(conn, "bulk_jobs", "template_components_json", "TEXT DEFAULT '[]'")
        _ensure_column(conn, "bulk_contacts", "client_id", "TEXT NOT NULL DEFAULT 'default'")
        _ensure_column(conn, "bulk_contacts", "delivery_status", "TEXT DEFAULT ''")
        _ensure_column(conn, "bulk_contacts", "delivery_error", "TEXT DEFAULT ''")
        _ensure_column(conn, "bulk_contacts", "delivery_updated_at", "TEXT")
        _ensure_column(conn, "suppression_list", "client_id", "TEXT NOT NULL DEFAULT 'default'")
        _ensure_column(conn, "webhook_events", "client_id", "TEXT NOT NULL DEFAULT 'default'")
        _ensure_column(conn, "webhook_events", "metadata_phone_number_id", "TEXT DEFAULT ''")
        _ensure_column(conn, "audit_events", "client_id", "TEXT NOT NULL DEFAULT 'default'")

        conn.execute("UPDATE bulk_jobs SET client_id = 'default' WHERE client_id IS NULL OR client_id = ''")
        conn.execute("UPDATE bulk_contacts SET client_id = 'default' WHERE client_id IS NULL OR client_id = ''")
        conn.execute("UPDATE suppression_list SET client_id = 'default' WHERE client_id IS NULL OR client_id = ''")
        conn.execute("UPDATE webhook_events SET client_id = 'default' WHERE client_id IS NULL OR client_id = ''")
        conn.execute("UPDATE audit_events SET client_id = 'default' WHERE client_id IS NULL OR client_id = ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bulk_contacts_client_status ON bulk_contacts(client_id, status)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_suppression_client_phone ON suppression_list(client_id, phone)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_webhook_events_message_id ON webhook_events(message_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_webhook_events_client_id ON webhook_events(client_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_entity ON audit_events(client_id, entity_type, entity_id, created_at)")

    client_manager.ensure_default_client()
    return db_path


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
