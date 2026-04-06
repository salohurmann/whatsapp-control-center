from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from config import settings
from dependencies import get_client_id, require_api_key, require_local_request
from services import audit, bulk_manager, self_test
from services import ops


router = APIRouter(dependencies=[Depends(require_local_request), Depends(require_api_key)])


@router.get("/audit", summary="Listar auditoria")
async def list_audit(
    client_id: str = Depends(get_client_id),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    return audit.list_events(client_id=client_id, entity_type=entity_type, entity_id=entity_id, limit=limit)


@router.get("/backups", summary="Listar backups")
async def list_backups():
    return ops.list_backups()


@router.post("/backups", summary="Criar backup")
async def create_backup(client_id: str = Depends(get_client_id)):
    backup_path = ops.create_backup(settings.BULK_DB_FILE)
    audit.record_event(
        client_id=client_id,
        event_type="backup_created",
        entity_type="backup",
        entity_id=backup_path.name,
        details={"path": str(backup_path)},
    )
    return {"success": True, "backup": backup_path.name}


@router.get("/backups/download/{name}", summary="Baixar backup")
async def download_backup(name: str):
    path = settings.BACKUP_DIR_PATH / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Backup nao encontrado.")
    return FileResponse(path, filename=path.name, media_type="application/zip")


@router.post("/backups/restore", summary="Restaurar backup")
async def restore_backup(file: UploadFile = File(...), client_id: str = Depends(get_client_id)):
    active_jobs = [
        job
        for job in bulk_manager.list_jobs(client_id=client_id)
        if job["status"] in {"queued", "running", "pause_requested", "cancel_requested"}
    ]
    if active_jobs:
        raise HTTPException(status_code=409, detail="Pause ou finalize campanhas ativas antes de restaurar um backup.")

    temp_path = settings.BACKUP_DIR_PATH / f"restore_{file.filename or 'backup.zip'}"
    settings.BACKUP_DIR_PATH.mkdir(parents=True, exist_ok=True)
    temp_path.write_bytes(await file.read())
    try:
        ops.restore_backup(temp_path, settings.BULK_DB_FILE)
        settings.reload()
    finally:
        if temp_path.exists():
            temp_path.unlink()

    audit.record_event(client_id=client_id, event_type="backup_restored", entity_type="backup", entity_id=file.filename or "")
    return {"success": True, "message": "Backup restaurado com sucesso."}


@router.post("/auth/login", summary="Validar acesso local")
async def login():
    return {"success": True}


@router.post("/self-test", summary="Executar diagnostico local sem Meta")
async def run_self_test(request: Request, client_id: str = Depends(get_client_id)):
    result = await self_test.run_local_self_test(request.app, client_id=client_id)
    audit.record_event(
        client_id=client_id,
        event_type="self_test_executed",
        entity_type="system",
        entity_id="local",
        details={"success": result["success"], "job_id": result["job_id"]},
    )
    return result
