from fastapi import APIRouter, Depends, Request, UploadFile, File
from models.requests import MediaMessageRequest
from models.responses import MessageSentResponse, MediaUploadResponse
from services import client_manager, whatsapp
from dependencies import get_client_id, require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/send", response_model=MessageSentResponse, summary="Enviar mídia (imagem/vídeo/áudio/documento)")
async def send_media_message(body: MediaMessageRequest, request: Request, client_id: str = Depends(get_client_id)):
    """
    Envia uma mensagem de mídia. Informe **media_id** (pré-enviado via /media/upload)
    ou **media_url** (URL pública acessível pela Meta).

    Tipos suportados: `image`, `video`, `audio`, `document`, `sticker`
    """
    client = request.app.state.http_client
    client_config = client_manager.resolve_client(client_id)
    result = await whatsapp.send_media(
        client=client,
        client_config=client_config,
        to=body.to,
        media_type=body.media_type,
        media_id=body.media_id,
        media_url=body.media_url,
        caption=body.caption,
        filename=body.filename,
    )
    contacts = result.get("contacts", [{}])
    messages = result.get("messages", [{}])
    return MessageSentResponse(
        success=True,
        whatsapp_id=contacts[0].get("wa_id"),
        message_id=messages[0].get("id"),
        status=messages[0].get("message_status", "accepted"),
    )


@router.post("/upload", response_model=MediaUploadResponse, summary="Fazer upload de mídia para a Meta")
async def upload_media(
    request: Request,
    file: UploadFile = File(..., description="Arquivo a ser enviado"),
    client_id: str = Depends(get_client_id),
    _: str = Depends(require_api_key),
):
    """
    Faz upload de um arquivo para a infraestrutura da Meta e retorna o **media_id**
    que pode ser reutilizado em múltiplos envios sem re-upload.

    Tamanho máximo por tipo:
    - Imagem: 5 MB
    - Vídeo: 16 MB
    - Áudio: 16 MB
    - Documento: 100 MB
    """
    client = request.app.state.http_client
    client_config = client_manager.resolve_client(client_id)
    file_bytes = await file.read()
    result = await whatsapp.upload_media(
        client=client,
        client_config=client_config,
        file_bytes=file_bytes,
        mime_type=file.content_type or "application/octet-stream",
        filename=file.filename or "upload",
    )
    return MediaUploadResponse(
        success=True,
        media_id=result.get("id"),
    )
