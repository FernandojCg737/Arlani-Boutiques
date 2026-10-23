from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ResumenCajaOut(BaseModel):
    ventas: int
    total_ventas: Decimal
    efectivo: Decimal
    qr: Decimal
    paypal: Decimal
    otros: Decimal
    ingresos: Decimal
    retiros: Decimal
    devoluciones_efectivo: Decimal
    efectivo_esperado: Decimal | None


class CajaOut(BaseModel):
    id: int
    tipo: str
    estado: str
    sucursal_id: int | None
    sucursal_nombre: str | None
    fecha: date
    abierta_en: datetime
    abierta_por_nombre: str | None
    abierta_por_rol: str | None
    cerrada_en: datetime | None
    cerrada_por_nombre: str | None
    monto_inicial: Decimal
    efectivo_esperado: Decimal | None
    efectivo_contado: Decimal | None
    diferencia: Decimal | None
    observacion: str | None
    resumen: ResumenCajaOut


class MovimientoCajaOut(BaseModel):
    id: int
    tipo: str
    monto: Decimal
    motivo: str
    usuario_nombre: str | None
    fecha: datetime


class VentaCajaOut(BaseModel):
    id: int
    fecha: datetime
    tipo: str
    origen: str
    estado: str
    cliente: str
    metodo_pago: str | None
    estado_pago: str | None
    atendido_por: str | None
    total: Decimal
    fuera_de_arqueo: bool


class CajaDetalleOut(CajaOut):
    movimientos: list[MovimientoCajaOut]
    ventas_detalle: list[VentaCajaOut]


class SucursalCajaOut(BaseModel):
    id: int
    nombre: str
    horario_atencion: str | None
    caja: CajaOut | None


class PanelCajaOut(BaseModel):
    sucursales: list[SucursalCajaOut]
    online: CajaOut | None
    puede_operar: bool


class AbrirCajaIn(BaseModel):
    sucursal_id: int
    monto_inicial: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class MovimientoCajaIn(BaseModel):
    tipo: str = Field(pattern="^(ingreso|retiro)$")
    monto: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    motivo: str = Field(min_length=3, max_length=200)


class CerrarCajaIn(BaseModel):
    efectivo_contado: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    observacion: str | None = Field(default=None, max_length=500)


class EstadoTiendaOut(BaseModel):
    """Para el checkout: si la sucursal esta atendiendo ahora."""

    abierta: bool
    horario_atencion: str | None
