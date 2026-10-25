from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer


class CarritoItemCreate(BaseModel):
    producto_id: int
    talla_id: int
    color_id: int
    sucursal_id: int
    cantidad: int = Field(ge=1)


class CarritoItemUpdate(BaseModel):
    cantidad: int = Field(ge=1)


class DetalleCarritoOut(BaseModel):
    id: int
    producto_id: int
    producto_nombre: str
    producto_imagen_url: str | None
    talla_id: int
    talla_codigo: str
    color_id: int
    color_nombre: str
    sucursal_id: int
    sucursal_nombre: str
    cantidad: int
    precio_unitario: Decimal
    subtotal: Decimal
    # Boutique que vende la prenda: el carrito las agrupa por tienda, cada una
    # con su logo y su color (los que la tienda tiene guardados en la base).
    tienda: str | None = None
    tienda_nombre: str | None = None
    tienda_logo: str | None = None
    tienda_color: str | None = None


class CarritoOut(BaseModel):
    id: int
    estado: str
    detalles: list[DetalleCarritoOut]
    total: Decimal


class CarritoAdminOut(CarritoOut):
    cliente_id: int
    cliente_nombre: str
    cliente_email: str
    fecha_creacion: datetime
    fecha_actualizacion: datetime
    cantidad_items: int

    @field_serializer("fecha_creacion", "fecha_actualizacion")
    def _serialize_fecha(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
