from fastapi import APIRouter, Depends, Request
from models.requests import TextMessageRequest
from models.responses import MessageSentResponse
from services import client_manager, whatsapp
from dependencies import get_client_id, require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/text", response_model=MessageSentResponse, summary="Enviar mensagem de texto")
async def send_text_message(body: TextMessageRequest, request: Request, client_id: str = Depends(get_client_id)):
    """
    Envia uma mensagem de texto simples para um número WhatsApp.

    - **to**: número com DDI, sem símbolos (ex: `5541999999999`)
    - **message**: texto da mensagem (até 4096 caracteres)
    - **preview_url**: exibe preview de links dentro do texto
    """
    client = request.app.state.http_client
    client_config = client_manager.resolve_client(client_id)
    result = await whatsapp.send_text(
        client=client,
        client_config=client_config,
        to=body.to,
        message=body.message,
        preview_url=body.preview_url,
    )
    contacts = result.get("contacts", [{}])
    messages = result.get("messages", [{}])
    return MessageSentResponse(
        success=True,
        whatsapp_id=contacts[0].get("wa_id"),
        message_id=messages[0].get("id"),
        status=messages[0].get("message_status", "accepted"),
    )
