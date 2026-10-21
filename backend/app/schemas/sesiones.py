from datetime import datetime

from pydantic import BaseModel


class SesionActivaOut(BaseModel):
    id: int
    nombre: str
    email: str
    tipo: str
    rol: str | None
    empresa_id: int | None
    empresa_nombre: str | None
    sucursal_nombre: str | None
    expira_en: datetime
