from fastapi import APIRouter, Depends, Request
from models.requests import TemplateMessageRequest
from models.responses import MessageSentResponse
from services import client_manager, whatsapp
from dependencies import get_client_id, require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/send", response_model=MessageSentResponse, summary="Enviar mensagem via template aprovado")
async def send_template_message(body: TemplateMessageRequest, request: Request, client_id: str = Depends(get_client_id)):
    """
    Envia uma mensagem usando um **template aprovado** no Meta Business Manager.

    Templates são obrigatórios para iniciar conversas fora da janela de 24h.

    **Exemplo com variáveis:**
    ```json
    {
      "to": "5541999999999",
      "template_name": "boas_vindas",
      "language_code": "pt_BR",
      "components": [
        {
          "type": "body",
          "parameters": [
            { "type": "text", "text": "João Silva" },
            { "type": "text", "text": "pedido #1234" }
          ]
        }
      ]
    }
    ```
    """
    client = request.app.state.http_client
    client_config = client_manager.resolve_client(client_id)
    result = await whatsapp.send_template(
        client=client,
        client_config=client_config,
        to=body.to,
        template_name=body.template_name,
        language_code=body.language_code,
        components=body.components,
    )
    contacts = result.get("contacts", [{}])
    messages = result.get("messages", [{}])
    return MessageSentResponse(
        success=True,
        whatsapp_id=contacts[0].get("wa_id"),
        message_id=messages[0].get("id"),
        status=messages[0].get("message_status", "accepted"),
    )
