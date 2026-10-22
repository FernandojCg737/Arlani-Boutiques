from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class ImagenOut(BaseModel):
    id: int
    url: str
    orden: int

    model_config = {"from_attributes": True}


class PrendaArOut(BaseModel):
    url: str
    ancla_hombro_izq_x: Decimal
    ancla_hombro_izq_y: Decimal
    ancla_hombro_der_x: Decimal
    ancla_hombro_der_y: Decimal
    ancla_torso_y: Decimal

    model_config = {"from_attributes": True}


class PrendaArUpsert(BaseModel):
    ancla_hombro_izq_x: Decimal = Field(default=Decimal("0.20"), ge=0, le=1)
    ancla_hombro_izq_y: Decimal = Field(default=Decimal("0.15"), ge=0, le=1)
    ancla_hombro_der_x: Decimal = Field(default=Decimal("0.80"), ge=0, le=1)
    ancla_hombro_der_y: Decimal = Field(default=Decimal("0.15"), ge=0, le=1)
    ancla_torso_y: Decimal = Field(default=Decimal("0.65"), ge=0, le=1)


class ArSesionOut(BaseModel):
    token: str
    expira_en: Any = None
    imagen_url: str
    prompt: str


class ArFotoTrabajoOut(BaseModel):
    job_id: str


class ArFotoEstadoOut(BaseModel):
    estado: str
    listo: bool
    error: bool = False


class ProductoCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    descripcion: str | None = None
    precio: Decimal = Field(gt=0, decimal_places=2)
    precio_original: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    categoria_id: int
    marca_id: int
    proveedor_id: int
    temporada_id: int
    coleccion_id: int


class ProductoUpdate(ProductoCreate):
    estado: str = Field(pattern="^(activo|inactivo)$")


class DisponibilidadOut(BaseModel):
    sucursal_nombre: str
    cantidad: int


class ProductoOut(BaseModel):
    id: int
    nombre: str
    descripcion: str | None
    precio: Decimal
    precio_original: Decimal | None
    estado: str
    categoria_id: int
    categoria_nombre: str
    marca_id: int
    marca_nombre: str
    proveedor_id: int
    proveedor_nombre: str
    temporada_id: int
    temporada_nombre: str
    coleccion_id: int
    coleccion_nombre: str
    imagenes: list[ImagenOut]
    sucursales_disponibles: list[DisponibilidadOut]
    prenda_ar: PrendaArOut | None = None

    model_config = {"from_attributes": True}


class OpcionOut(BaseModel):
    id: int
    nombre: str

    model_config = {"from_attributes": True}


class CatalogoBaseOut(BaseModel):
    categorias: list[OpcionOut]
    marcas: list[OpcionOut]
    temporadas: list[OpcionOut]
    colecciones: list[OpcionOut]
    proveedores: list[OpcionOut]
    sucursales: list[OpcionOut]
    tallas: list[OpcionOut]
    colores: list[OpcionOut]


class MarcaCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)


class MarcaOut(BaseModel):
    id: int
    nombre: str

    model_config = {"from_attributes": True}


class ColorCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=50)


class InventarioOut(BaseModel):
    id: int
    sucursal_id: int
    sucursal_nombre: str
    talla_id: int
    talla_codigo: str
    color_id: int
    color_nombre: str
    cantidad: int

    model_config = {"from_attributes": True}


class InventarioUpsert(BaseModel):
    sucursal_id: int
    talla_id: int
    color_id: int
    cantidad: int = Field(ge=0)


class InventarioCantidadUpdate(BaseModel):
    cantidad: int = Field(ge=0)


class ProductoPublicoOut(BaseModel):
    id: int
    # Tienda que lo vende (cada boutique muestra solo lo suyo).
    tienda: str
    tienda_nombre: str
    tienda_logo: str | None
    tienda_color: str
    nombre: str
    descripcion: str | None
    precio: Decimal
    precio_original: Decimal | None
    marca_nombre: str
    categoria_nombre: str
    temporada_nombre: str
    imagenes: list[str]
    sucursales_disponibles: list[str]
    prenda_ar: PrendaArOut | None = None
