from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_serializer


class CalificacionIn(BaseModel):
    estrellas: int = Field(ge=1, le=5)
    comentario: str | None = Field(default=None, max_length=1000)


class CalificacionOut(BaseModel):
    id: int
    venta_id: int
    # Numero de la venta en su tienda (el que se muestra).
    venta_numero: int | None = None
    estrellas: int
    comentario: str | None
    fecha: datetime

    @field_serializer("fecha")
    def _serialize_fecha(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class CalificacionAdminOut(CalificacionOut):
    cliente_nombre: str
    cliente_email: str
    sucursal_nombre: str
    empleado_nombre: str | None


class DistribucionEstrellas(BaseModel):
    estrellas: int
    cantidad: int


class CalificacionResumen(BaseModel):
    promedio: float
    total: int
    distribucion: list[DistribucionEstrellas]


class CalificacionPage(BaseModel):
    resumen: CalificacionResumen
    items: list[CalificacionAdminOut]
    total: int
    page: int
    page_size: int
