from typing import Any

from config import settings
from services import bulk_manager, ops, suppression, webhooks


async def run_local_self_test(app, client_id: str = "default") -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    suppression_phone = "5511999990009"
    suppression.add_phone(suppression_phone, client_id=client_id, reason="Diagnostico local", source="self_test")
    checks.append({"step": "suppression_add", "ok": suppression.is_suppressed(suppression_phone, client_id=client_id)})
    suppression.remove_phone(suppression_phone, client_id=client_id)
    checks.append({"step": "suppression_remove", "ok": not suppression.is_suppressed(suppression_phone, client_id=client_id)})

    contacts = [
        {"phone": "5511999990001", "name": "Contato Teste 1", "cidade": "Sao Paulo"},
        {"phone": "5511999990002", "name": "Contato Teste 2", "cidade": "Campinas"},
    ]
    job = bulk_manager.create_job(
        client_id=client_id,
        message="Diagnostico local para {name} em {cidade}",
        delay_seconds=0.5,
        contacts=contacts,
    )
    await bulk_manager.process_job(job["id"], app.state.http_client, simulate=True)
    status = bulk_manager.get_job_status(job["id"], client_id=client_id) or {}
    checks.append(
        {
            "step": "bulk_processing",
            "ok": status.get("status") == "finished" and status.get("sent", 0) == 2,
            "job_id": job["id"],
        }
    )

    processed_contacts = bulk_manager.list_contacts(client_id=client_id, job_id=job["id"], limit=10)
    first_item = next((item for item in processed_contacts if item.get("message_id")), None)
    if first_item:
        webhooks.process_payload(
            {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {"phone_number_id": ""},
                                    "statuses": [
                                        {
                                            "id": first_item["message_id"],
                                            "status": "read",
                                            "recipient_id": first_item["phone"],
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                ]
            }
        )

    delivery = bulk_manager.get_delivery_summary(client_id, job["id"])
    checks.append(
        {
            "step": "delivery_tracking",
            "ok": delivery.get("delivered", 0) >= 2 and delivery.get("read_count", 0) >= 1,
            "delivery": delivery,
        }
    )

    backup_path = ops.create_backup(settings.BULK_DB_FILE)
    checks.append({"step": "backup_create", "ok": backup_path.exists(), "backup": backup_path.name})

    return {
        "success": all(item.get("ok") for item in checks),
        "simulation_mode": True,
        "job_id": job["id"],
        "checks": checks,
    }
