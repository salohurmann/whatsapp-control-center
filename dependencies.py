import secrets

from fastapi import Header, HTTPException, Query, Request, Security, status
from fastapi.security import APIKeyHeader

from config import settings
from services import client_manager


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(key: str = Security(api_key_header)) -> str:
    if not key or not settings.API_KEY or not secrets.compare_digest(key, settings.API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key invalida ou ausente. Envie o header X-API-Key.",
        )
    return key


async def require_local_request(request: Request) -> None:
    if settings.REMOTE_ADMIN_ALLOWED:
        return

    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "localhost", "::1", "testclient"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta operacao so e permitida localmente. Ative REMOTE_ADMIN_ENABLED=true para hospedar com painel remoto.",
        )


async def get_operator_name(x_operator: str | None = Header(default="")) -> str:
    return (x_operator or "").strip()


async def get_client_id(
    x_client_id: str | None = Header(default=None),
    client_id: str | None = Query(default=None),
) -> str:
    requested = (x_client_id or client_id or "").strip()
    try:
        client = client_manager.resolve_client(requested or None, include_secrets=False)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return client["id"]
