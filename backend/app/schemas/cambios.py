from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.metodos_pago import MetodoPagoPublicoOut
from app.schemas.ventas import TiendaFacturaOut

MotivoCambio = Literal["talla", "color", "modelo", "defecto", "otro"]
DestinoPrenda = Literal["reingreso", "merma", "proveedor"]


class LineaCambiableOut(BaseModel):
    item_linea_id: int
    producto_id: int
    producto_nombre: str
    imagen_url: str | None
    talla_codigo: str
    color_nombre: str
    cantidad: int
    # Unidades que aun se pueden cambiar (descontando cambios abiertos o hechos).
    disponibles: int
    precio_pagado: Decimal


class StockSucursalOut(BaseModel):
    sucursal_id: int
    sucursal_nombre: str
    stock: int


class VarianteOut(BaseModel):
    talla_id: int
    talla_codigo: str
    color_id: int
    color_nombre: str
    # Total en la tienda y cuanto hay en cada sucursal (donde se recoge).
    stock: int
    sucursales: list[StockSucursalOut]


class PrendaCambioOut(BaseModel):
    producto_id: int
    nombre: str
    precio: Decimal
    imagen_url: str | None
    variantes: list[VarianteOut]


class OpcionesCambioOut(BaseModel):
    """Lo que el cliente puede cambiar de una compra y por que prendas."""

    venta_id: int
    fecha: datetime
    plazo_hasta: datetime
    en_plazo: bool
    puede_cambiar: bool
    motivo_no: str | None
    tienda_nombre: str
    sucursal_id: int
    sucursal_nombre: str
    lineas: list[LineaCambiableOut]
    prendas: list[PrendaCambioOut]


class SolicitudCambioIn(BaseModel):
    venta_id: int
    item_linea_id: int
    cantidad: int = Field(ge=1, le=50)
    producto_id: int
    talla_id: int
    color_id: int
    # Sucursal donde recoge la prenda nueva (y entrega la que devuelve).
    sucursal_id: int
    motivo: MotivoCambio
    observaciones: str | None = Field(default=None, max_length=500)


class AprobarCambioIn(BaseModel):
    # Que se hace con la prenda devuelta.
    destino: DestinoPrenda = "reingreso"
    observacion: str | None = Field(default=None, max_length=500)


class MotivoIn(BaseModel):
    motivo: str = Field(min_length=3, max_length=500)


class CambioOut(BaseModel):
    id: int
    venta_id: int
    # Linea de la compra que se cambia (para tacharla en Mis Compras).
    item_linea_id: int
    venta_fecha: datetime
    estado: str
    motivo: str
    observaciones: str | None
    cantidad: int
    sucursal_id: int
    sucursal_nombre: str
    cliente_nombre: str
    cliente_email: str
    producto_original: str
    talla_original: str
    color_original: str
    producto_nuevo: str
    talla_nueva: str
    color_nuevo: str
    precio_pagado: Decimal
    precio_nuevo: Decimal
    # > 0: el cliente paga; < 0: se le devuelve.
    diferencia: Decimal
    destino: str | None
    motivo_rechazo: str | None
    reembolso_metodo: str | None
    metodo_pago_nombre: str | None
    comprobante_url: str | None
    empleado_nombre: str | None
    fecha_solicitud: datetime
    fecha_resolucion: datetime | None
    fecha_completado: datetime | None
    tienda: TiendaFacturaOut
    # Para pagar la diferencia (solo mientras esta por pagar).
    metodos: list[MetodoPagoPublicoOut] = []
    diferencia_usd: Decimal | None = None
