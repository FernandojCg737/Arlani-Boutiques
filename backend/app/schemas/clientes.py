from datetime import date, datetime, timezone

from pydantic import BaseModel, EmailStr, Field, field_serializer


class ClienteAdminCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    email: EmailStr
    telefono: str | None = Field(default=None, max_length=30)
    direccion: str | None = Field(default=None, max_length=255)


class ClienteAdminUpdate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    telefono: str | None = Field(default=None, max_length=30)
    direccion: str | None = Field(default=None, max_length=255)
    estado: str = Field(pattern="^(activo|inactivo)$")


class ClienteAdminOut(BaseModel):
    id: int
    nombre: str
    email: EmailStr
    telefono: str | None
    direccion: str | None
    estado: str
    fecha_registro: date
    metodo_registro: str
    # Solo cuando se listan los clientes de una empresa.
    relacion: "RelacionTiendaOut | None" = None

    model_config = {"from_attributes": True}


class RelacionTiendaOut(BaseModel):
    # Que hizo el cliente con la tienda (fn_clientes_de_empresa).
    compras: int
    reservas: int
    en_carrito: int
    usos_probador: int
    ultima_interaccion: datetime | None

    @field_serializer("ultima_interaccion")
    def _serializar_fecha(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


class ClientesPorEmpresaOut(BaseModel):
    empresa_id: int
    total: int
