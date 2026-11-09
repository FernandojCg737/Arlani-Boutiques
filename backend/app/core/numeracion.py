"""Numeracion propia de cada tienda (#1, #2...) de lo que se muestra con numero.

El id de estas tablas es de todo el sistema (lo comparten todas las tiendas);
la columna `numero` la asigna la base (trigger trg_0_numero, una secuencia por
tienda) y es lo que ven las pantallas. Ver la migracion b2d4f6a8c013.
"""

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import text

# entidad de la bitacora -> tabla con columna numero
TABLAS_NUMERADAS = {
    "venta": "venta",
    "reserva": "reserva",
    "devolucion": "devolucion",
    "cambio_prenda": "cambio_prenda",
    "caja": "caja",
    "operacion_offline": "operacion_offline",
    "backup": "backup",
}


def numeros_de(db, pares: Iterable[tuple[str | None, int | None]]) -> dict[tuple[str, int], int]:
    """{(entidad, id): numero} de las entidades numeradas (una consulta por tabla)."""
    por_tabla: dict[str, set[int]] = defaultdict(set)
    for entidad, ident in pares:
        if entidad in TABLAS_NUMERADAS and ident is not None:
            por_tabla[entidad].add(ident)
    numeros: dict[tuple[str, int], int] = {}
    for entidad, ids in por_tabla.items():
        filas = db.execute(
            text(f"SELECT id, numero FROM {TABLAS_NUMERADAS[entidad]} WHERE id = ANY(:ids)"), {"ids": list(ids)}
        )
        for ident, numero in filas:
            if numero is not None:
                numeros[(entidad, ident)] = numero
    return numeros
