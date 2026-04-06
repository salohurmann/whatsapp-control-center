from pydantic import BaseModel
from typing import Optional, Any


class MessageSentResponse(BaseModel):
    success: bool
    message_id: Optional[str] = None
    whatsapp_id: Optional[str] = None
    status: Optional[str] = None
    detail: Optional[str] = None


class MediaUploadResponse(BaseModel):
    success: bool
    media_id: Optional[str] = None
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    phone_number_id: str
    simulation_mode: bool = False
    meta_configured: bool = False
