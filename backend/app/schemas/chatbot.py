from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_serializer


class MensajeIn(BaseModel):
    mensaje: str = Field(min_length=1, max_length=1000)
    # Subdominio de la tienda donde esta el cliente (sin el: la original).
    tienda: str | None = Field(default=None, max_length=60)
    # El chat del catalogo universal: responde con todas las tiendas.
    universal: bool = False


class MensajePrevioIn(BaseModel):
    remitente: Literal["cliente", "bot"]
    mensaje: str = Field(max_length=2000)


class MensajePublicoIn(BaseModel):
    """Chat universal sin sesion: el navegador guarda la conversacion y manda
    los ultimos mensajes para que Gemini tenga el hilo."""

    mensaje: str = Field(min_length=1, max_length=1000)
    historial: list[MensajePrevioIn] = Field(default_factory=list, max_length=20)


class RespuestaPublicaOut(BaseModel):
    mensaje: str
    intencion: str
    confianza: float


class MensajeOut(BaseModel):
    id: int
    remitente: str
    mensaje: str
    fecha: datetime
    # CU18: lo que el modelo entendio del mensaje del cliente.
    intencion: str | None = None
    confianza: float | None = None

    @field_serializer("fecha")
    def _serialize_fecha(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class ChatbotUsuarioOut(BaseModel):
    cliente_id: int
    cliente_nombre: str
    cliente_email: str
    total_mensajes: int
    ultima_actividad: datetime

    @field_serializer("ultima_actividad")
    def _serialize_fecha(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
