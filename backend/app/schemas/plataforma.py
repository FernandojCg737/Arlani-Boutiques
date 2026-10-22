from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

Periodo = Literal["mensual", "anual", "prueba"]
COLOR_HEX = r"^#[0-9a-fA-F]{6}$"


class ResumenPlataformaOut(BaseModel):
    empresas_total: int
    empresas_activas: int
    empresas_suspendidas: int
    empresas_prueba: int
    mrr: Decimal
    sucursales_activas: int
    personal: int
    clientes: int
    ventas_mes: Decimal


class IngresoMesOut(BaseModel):
    mes: date
    ingresos: Decimal


class DistribucionPlanOut(BaseModel):
    codigo: str
    nombre: str
    empresas: int


class EmpresaOut(BaseModel):
    id: int
    nombre: str
    subdominio: str
    ciudad: str | None
    color_marca: str
    email_contacto: str | None
    estado: str
    fecha_creacion: datetime
    plan_codigo: str | None
    plan_nombre: str | None
    periodo: str | None
    monto: Decimal | None
    fecha_fin: date | None
    sucursales_activas: int
    max_sucursales: int | None
    usuarios: int
    ventas_total: Decimal


class EmpresaCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    subdominio: str = Field(min_length=3, max_length=40)
    ciudad: str | None = Field(default=None, max_length=80)
    color_marca: str = Field(default="#1f2a44", pattern=COLOR_HEX)
    email_contacto: EmailStr | None = None
    plan_codigo: str
    periodo: Periodo = "mensual"


class EmpresaUpdate(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    ciudad: str | None = Field(default=None, max_length=80)
    color_marca: str = Field(pattern=COLOR_HEX)
    email_contacto: EmailStr | None = None


class EmpresaEstadoIn(BaseModel):
    estado: Literal["activa", "suspendida"]


class EmpresaPlanIn(BaseModel):
    plan_codigo: str
    periodo: Periodo = "mensual"


class PlanOut(BaseModel):
    id: int
    codigo: str
    nombre: str
    precio_mensual: Decimal
    max_sucursales: int
    dias_prueba: int | None
    ia_generativa: bool
    operacion_offline: bool
    empresas: int


class PlanUpdate(BaseModel):
    precio_mensual: Decimal = Field(ge=0, le=100000)
    max_sucursales: int = Field(ge=1, le=500)
    ia_generativa: bool


class LimiteSucursalesOut(BaseModel):
    usadas: int
    maximo: int
    disponibles: int


class ActividadOut(BaseModel):
    id: int
    accion: str
    entidad_afectada: str
    entidad_id: int | None
    detalle: str | None
    fecha: datetime
    usuario_nombre: str
