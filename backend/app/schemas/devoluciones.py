from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer, field_validator


class ItemDevolucionIn(BaseModel):
    """Un item que se devuelve: referencia al detalle original de la venta
    (item_linea_id) y cuantas unidades de ese item se devuelven."""

    item_linea_id: int
    cantidad_devuelta: int = Field(ge=1)


class DevolucionCreate(BaseModel):
    """Payload para que el staff registre una devolucion desde el panel."""

    motivo: str = Field(pattern="^(defecto|talla_incorrecta|insatisfaccion|otro)$")
    tipo: str = Field(pattern="^(total|parcial)$")
    metodo_reembolso: str = Field(pattern="^(mismo_medio|credito_tienda|efectivo)$")
    observaciones: str | None = Field(default=None, max_length=1000)
    items: list[ItemDevolucionIn] = Field(min_length=1)

    @field_validator("items")
    @classmethod
    def _sin_items_repetidos(cls, value: list[ItemDevolucionIn]) -> list[ItemDevolucionIn]:
        # Si un mismo item_linea_id viniera dos veces, cada linea pasaria
        # sola la validacion "no devolver mas de lo comprado", pero juntas
        # reembolsarian (y reingresarian al stock) el doble.
        ids = [i.item_linea_id for i in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Cada producto de la compra puede aparecer una sola vez en la devolucion.")
        return value


class DetalleDevolucionOut(BaseModel):
    id: int
    item_linea_id: int
    producto_nombre: str
    talla_codigo: str
    color_nombre: str
    cantidad_devuelta: int
    precio_unitario: Decimal


class DevolucionOut(BaseModel):
    id: int
    venta_id: int
    empleado_nombre: str | None = None
    motivo: str
    tipo: str
    monto_reembolso: Decimal
    metodo_reembolso: str
    estado: str
    fecha_solicitud: datetime
    fecha_resolucion: datetime | None
    observaciones: str | None
    detalles: list[DetalleDevolucionOut]

    @field_serializer("fecha_solicitud", "fecha_resolucion")
    def _serialize_fecha(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class DevolucionAdminOut(DevolucionOut):
    """Vista extendida para el panel de admin: incluye datos del cliente."""

    cliente_nombre: str
    cliente_email: str
    venta_total: Decimal
    venta_fecha: datetime
    sucursal_nombre: str

    @field_serializer("venta_fecha")
    def _serialize_venta_fecha(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
