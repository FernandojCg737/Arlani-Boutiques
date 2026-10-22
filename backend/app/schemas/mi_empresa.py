from datetime import date
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
    # La tienda original tiene su sitio completo (/atelier); las demas
    # muestran su catalogo dentro de su pagina /tienda-<subdominio>.
    sitio_propio: bool
    sucursales: list[SucursalPublicaOut]
