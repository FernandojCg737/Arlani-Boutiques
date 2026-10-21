from datetime import date
from decimal import Decimal

from pydantic import BaseModel


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
    sucursales: list[SucursalPublicaOut]
