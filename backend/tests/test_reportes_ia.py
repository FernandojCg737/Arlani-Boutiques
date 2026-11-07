"""Reportes generativos (Desafio V, 8.3): del pedido en lenguaje natural a
la consulta controlada. Los filtros (fechas, sucursal, categoria, producto)
salen de la frase y el motor solo usa piezas de su lista blanca."""

from datetime import date

import pytest
from fastapi import HTTPException

from app.core.reporte_dinamico import FUENTES_TIENDA, ejecutar
from app.ml.consulta import interpretar

HOY = date(2026, 11, 7)
SUCURSALES = [(5, "Sucursal Centro"), (6, "Sucursal Norte")]
CATEGORIAS = [(1, "Vestidos"), (2, "Blusas"), (3, "Pantalones")]
PRODUCTOS = [(10, "Polo Básico"), (11, "Polo"), (12, "Jean Slim")]


def _c(texto: str, intencion: str):
    return interpretar(texto, intencion, HOY, SUCURSALES, CATEGORIAS, PRODUCTOS)


# --------------------------------------------------- interpretacion de la frase


def test_ventas_de_septiembre_agrupadas_por_sucursal():
    c = _c("Mostrame las ventas de septiembre agrupadas por sucursal", "ventas_sucursal")
    assert c.fuente == "ventas" and "sucursal" in c.agrupar
    assert (c.desde, c.hasta) == (date(2026, 9, 1), date(2026, 9, 30))


def test_top_n_y_filtro_por_categoria():
    c = _c("los 5 productos más vendidos de blusas este mes", "top_productos")
    assert c.limite == 5 and c.categoria_id == 2
    assert c.desde == date(2026, 11, 1) and "Categoría: Blusas" in c.filtros


def test_categoria_en_singular_o_plural():
    assert _c("ventas de vestido por semana", "ventas_periodo").categoria_id == 1
    assert _c("ventas de vestidos por semana", "ventas_periodo").categoria_id == 1


def test_filtro_por_producto_gana_el_nombre_mas_largo():
    c = _c("ventas del polo básico por semana", "ventas_periodo")
    assert c.producto_id == 10 and c.categoria_id is None
    assert c.agrupar == ["semana"]


def test_stock_de_un_producto_se_desglosa_por_talla_y_color():
    c = _c("stock del jean slim en la sucursal norte", "stock")
    assert (c.producto_id, c.sucursal_id) == (12, 6)
    assert c.agrupar == ["talla", "color"]


def test_ultimos_tres_meses():
    c = _c("compará las ventas de las sucursales durante los últimos tres meses", "ventas_sucursal")
    assert (HOY - c.desde).days == 89 and c.hasta == HOY


def test_sin_periodo_usa_los_ultimos_30_dias_y_lo_avisa():
    c = _c("ventas por semana", "ventas_periodo")
    assert (HOY - c.desde).days == 29
    assert any("no se indicó" in f for f in c.filtros)


def test_agrupar_por_categoria_no_filtra_por_categoria():
    c = _c("qué categorías generaron mayores ingresos, incluidas las blusas", "categorias")
    assert c.agrupar == ["categoria"] and c.categoria_id is None


# ------------------------------------------------- consultas controladas en la base


def test_el_motor_rechaza_fuentes_y_columnas_fuera_de_la_lista_blanca():
    with pytest.raises(HTTPException):
        ejecutar(None, FUENTES_TIENDA, "usuario; DROP TABLE venta", ["producto"], ["unidades"], None, None)
    with pytest.raises(HTTPException):
        ejecutar(None, FUENTES_TIENDA, "productos", ["password_hash"], ["unidades"], None, None)


@pytest.mark.parametrize("fuente", list(FUENTES_TIENDA))
def test_filtros_de_categoria_y_producto_en_cada_fuente(prueba, fuente):
    from app.db.session import SessionLocal

    fila = prueba.sql(
        """SELECT pr.id, pr.nombre, pr.categoria_id, c.nombre AS categoria FROM producto pr
           JOIN categoria c ON c.id = pr.categoria_id
           WHERE EXISTS (SELECT 1 FROM item_linea il WHERE il.producto_id = pr.id)
              OR EXISTS (SELECT 1 FROM inventario i WHERE i.producto_id = pr.id)
           ORDER BY pr.id LIMIT 1"""
    ).mappings().first()
    if fila is None:
        pytest.skip("no hay productos con movimiento")
    db = SessionLocal(bind=prueba.conexion, join_transaction_mode="create_savepoint")
    f = FUENTES_TIENDA[fuente]
    dim = "producto" if "producto" in f.dimensiones else next(iter(f.dimensiones))
    metrica = next(iter(f.metricas))
    por_producto = ejecutar(db, FUENTES_TIENDA, fuente, [dim], [metrica], None, None, producto_id=fila["id"])
    por_categoria = ejecutar(db, FUENTES_TIENDA, fuente, [dim], [metrica], None, None, categoria_id=fila["categoria_id"])
    todo = ejecutar(db, FUENTES_TIENDA, fuente, [dim], [metrica], None, None)
    if dim == "producto":
        assert {r["d0"] for r in por_producto.filas} <= {fila["nombre"]}
    total = lambda r: sum(float(x[metrica] or 0) for x in r.filas)  # noqa: E731
    assert total(por_producto) <= total(por_categoria) <= total(todo)
    db.close()
