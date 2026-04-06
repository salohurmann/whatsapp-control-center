from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
import re


# ──────────────────────────────────────────────
# Base
# ──────────────────────────────────────────────
class PhoneBase(BaseModel):
    to: str = Field(..., description="Número do destinatário com DDI (ex: 5541999999999)")

    @field_validator("to")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = re.sub(r"\D", "", v)
        if len(cleaned) < 10 or len(cleaned) > 15:
            raise ValueError("Número inválido. Use formato internacional: 5541999999999")
        return cleaned


# ──────────────────────────────────────────────
# Mensagem de Texto
# ──────────────────────────────────────────────
class TextMessageRequest(PhoneBase):
    message: str = Field(..., min_length=1, max_length=4096, description="Texto da mensagem")
    preview_url: bool = Field(False, description="Exibir preview de URLs no texto")


# ──────────────────────────────────────────────
# Mensagem de Mídia
# ──────────────────────────────────────────────
class MediaMessageRequest(PhoneBase):
    media_type: str = Field(
        ...,
        description="Tipo: image | video | audio | document | sticker",
    )
    media_id: Optional[str]   = Field(None, description="ID de mídia já enviada à Meta")
    media_url: Optional[str]  = Field(None, description="URL pública da mídia (alternativa ao media_id)")
    caption: Optional[str]    = Field(None, max_length=1024, description="Legenda (apenas image/video/document)")
    filename: Optional[str]   = Field(None, description="Nome do arquivo (apenas document)")

    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, v: str) -> str:
        allowed = {"image", "video", "audio", "document", "sticker"}
        if v not in allowed:
            raise ValueError(f"media_type deve ser um de: {allowed}")
        return v

    def model_post_init(self, __context):
        if not self.media_id and not self.media_url:
            raise ValueError("Informe media_id OU media_url")


# ──────────────────────────────────────────────
# Template
# ──────────────────────────────────────────────
class TemplateComponent(BaseModel):
    type: str = Field(..., description="header | body | button")
    sub_type: Optional[str] = Field(None, description="Subtipo para botões: quick_reply | url")
    index: Optional[int]    = Field(None, description="Índice do botão (começa em 0)")
    parameters: List[dict]  = Field(default_factory=list)


class TemplateMessageRequest(PhoneBase):
    template_name: str        = Field(..., description="Nome do template aprovado")
    language_code: str        = Field("pt_BR", description="Código do idioma (ex: pt_BR, en_US)")
    components: Optional[List[TemplateComponent]] = Field(
        None,
        description="Componentes com variáveis do template",
    )
