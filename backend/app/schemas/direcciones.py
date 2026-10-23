from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class DireccionIn(BaseModel):
    alias: str = Field(min_length=2, max_length=40)
    direccion: str = Field(min_length=5, max_length=250)
    referencia: str | None = Field(default=None, max_length=250)
    ciudad: str | None = Field(default=None, max_length=80)
    latitud: Decimal = Field(ge=-90, le=90)
    longitud: Decimal = Field(ge=-180, le=180)
    predeterminada: bool = False


class DireccionOut(DireccionIn):
    id: int
    actualizado_en: datetime


class UbicacionClienteOut(BaseModel):
    """Ubicacion de la ultima compra con envio de un cliente (CU03)."""

    venta_id: int
    fecha: datetime
    tienda_nombre: str
    direccion: str
    referencia: str | None
    ciudad: str | None
    latitud: Decimal
    longitud: Decimal
