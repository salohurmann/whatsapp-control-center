import os
from functools import lru_cache
from pathlib import Path


ENV_PATH = Path(".env")
MANAGED_ENV_KEYS = [
    "APP_ENV",
    "HOST",
    "PORT",
    "PUBLIC_BASE_URL",
    "META_APP_SECRET",
    "ACCESS_TOKEN",
    "PHONE_NUMBER_ID",
    "WHATSAPP_BUSINESS_ACCOUNT_ID",
    "API_VERSION",
    "API_KEY",
    "SIMULATION_MODE",
    "BULK_DB_PATH",
    "ALLOWED_ORIGINS",
    "WEBHOOK_VERIFY_TOKEN",
    "LOG_FILE_PATH",
    "BACKUP_DIR",
    "REMOTE_ADMIN_ENABLED",
]


def _load_dotenv(dotenv_path: str = ".env") -> None:
    path = Path(dotenv_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


class Settings:
    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        _load_dotenv()
        self.APP_ENV = os.getenv("APP_ENV", "development")
        self.HOST = os.getenv("HOST", "0.0.0.0")
        self.PORT = os.getenv("PORT", "8000")
        self.PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")
        self.META_APP_SECRET = os.getenv("META_APP_SECRET", "")
        self.ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "")
        self.PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
        self.WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
        self.API_VERSION = os.getenv("API_VERSION", "v19.0")
        self.API_KEY = os.getenv("API_KEY", "")
        self.SIMULATION_MODE = os.getenv("SIMULATION_MODE", "false")
        self.BULK_DB_PATH = os.getenv("BULK_DB_PATH", "whatsapp_bulk.db")
        self.ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
        self.WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "")
        self.LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "logs/app.log")
        self.BACKUP_DIR = os.getenv("BACKUP_DIR", "backups")
        self.REMOTE_ADMIN_ENABLED = os.getenv("REMOTE_ADMIN_ENABLED", "true")

    def as_dict(self) -> dict[str, str]:
        return {key: str(getattr(self, key, "")) for key in MANAGED_ENV_KEYS}

    def save(self, values: dict[str, str]) -> None:
        current_lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
        preserved: dict[str, str] = {}
        for raw_line in current_lines:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            preserved[key.strip()] = value.strip()

        for key in MANAGED_ENV_KEYS:
            if key in values:
                preserved[key] = str(values[key]).strip()

        content = "\n".join(f"{key}={preserved.get(key, '')}" for key in MANAGED_ENV_KEYS)
        other_keys = [key for key in preserved.keys() if key not in MANAGED_ENV_KEYS]
        if other_keys:
            content += "\n" + "\n".join(f"{key}={preserved[key]}" for key in other_keys)
        content += "\n"
        ENV_PATH.write_text(content, encoding="utf-8")

        for key, value in preserved.items():
            os.environ[key] = value
        self.reload()

    @property
    def META_BASE_URL(self) -> str:
        return f"https://graph.facebook.com/{self.API_VERSION}"

    @property
    def MESSAGES_URL(self) -> str:
        return f"{self.META_BASE_URL}/{self.PHONE_NUMBER_ID}/messages"

    @property
    def MEDIA_URL(self) -> str:
        return f"{self.META_BASE_URL}/{self.PHONE_NUMBER_ID}/media"

    @property
    def BULK_DB_FILE(self) -> Path:
        return Path(self.BULK_DB_PATH).expanduser().resolve()

    @property
    def SIMULATION_MODE_ENABLED(self) -> bool:
        return str(self.SIMULATION_MODE).strip().lower() in {"1", "true", "yes", "on", "sim"}

    @property
    def META_CONFIGURED(self) -> bool:
        values = [self.ACCESS_TOKEN, self.PHONE_NUMBER_ID]
        if not all(value and value.strip() for value in values):
            return False
        placeholders = ("COLE_SEU_", "SEU_", "YOUR_", "CHANGE_ME")
        return not any(any(value.strip().upper().startswith(prefix) for prefix in placeholders) for value in values)

    @property
    def CORS_ORIGINS(self) -> list[str]:
        origins = [item.strip() for item in self.ALLOWED_ORIGINS.split(",") if item.strip()]
        if self.PUBLIC_BASE_URL.strip():
            origins.append(self.PUBLIC_BASE_URL.strip().rstrip("/"))
        deduplicated = list(dict.fromkeys(origins))
        return deduplicated or ["http://localhost:8000", "http://127.0.0.1:8000"]

    @property
    def LOG_FILE(self) -> Path:
        return Path(self.LOG_FILE_PATH).expanduser().resolve()

    @property
    def BACKUP_DIR_PATH(self) -> Path:
        return Path(self.BACKUP_DIR).expanduser().resolve()

    @property
    def PORT_INT(self) -> int:
        try:
            return int(str(self.PORT).strip())
        except (TypeError, ValueError):
            return 8000

    @property
    def REMOTE_ADMIN_ALLOWED(self) -> bool:
        return str(self.REMOTE_ADMIN_ENABLED).strip().lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
