from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer, field_validator


class OrdenPaypalOut(BaseModel):
    order_id: str
    total: Decimal
    # Link "approve" que devuelve PayPal (checkoutnow?token=...) -- lo usa
    # solo el WebView del checkout movil para el boton "PayPal" (login con
    # cuenta): en vez de abrir el popup del boton del JS SDK (que el WebView
    # de Flutter no soporta), navega dentro del mismo WebView a esta URL real
    # de PayPal, y PayPal redirige de vuelta a /paypal-embed/retorno al
    # terminar. La web no lo usa (sigue con el boton del JS SDK normal).
    approve_url: str | None = None


class VerificarStockItemOut(BaseModel):
    detalle_id: int
    producto_id: int
    producto_nombre: str
    talla_codigo: str
    color_nombre: str
    sucursal_id: int
    sucursal_nombre: str
    cantidad_pedida: int
    cantidad_disponible: int
    disponible: bool


class DetalleVentaOut(BaseModel):
    id: int
    producto_id: int
    producto_nombre: str
    talla_id: int
    talla_codigo: str
    color_id: int
    color_nombre: str
    cantidad: int
    precio_unitario: Decimal


class VentaOut(BaseModel):
    id: int
    tipo: str
    sucursal_id: int
    sucursal_nombre: str
    fecha: datetime
    total: Decimal
    estado: str
    metodo_pago: str
    estado_pago: str
    atendido_por_nombre: str | None
    calificacion_estrellas: int | None
    calificacion_comentario: str | None
    detalles: list[DetalleVentaOut]
    # CU11: info de devolucion (si tiene)
    tiene_devolucion: bool = False
    estado_devolucion: str | None = None
    monto_devolucion: Decimal | None = None
    puede_devolver: bool = False
    horas_restantes_devolucion: float | None = None

    @field_serializer("fecha")
    def _serialize_fecha(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class VentaAdminOut(VentaOut):
    cliente_nombre: str
    cliente_email: str
    comprobante_url: str | None


class VentaPage(BaseModel):
    items: list[VentaAdminOut]
    total: int
    page: int
    page_size: int


class ClienteBusquedaOut(BaseModel):
    id: int
    nombre: str
    email: str


class ItemVentaPresencialCreate(BaseModel):
    producto_id: int
    talla_id: int
    color_id: int
    cantidad: int = Field(ge=1)


def rechazar_items_repetidos(items: list) -> list:
    """Cada combinacion producto/talla/color debe venir una sola vez: si se
    repite, cada linea se valida contra el stock por separado y en conjunto
    se descuenta mas de lo que hay (stock negativo)."""
    vistos: set[tuple[int, int, int]] = set()
    for item in items:
        clave = (item.producto_id, item.talla_id, item.color_id)
        if clave in vistos:
            raise ValueError(
                "Hay productos repetidos con la misma talla y color: junta las cantidades en una sola linea."
            )
        vistos.add(clave)
    return items


class VentaPresencialCreate(BaseModel):
    cliente_id: int
    sucursal_id: int
    items: list[ItemVentaPresencialCreate] = Field(min_length=1)

    @field_validator("items")
    @classmethod
    def _sin_items_repetidos(cls, value: list[ItemVentaPresencialCreate]) -> list[ItemVentaPresencialCreate]:
        return rechazar_items_repetidos(value)


class VentaEditIn(BaseModel):
    sucursal_id: int
    items: list[ItemVentaPresencialCreate] = Field(min_length=1)
    metodo_pago: str
    estado_pago: str = Field(pattern="^(pendiente|verificando|completado|rechazado)$")

    @field_validator("items")
    @classmethod
    def _sin_items_repetidos(cls, value: list[ItemVentaPresencialCreate]) -> list[ItemVentaPresencialCreate]:
        return rechazar_items_repetidos(value)
