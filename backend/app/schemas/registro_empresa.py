from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

COLOR_HEX = r"^#[0-9a-fA-F]{6}$"


class BoutiqueRegistroIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    subdominio: str = Field(min_length=3, max_length=40)
    ciudad: str | None = Field(default=None, max_length=80)
    # Sucursales que piensa abrir: no puede pasar el maximo del plan elegido.
    sucursales: int = Field(ge=1, le=500)
    color: str = Field(pattern=COLOR_HEX)
    # Para quien vende: mujer, hombre, unisex, nina, nino, bebe.
    publicos: list[str] = Field(default_factory=list, max_length=6)


class AdministradorRegistroIn(BaseModel):
    # Usuario con el que la boutique entra a su panel (distinto de la cuenta
    # de cliente). Sus credenciales llegan al correo del cliente que compra.
    nombre: str = Field(min_length=2, max_length=150)
    email: EmailStr


class SolicitudSuscripcionIn(BaseModel):
    plan: str
    periodo: Literal["mensual", "anual"] = "mensual"
    boutique: BoutiqueRegistroIn
    administrador: AdministradorRegistroIn


class ConfirmarSuscripcionIn(SolicitudSuscripcionIn):
    # Orden de PayPal ya aprobada por el cliente (no hace falta en la prueba).
    order_id: str | None = Field(default=None, max_length=64)
    # Logo como data URL (data:image/...;base64,...): cualquier formato de imagen.
    logo: str | None = Field(default=None, max_length=7_500_000)


class CotizacionOut(BaseModel):
    plan_codigo: str
    plan_nombre: str
    periodo: str
    max_sucursales: int
    monto_bob: Decimal
    tipo_cambio: Decimal
    monto_usd: Decimal
    requiere_pago: bool
    # Enlace con el que quedaria la tienda (con numero si el pedido ya existe).
    subdominio: str


class OrdenSuscripcionOut(BaseModel):
    order_id: str
    monto_usd: Decimal
    monto_bob: Decimal
    # La app movil abre este enlace de PayPal y vuelve a /paypal-embed/retorno.
    approve_url: str | None = None


class SuscripcionCreadaOut(BaseModel):
    empresa_id: int
    empresa_nombre: str
    subdominio: str
    plan_nombre: str
    admin_email: str
    # Adonde se enviaron las credenciales: el correo del cliente que compro.
    correo_destino: str
    metodo: Literal["paypal", "prueba"]
    monto_bob: Decimal
    monto_usd: Decimal
    logo_guardado: bool
    correo_enviado: bool
