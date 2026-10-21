from datetime import date

from pydantic import BaseModel, EmailStr, Field


class EmpleadoCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    email: EmailStr
    tipo: str = Field(pattern="^(administrador|encargado_sucursal|cajero)$")
    sucursal_id: int | None = None
    rol_id: int | None = None
    # Solo lo usa el SuperAdministrador: el personal de una tienda siempre
    # crea usuarios en su propia empresa.
    empresa_id: int | None = None


class EmpleadoUpdate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    sucursal_id: int | None = None
    rol_id: int | None = None
    estado: str = Field(pattern="^(activo|inactivo)$")


class EmpleadoOut(BaseModel):
    id: int
    nombre: str
    email: EmailStr
    tipo: str
    estado: str
    fecha_registro: date
    metodo_registro: str
    sucursal_id: int | None
    sucursal_nombre: str | None
    rol_id: int | None
    rol_nombre: str | None
    empresa_id: int | None = None

    model_config = {"from_attributes": True}
