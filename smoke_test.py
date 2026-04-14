import io
import hmac
import hashlib
import json
import logging
import os
import shutil
from pathlib import Path


def main() -> int:
    root = Path(".smoke_test_runtime").resolve()
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    env_path = root / ".env"
    db_path = root / "test.db"
    logs_dir = root / "logs"
    backups_dir = root / "backups"
    logs_dir.mkdir(parents=True, exist_ok=True)
    backups_dir.mkdir(parents=True, exist_ok=True)

    os.environ["APP_ENV"] = "test"
    os.environ["HOST"] = "127.0.0.1"
    os.environ["PORT"] = "8001"
    os.environ["PUBLIC_BASE_URL"] = "http://testserver"
    os.environ["META_APP_SECRET"] = "test-app-secret"
    os.environ["ACCESS_TOKEN"] = ""
    os.environ["PHONE_NUMBER_ID"] = ""
    os.environ["WHATSAPP_BUSINESS_ACCOUNT_ID"] = ""
    os.environ["API_VERSION"] = "v19.0"
    os.environ["API_KEY"] = "test-api-key"
    os.environ["SIMULATION_MODE"] = "true"
    os.environ["ALLOWED_ORIGINS"] = "http://testserver"
    os.environ["BULK_DB_PATH"] = str(db_path)
    os.environ["WEBHOOK_VERIFY_TOKEN"] = "verify-token"
    os.environ["LOG_FILE_PATH"] = str(logs_dir / "app.log")
    os.environ["BACKUP_DIR"] = str(backups_dir)
    os.environ["REMOTE_ADMIN_ENABLED"] = "true"

    import config

    config.ENV_PATH = env_path
    config.settings.reload()

    from fastapi.testclient import TestClient
    from main import app
    from models.requests import TemplateComponent
    from services.whatsapp import _normalize_template_components

    with TestClient(app) as client:
        headers = {"X-API-Key": "test-api-key"}

        resp = client.get("/")
        assert resp.status_code in {200, 307}

        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["simulation_mode"] is True

        resp = client.get("/system/config")
        assert resp.status_code == 401

        resp = client.get("/system/config", headers=headers)
        assert resp.status_code == 200
        assert "public_base_url" in resp.json()
        assert "callback_url" in resp.json()

        resp = client.get("/clients", headers=headers)
        assert resp.status_code == 200 and len(resp.json()) >= 1

        resp = client.get("/clients/current/diagnostics", headers=headers)
        assert resp.status_code == 200
        assert "warnings" in resp.json()
        assert resp.json()["ready_for_live"] is False

        resp = client.post("/clients/current/connection-test", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is False

        resp = client.post(
            "/clients",
            headers=headers,
            json={"name": "Cliente Secundario", "simulation_mode": True, "notes": "teste"},
        )
        assert resp.status_code == 200, resp.text

        resp = client.post(
            "/system/config",
            headers=headers,
            json={
                "access_token": "",
                "phone_number_id": "",
                "whatsapp_business_account_id": "",
                "api_version": "v19.0",
                "api_key": "test-api-key",
                "webhook_verify_token": "verify-token",
                "public_base_url": "http://testserver",
                "meta_app_secret": "test-app-secret",
                "simulation_mode": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        resp = client.post(
            "/messages/text",
            headers=headers,
            json={"to": "5511999999999", "message": "teste"},
        )
        assert resp.status_code == 200, resp.text

        resp = client.post(
            "/media/send",
            headers=headers,
            json={
                "to": "5511999999999",
                "media_type": "image",
                "media_url": "https://example.com/img.jpg",
                "caption": "teste",
            },
        )
        assert resp.status_code == 200, resp.text

        resp = client.post(
            "/media/upload",
            headers=headers,
            files={"file": ("teste.txt", b"abc", "text/plain")},
        )
        assert resp.status_code == 200, resp.text

        resp = client.post(
            "/templates/send",
            headers=headers,
            json={
                "to": "5511999999999",
                "template_name": "boas_vindas",
                "language_code": "pt_BR",
                "components": [{"type": "body", "parameters": [{"type": "text", "text": "Joao"}]}],
            },
        )
        assert resp.status_code == 200, resp.text
        assert _normalize_template_components(
            [
                TemplateComponent(type="body", parameters=[{"type": "text", "text": "Joao"}]),
                {"type": "button", "sub_type": "quick_reply", "index": 0, "parameters": []},
            ]
        ) == [
            {"type": "body", "parameters": [{"type": "text", "text": "Joao"}]},
            {"type": "button", "sub_type": "quick_reply", "index": 0, "parameters": []},
        ]

        csv_content = "telefone;nome\n5511999990001;Alice\n5511999990002;Bruno\n"

        resp = client.post(
            "/bulk/send-template",
            headers=headers,
            files={"file": ("contatos.csv", csv_content.encode("utf-8"), "text/csv")},
            data={
                "template_name": "boas_vindas",
                "language_code": "pt_BR",
                "components_json": '[{"type":"body","parameters":[{"type":"text","text":"Ola {nome}"}]}]',
                "delay_seconds": "0.5",
                "pilot_size": "0",
            },
        )
        assert resp.status_code == 200, resp.text

        resp = client.post(
            "/bulk/send",
            headers=headers,
            files={"file": ("contatos.csv", csv_content.encode("utf-8"), "text/csv")},
            data={"message": "Oi {nome}", "delay_seconds": "0.5", "pilot_size": "0"},
        )
        assert resp.status_code == 200, resp.text
        job_id = resp.json()["job_id"]

        resp = client.post(
            "/bulk/send-direct",
            headers=headers,
            data={
                "phones_text": "5511999990003\n5511999990004,5511999990003",
                "message": "Ola direto",
                "delay_seconds": "0.5",
                "pilot_size": "0",
            },
        )
        assert resp.status_code == 200, resp.text

        resp = client.get(f"/bulk/status/{job_id}", headers=headers)
        assert resp.status_code == 200, resp.text

        resp = client.get("/bulk/jobs", headers=headers)
        assert resp.status_code == 200 and len(resp.json()) >= 1

        resp = client.get(f"/bulk/report/{job_id}", headers=headers)
        assert resp.status_code == 200

        resp = client.get("/bulk/contacts", headers=headers)
        assert resp.status_code == 200

        resp = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-token",
                "hub.challenge": "12345",
            },
        )
        assert resp.status_code == 200 and resp.text == "12345"

        sent_message_id = client.post(
            "/messages/text",
            headers=headers,
            json={"to": "5511999999999", "message": "webhook test"},
        ).json()["message_id"]
        webhook_payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": sent_message_id,
                                        "status": "read",
                                        "recipient_id": "5511999999999",
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        webhook_body = json.dumps(webhook_payload).encode("utf-8")
        signature = "sha256=" + hmac.new(b"test-app-secret", webhook_body, hashlib.sha256).hexdigest()
        resp = client.post("/webhook", content=webhook_body, headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature})
        assert resp.status_code == 200, resp.text

        resp = client.get("/webhooks/events", headers=headers)
        assert resp.status_code == 200

        resp = client.post("/admin/self-test", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True

        resp = client.post("/admin/backups", headers=headers)
        assert resp.status_code == 200, resp.text

        resp = client.get("/admin/backups", headers=headers)
        assert resp.status_code == 200 and len(resp.json()) >= 1

        resp = client.post(
            "/system/config",
            headers=headers,
            json={
                "name": "Operacao Principal",
                "access_token": "",
                "phone_number_id": "",
                "whatsapp_business_account_id": "",
                "api_version": "v19.0",
                "api_key": "test-api-key",
                "webhook_verify_token": "verify-token",
                "simulation_mode": False,
                "notes": "",
            },
        )
        assert resp.status_code == 200, resp.text
        resp = client.post(
            "/messages/text",
            headers=headers,
            json={"to": "5511999999999", "message": "teste"},
        )
        assert resp.status_code == 400

    print("SMOKE TEST OK")
    logger = logging.getLogger("wa_ops")
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
