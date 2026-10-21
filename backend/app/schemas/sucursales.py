from datetime import date

from pydantic import BaseModel, Field


class SucursalCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    ciudad_nombre: str = Field(min_length=2, max_length=100)
    departamento: str = Field(min_length=2, max_length=100)
    direccion: str = Field(min_length=3, max_length=255)
    horario_atencion: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=30)
    estado: str = Field(default="activa", pattern="^(activa|inactiva)$")
    # CU01: coordenadas para validar la ubicacion al marcar asistencia.
    latitud: float | None = Field(default=None, ge=-90, le=90)
    longitud: float | None = Field(default=None, ge=-180, le=180)


class SucursalUpdate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    ciudad_nombre: str = Field(min_length=2, max_length=100)
    departamento: str = Field(min_length=2, max_length=100)
    direccion: str = Field(min_length=3, max_length=255)
    horario_atencion: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=30)
    estado: str = Field(pattern="^(activa|inactiva)$")
    latitud: float | None = Field(default=None, ge=-90, le=90)
    longitud: float | None = Field(default=None, ge=-180, le=180)


class SucursalOut(BaseModel):
    id: int
    nombre: str
    ciudad_id: int
    ciudad_nombre: str
    departamento: str
    direccion: str
    horario_atencion: str | None
    telefono: str | None
    estado: str
    fecha_creacion: date
    latitud: float | None
    longitud: float | None
    empresa_id: int | None = None

    model_config = {"from_attributes": True}


class SucursalPublicaOut(BaseModel):
    id: int
    nombre: str
    direccion: str
    horario_atencion: str | None
