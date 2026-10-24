from datetime import date
from typing import Any

from pydantic import BaseModel, Field

FORMATO = r"^(pdf|excel|csv|html)$"
CORREO = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class ColumnaTabla(BaseModel):
    clave: str = Field(max_length=40)
    etiqueta: str = Field(max_length=80)
    tipo: str = Field(default="texto", pattern=r"^(texto|numero|moneda|fecha)$")


class TablaReporte(BaseModel):
    """Un reporte listo para ver, exportar o enviar."""

    titulo: str = Field(max_length=150)
    subtitulo: str | None = Field(default=None, max_length=300)
    columnas: list[ColumnaTabla] = Field(min_length=1, max_length=20)
    filas: list[dict[str, Any]] = Field(max_length=5000)
    totales: dict[str, Any] | None = None


class ExportarTablaIn(BaseModel):
    tabla: TablaReporte
    formato: str = Field(pattern=FORMATO)
    # Con correo, el reporte se envia como adjunto en vez de descargarse.
    correo: str | None = Field(default=None, max_length=150, pattern=CORREO)


class DinamicoIn(BaseModel):
    fuente: str = Field(max_length=30)
    agrupar: list[str] = Field(min_length=1, max_length=2)
    metricas: list[str] = Field(min_length=1, max_length=6)
    desde: date | None = None
    hasta: date | None = None
    sucursal_id: int | None = None
    empresa_id: int | None = None
