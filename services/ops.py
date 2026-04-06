import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from config import ENV_PATH, settings


logger = logging.getLogger("wa_ops")


def utc_now_stamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def setup_logging() -> Path:
    log_file = settings.LOG_FILE
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if not logger.handlers:
        handler = logging.FileHandler(log_file, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
    return log_file


def create_backup(db_path: Path) -> Path:
    settings.BACKUP_DIR_PATH.mkdir(parents=True, exist_ok=True)
    backup_path = settings.BACKUP_DIR_PATH / f"backup_{utc_now_stamp()}.zip"
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if db_path.exists():
            zf.write(db_path, arcname=db_path.name)
        if ENV_PATH.exists():
            zf.write(ENV_PATH, arcname=".env")
        if settings.LOG_FILE.exists():
            zf.write(settings.LOG_FILE, arcname=settings.LOG_FILE.name)
    logger.info("Backup criado em %s", backup_path)
    return backup_path


def list_backups(limit: int = 50) -> list[dict[str, str | int]]:
    settings.BACKUP_DIR_PATH.mkdir(parents=True, exist_ok=True)
    backups = []
    for path in sorted(settings.BACKUP_DIR_PATH.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        backups.append(
            {
                "name": path.name,
                "path": str(path),
                "size": path.stat().st_size,
                "updated_at": datetime.utcfromtimestamp(path.stat().st_mtime).replace(microsecond=0).isoformat() + "Z",
            }
        )
    return backups


def restore_backup(backup_file: Path, db_path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_dir = Path(tmpdir)
        with zipfile.ZipFile(backup_file, "r") as zf:
            zf.extractall(temp_dir)

        restored_env = temp_dir / ".env"
        restored_db = temp_dir / db_path.name

        if restored_env.exists():
            shutil.copy2(restored_env, ENV_PATH)
        if restored_db.exists():
            if db_path.exists():
                os.remove(db_path)
            shutil.copy2(restored_db, db_path)

    logger.info("Backup restaurado de %s", backup_file)
