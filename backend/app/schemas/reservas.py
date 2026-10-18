from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.schemas.ventas import rechazar_items_repetidos


class ItemReservaCreate(BaseModel):
    producto_id: int
    talla_id: int
    color_id: int
    cantidad: int = Field(ge=1)


class ReservaCreate(BaseModel):
    sucursal_id: int
    horario_atencion: datetime
    items: list[ItemReservaCreate] = Field(min_length=1)

    @field_validator("items")
    @classmethod
    def _sin_items_repetidos(cls, value: list[ItemReservaCreate]) -> list[ItemReservaCreate]:
        return rechazar_items_repetidos(value)


class DetalleReservaOut(BaseModel):
    id: int
    producto_id: int
    producto_nombre: str
    talla_codigo: str
    color_nombre: str
    cantidad: int

    model_config = {"from_attributes": True}


class ReservaOut(BaseModel):
    id: int
    cliente_id: int
    sucursal_id: int
    sucursal_nombre: str
    horario_atencion: datetime
    estado: str
    fecha_creacion: datetime
    detalles: list[DetalleReservaOut]

    model_config = {"from_attributes": True}

    @field_serializer("horario_atencion", "fecha_creacion")
    def _serialize_fecha(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class ReservaAdminOut(ReservaOut):
    cliente_nombre: str
    cliente_email: str


class ReservaPage(BaseModel):
    items: list[ReservaAdminOut]
    total: int
    page: int
    page_size: int


class ReservaEstadoUpdate(BaseModel):
    estado: str = Field(pattern="^(confirmada|cancelada)$")


class DisponibilidadItem(BaseModel):
    sucursal_id: int
    sucursal_nombre: str
    talla_id: int
    talla_codigo: str
    color_id: int
    color_nombre: str
    cantidad: int
