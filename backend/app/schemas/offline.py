"""Contrato de la operacion sin conexion (lo comparten la PWA y Flutter)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.schemas.ventas import rechazar_items_repetidos


def _iso_utc(value: datetime | None) -> str | None:
    """Las fechas se guardan en UTC sin zona: se mandan con 'Z'."""
    if value is None:
        return None
    return value.isoformat() + ("Z" if value.tzinfo is None else "")


# ------------------------------------------------------------------ CU11


class VarianteOfflineOut(BaseModel):
    talla_id: int
    talla_codigo: str
    color_id: int
    color_nombre: str
    stock: int
    sucursal_id: int | None = None


class ProductoOfflineOut(BaseModel):
    producto_id: int
    nombre: str
    precio: Decimal
    imagen_url: str | None
    categoria: str | None
    variantes: list[VarianteOfflineOut]


class ClienteOfflineOut(BaseModel):
    id: int
    nombre: str
    email: str


class SucursalOfflineOut(BaseModel):
    id: int
    nombre: str


class PaqueteOfflineOut(BaseModel):
    """Lo que el personal descarga para trabajar sin conexion en su sucursal."""

    empresa_id: int
    empresa_nombre: str
    sucursal: SucursalOfflineOut
    descargado_en: datetime
    productos: list[ProductoOfflineOut]
    clientes: list[ClienteOfflineOut]

    @field_serializer("descargado_en")
    def _fecha(self, value: datetime) -> str | None:
        return _iso_utc(value)


class TiendaOfflineOut(BaseModel):
    empresa_id: int
    nombre: str
    logo_url: str | None
    sucursales: list[SucursalOfflineOut]
    productos: list[ProductoOfflineOut]
    # La tienda habilito "contra entrega" (compras sin conexion).
    acepta_contra_entrega: bool = False
    # Recibe pagos con PayPal: se puede comprar con el PayPal guardado.
    acepta_paypal: bool = False


class PaypalClienteOfflineOut(BaseModel):
    id: int
    cuenta: str | None
    # Autorizada con la cuenta de Arlani: se cobra sin conexion en cualquier tienda.
    autorizada: bool
    # Autorizada al pagar en estas tiendas (empresa_id): solo en ellas.
    tiendas: list[int] = []


class DireccionOfflineOut(BaseModel):
    id: int
    alias: str
    direccion: str


class CatalogoClienteOfflineOut(BaseModel):
    """Catalogo de las tiendas que trabajan sin conexion, para el cliente."""

    descargado_en: datetime
    tiendas: list[TiendaOfflineOut]
    # Sus direcciones, para elegir envio a domicilio sin conexion.
    direcciones: list[DireccionOfflineOut] = []
    # Sus cuentas PayPal (Metodos de pago), para pagar sin conexion.
    paypals: list[PaypalClienteOfflineOut] = []

    @field_serializer("descargado_en")
    def _fecha(self, value: datetime) -> str | None:
        return _iso_utc(value)


# ------------------------------------------------------------------ CU12


class ItemOfflineIn(BaseModel):
    producto_id: int
    talla_id: int
    color_id: int
    cantidad: int = Field(ge=1, le=99)
    # Precio que se cobro en el dispositivo (se respeta en la venta).
    precio: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)


class OperacionOfflineIn(BaseModel):
    uuid: UUID
    # venta (personal, de contado), reserva o pedido (compra del cliente que
    # se paga al volver la conexion o contra entrega).
    tipo: str = Field(pattern="^(venta|reserva|pedido)$")
    sucursal_id: int
    registrada_en: datetime
    cliente_id: int | None = None
    factura_nombre: str | None = Field(default=None, max_length=150)
    factura_nit: str | None = Field(default=None, max_length=20, pattern=r"^[0-9A-Za-z\-]*$")
    horario_atencion: datetime | None = None
    entrega: str = Field(default="retiro", pattern="^(retiro|envio)$")
    direccion_id: int | None = None
    # paypal_guardado: se cobra solo al sincronizar con el PayPal que el
    # cliente vinculo antes (ver paypal_guardado.py).
    forma_pago: str | None = Field(default=None, pattern="^(en_linea|contra_entrega|paypal_guardado)$")
    # Con "paypal_guardado": cual de sus cuentas PayPal autorizadas (Metodos de
    # pago). Sin ella se usa la ultima autorizada.
    metodo_pago_id: int | None = None
    items: list[ItemOfflineIn] = Field(min_length=1, max_length=30)

    @field_validator("items")
    @classmethod
    def _sin_items_repetidos(cls, value: list[ItemOfflineIn]) -> list[ItemOfflineIn]:
        return rechazar_items_repetidos(value)


class SincronizarIn(BaseModel):
    operaciones: list[OperacionOfflineIn] = Field(min_length=1, max_length=50)


class ResultadoOperacionOut(BaseModel):
    uuid: UUID
    # confirmada | conflicto | rechazada | resuelta | anulada | error (no se
    # guardo: el dispositivo la reintenta).
    estado: str
    mensaje: str | None
    venta_id: int | None = None
    reserva_id: int | None = None
    # Compras con PayPal guardado: lo que NO se cobro y por que (producto,
    # talla, color, motivo), y lo que si se cobro.
    no_pagados: list[dict] | None = None
    total_cobrado: Decimal | None = None


class EstadoOperacionesIn(BaseModel):
    uuids: list[UUID] = Field(min_length=1, max_length=200)


# ------------------------------------------------------------- CU13/CU14


class ItemConflictoOut(BaseModel):
    producto_id: int
    producto: str
    talla_id: int
    talla: str
    color_id: int
    color: str
    pedido: int
    disponible: int


class OperacionOfflineOut(BaseModel):
    id: int
    uuid: UUID
    tipo: str
    estado: str
    mensaje: str | None
    sucursal_id: int | None
    sucursal_nombre: str | None
    usuario_nombre: str | None
    usuario_tipo: str | None
    cliente_nombre: str | None
    registrada_en: datetime
    recibida_en: datetime
    intentos: int
    total: Decimal
    items: list[dict]
    conflicto: list[ItemConflictoOut] | None
    venta_id: int | None
    reserva_id: int | None
    resuelta_por_nombre: str | None
    resuelta_en: datetime | None
    resolucion: str | None

    @field_serializer("registrada_en", "recibida_en", "resuelta_en")
    def _fechas(self, value: datetime | None) -> str | None:
        return _iso_utc(value)


class VarianteDisponibleOut(BaseModel):
    producto_id: int
    talla_id: int
    talla: str
    color_id: int
    color: str
    stock: int


class OpcionesConflictoOut(BaseModel):
    operacion: OperacionOfflineOut
    # Variantes con stock hoy en la sucursal, de los productos del pedido.
    disponibles: list[VarianteDisponibleOut]


class ResolverConflictoIn(BaseModel):
    accion: str = Field(pattern="^(ajustar|anular)$")
    items: list[ItemOfflineIn] | None = None
    motivo: str | None = Field(default=None, max_length=500)


# ===================================================== seguimiento (CU11/12)


class ResumenSeguimientoOut(BaseModel):
    descargas_30d: int
    usuarios_con_datos: int
    ultima_descarga: datetime | None
    operaciones: int
    confirmadas: int
    conflictos: int
    resueltas: int
    anuladas: int
    rechazadas: int
    reenvios: int
    ultima_sincronizacion: datetime | None

    @field_serializer("ultima_descarga", "ultima_sincronizacion")
    def _fechas(self, value: datetime | None) -> str | None:
        return _iso_utc(value)


class DescargaOfflineOut(BaseModel):
    fecha: datetime
    tipo: str
    productos: int
    clientes: int
    usuario_nombre: str | None
    usuario_tipo: str | None
    sucursal_nombre: str | None

    @field_serializer("fecha")
    def _fecha(self, value: datetime) -> str | None:
        return _iso_utc(value)


class UsuarioOfflineOut(BaseModel):
    usuario_nombre: str
    usuario_tipo: str
    sucursal_nombre: str | None
    operaciones: int
    confirmadas: int
    conflictos: int
    resueltas: int
    no_registradas: int
    reenvios: int
    ultima_sincronizacion: datetime | None
    ultima_descarga: datetime | None
    descargas: int

    @field_serializer("ultima_sincronizacion", "ultima_descarga")
    def _fechas(self, value: datetime | None) -> str | None:
        return _iso_utc(value)


class SeguimientoOfflineOut(BaseModel):
    plan: str | None
    plan_offline: bool
    resumen: ResumenSeguimientoOut
    descargas: list[DescargaOfflineOut]
    usuarios: list[UsuarioOfflineOut]


# ================================================= compras sin conexion


class ItemPedidoOut(BaseModel):
    producto_id: int
    talla_id: int
    color_id: int
    producto: str
    talla: str
    color: str
    cantidad: int
    precio_guardado: Decimal
    precio_actual: Decimal
    stock: int


class PedidoOfflineOut(BaseModel):
    """Compra hecha sin conexion, revisada AHORA: precio y stock actuales."""

    id: int
    uuid: UUID
    estado: str
    mensaje: str | None
    empresa_id: int
    tienda: str
    logo_url: str | None
    color_marca: str | None
    sucursal_id: int
    sucursal: str
    registrada_en: datetime
    entrega: str
    direccion: str | None
    forma_pago: str
    items: list[ItemPedidoOut]
    total_guardado: Decimal
    total_actual: Decimal
    total_usd: Decimal
    precio_cambio: bool
    sin_stock: bool
    puede_pagar: bool
    metodos: list[dict]
    venta_id: int | None = None

    @field_serializer("registrada_en")
    def _fecha(self, value: datetime) -> str | None:
        return _iso_utc(value)
