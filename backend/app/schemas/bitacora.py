from datetime import datetime, timezone

from pydantic import BaseModel, field_serializer


class BitacoraItem(BaseModel):
    id: int
    usuario_id: int
    usuario_nombre: str
    usuario_email: str
    accion: str
    entidad_afectada: str
    entidad_id: int | None
    fecha: datetime
    detalle: str | None
    ip_address: str | None
    plataforma: str | None
    empresa_id: int | None = None
    empresa_nombre: str | None = None

    model_config = {"from_attributes": True}

    @field_serializer("fecha")
    def _serialize_fecha(self, value: datetime) -> str:
        # La BD guarda "fecha" naive en UTC (datetime.utcnow()). Le marcamos
        # el offset UTC explicito para que el frontend no la confunda con
        # hora local del navegador al convertirla a hora de Bolivia (UTC-4).
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class BitacoraPage(BaseModel):
    items: list[BitacoraItem]
    total: int
    page: int
    page_size: int
