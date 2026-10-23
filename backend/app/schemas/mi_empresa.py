from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class MarcaEmpresaOut(BaseModel):
    # Identidad de la tienda para su panel, reportes y comprobantes.
    nombre: str
    subdominio: str
    ciudad: str | None
    color_marca: str
    logo_url: str | None
    email_contacto: str | None
    # False si la suscripcion vencio o la tienda esta suspendida: el panel
    # solo deja entrar a "Mi suscripcion".
    operativa: bool = True


class MarcaEmpresaIn(BaseModel):
    # Lo que no se manda queda igual.
    color_marca: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    # Logo nuevo como data URL (cualquier formato de imagen).
    logo: str | None = Field(default=None, max_length=7_500_000)
    quitar_logo: bool = False


class HistorialSuscripcionOut(BaseModel):
    id: int
    plan_nombre: str
    periodo: str
    monto: Decimal
    fecha_inicio: date
    fecha_fin: date | None
    estado: str


class PlanDisponibleOut(BaseModel):
    codigo: str
    nombre: str
    precio_mensual: Decimal
    max_sucursales: int
    dias_prueba: int | None
    ia_generativa: bool
    operacion_offline: bool
    comision_pct: Decimal


class MiSuscripcionOut(BaseModel):
    empresa_id: int
    empresa_nombre: str
    subdominio: str
    color_marca: str
    empresa_estado: str
    # NULL si la empresa no tiene una suscripcion vigente.
    plan_codigo: str | None
    plan_nombre: str | None
    precio_mensual: Decimal | None
    ia_generativa: bool | None
    periodo: str | None
    monto: Decimal | None
    fecha_inicio: date | None
    fecha_fin: date | None
    dias_restantes: int | None
    sucursales_usadas: int
    max_sucursales: int | None
    personal: int
    clientes: int
    # False: la suscripcion vencio (o la tienda esta suspendida) y no opera.
    operativa: bool
    comision_pct: Decimal | None
    historial: list[HistorialSuscripcionOut]
    planes: list[PlanDisponibleOut]


class SucursalPublicaOut(BaseModel):
    nombre: str
    direccion: str
    ciudad: str
    horario_atencion: str | None
    telefono: str | None


class TiendaResumenOut(BaseModel):
    # Una tienda activa en la lista publica (carrusel de la portada).
    id: int
    nombre: str
    subdominio: str
    ciudad: str | None
    color_marca: str
    logo_url: str | None


class TiendaPublicaOut(BaseModel):
    id: int
    nombre: str
    subdominio: str
    ciudad: str | None
    color_marca: str
    logo_url: str | None
    estado: str
    tiene_catalogo: bool
    # La tienda original tiene su sitio completo (/atelier); las demas
    # muestran su catalogo dentro de su pagina /tienda-<subdominio>.
    sitio_propio: bool
    sucursales: list[SucursalPublicaOut]


class RenovacionIn(BaseModel):
    # La tienda compra o renueva su plan (pago a Arlani con PayPal).
    plan: str = Field(min_length=2, max_length=30)
    periodo: str = Field(pattern=r"^(mensual|anual)$")


class ConfirmarRenovacionIn(RenovacionIn):
    order_id: str = Field(min_length=5, max_length=64)


class CotizacionRenovacionOut(BaseModel):
    plan_codigo: str
    plan_nombre: str
    periodo: str
    # Total a cobrar: el plan mas las comisiones pendientes (se pagan juntos).
    monto_bob: Decimal
    tipo_cambio: Decimal
    monto_usd: Decimal
    plan_bob: Decimal
    plan_usd: Decimal
    comisiones_bob: Decimal = Decimal("0")
    comisiones_usd: Decimal = Decimal("0")
    # Desde cuando corre el plan: al terminar el actual si renueva el mismo
    # plan antes de que venza; si no, desde hoy.
    fecha_inicio: date


class MovimientoCuentaOut(BaseModel):
    id: int
    fecha: datetime
    tipo: str
    venta_id: int | None
    base_bob: Decimal | None
    porcentaje: Decimal | None
    monto_bob: Decimal
    descripcion: str


class LiquidacionRecibidaOut(BaseModel):
    # Lo que Arlani le envio a la tienda por una compra con "Pagar todo".
    id: int
    fecha: datetime
    bruto_bob: Decimal
    comision_bob: Decimal
    neto_bob: Decimal
    neto_usd: Decimal
    paypal_email: str
    estado: str


class CuentaTiendaOut(BaseModel):
    """Estado de cuenta de la tienda con Arlani (comisiones por venta)."""

    liquidaciones: list[LiquidacionRecibidaOut] = []
    saldo_bob: Decimal
    saldo_usd: Decimal
    tipo_cambio: Decimal
    comision_pct: Decimal | None
    ventas_mes: int
    ventas_mes_bob: Decimal
    comisiones_mes_bob: Decimal
    pagado_total_bob: Decimal
    movimientos: list[MovimientoCuentaOut]


class OrdenSaldoOut(BaseModel):
    order_id: str
    monto_usd: Decimal
    monto_bob: Decimal


class ConfirmarSaldoIn(BaseModel):
    order_id: str = Field(min_length=5, max_length=64)


class OrdenRenovacionOut(BaseModel):
    order_id: str
    monto_usd: Decimal
    monto_bob: Decimal
