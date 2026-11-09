from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


# ---------------------------------------------------------------- dashboard --
class SerieDia(BaseModel):
    fecha: date
    total: Decimal
    cantidad: int


class SerieCategoria(BaseModel):
    etiqueta: str
    total: Decimal
    cantidad: int


class DashboardOut(BaseModel):
    ventas_hoy_total: Decimal
    ventas_hoy_cantidad: int
    ventas_mes_total: Decimal
    ventas_mes_cantidad: int
    ticket_promedio_mes: Decimal
    reservas_activas: int
    clientes_nuevos_mes: int
    ventas_por_dia: list[SerieDia]
    ventas_por_metodo: list[SerieCategoria]
    ventas_por_sucursal: list[SerieCategoria]
    top_productos: list[SerieCategoria]


# ------------------------------------------------------------------ ventas --
class VentaResumen(BaseModel):
    total_vendido: Decimal
    cantidad_ventas: int
    ticket_promedio: Decimal


class VentaDetalleFila(BaseModel):
    id: int
    # Numero de la venta en su tienda (el que se muestra).
    numero: int | None = None
    fecha: datetime
    cliente_nombre: str
    sucursal_nombre: str
    tipo: str
    metodo_pago: str
    estado_pago: str
    total: Decimal


class ReporteVentasOut(BaseModel):
    resumen: VentaResumen
    por_metodo: list[SerieCategoria]
    por_sucursal: list[SerieCategoria]
    top_productos: list[SerieCategoria]
    detalle: list[VentaDetalleFila]


# --------------------------------------------------------------- asistencia --
class AsistenciaFila(BaseModel):
    empleado_id: int
    empleado_nombre: str
    sucursal_nombre: str
    fecha: date
    hora_entrada: datetime | None
    hora_salida: datetime | None
    horas_conectado: float


class AsistenciaResumen(BaseModel):
    empleados_activos: int
    dias_con_actividad: int
    promedio_horas_por_dia: float


class ReporteAsistenciaOut(BaseModel):
    resumen: AsistenciaResumen
    detalle: list[AsistenciaFila]


# --------------------------------------------------------------- inventario --
class StockFila(BaseModel):
    producto_nombre: str
    talla_codigo: str
    color_nombre: str
    sucursal_nombre: str
    cantidad: int


class MovimientoFila(BaseModel):
    fecha: datetime
    tipo: str
    cantidad: int
    producto_nombre: str
    talla_codigo: str
    color_nombre: str
    sucursal_nombre: str
    empleado_nombre: str | None
    documento_referencia: str | None


class InventarioResumen(BaseModel):
    productos_distintos: int
    unidades_en_stock: int
    alertas_stock_bajo: int


class ReporteInventarioOut(BaseModel):
    resumen: InventarioResumen
    stock: list[StockFila]
    alertas: list[StockFila]
    movimientos: list[MovimientoFila]


# ---------------------------------------------------------------- productos --
class ProductoVentaFila(BaseModel):
    producto_id: int
    producto_nombre: str
    categoria: str
    marca: str
    cantidad_vendida: int
    total_vendido: Decimal
    precio_promedio: Decimal
    porcentaje_unidades: float


class ProductosResumen(BaseModel):
    productos_distintos: int
    total_unidades: int
    total_vendido: Decimal


class ReporteProductosOut(BaseModel):
    resumen: ProductosResumen
    detalle: list[ProductoVentaFila]


# ----------------------------------------------------------------- reservas --
class ReservaDetalleFila(BaseModel):
    id: int
    numero: int | None = None
    fecha_creacion: datetime
    cliente_nombre: str
    sucursal_nombre: str
    horario_atencion: datetime
    estado: str


class ReservaResumen(BaseModel):
    total: int
    pendientes: int
    confirmadas: int
    completadas: int
    canceladas: int
    vencidas: int
    tasa_conversion: float


class ReporteReservasOut(BaseModel):
    resumen: ReservaResumen
    detalle: list[ReservaDetalleFila]
