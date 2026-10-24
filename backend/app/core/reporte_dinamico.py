"""Reportes dinamicos (CU07 de cada tienda y CU20 de la plataforma).

El usuario elige la fuente de datos, como agrupar (1 o 2 dimensiones), que
medir y los filtros. La consulta se arma SOLO con piezas de esta lista
blanca (nunca con texto del usuario) y los valores van como parametros.
En las fuentes de tienda manda el aislamiento por empresa (RLS); las de la
plataforma son solo del SuperAdministrador.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.reporte_export import Columna, Reporte

BO = "AT TIME ZONE 'UTC' AT TIME ZONE 'America/La_Paz'"


def _tiempo(col: str) -> dict[str, tuple[str, str]]:
    return {
        "dia": ("Día", f"to_char(({col} {BO})::date, 'YYYY-MM-DD')"),
        "semana": ("Semana", f"to_char(date_trunc('week', {col} {BO}), 'IYYY-\"S\"IW')"),
        "mes": ("Mes", f"to_char({col} {BO}, 'YYYY-MM')"),
    }


@dataclass
class Fuente:
    etiqueta: str
    descripcion: str
    origen: str
    fecha: str | None
    dimensiones: dict[str, tuple[str, str]]
    metricas: dict[str, tuple[str, str, str]]  # clave: (etiqueta, sql, tipo)
    donde: str = "TRUE"
    sucursal: str | None = None
    empresa: str | None = None
    defecto: tuple[list[str], list[str]] = field(default_factory=lambda: ([], []))


_LINEAS = """(SELECT id, venta_presencial_id AS venta_id, precio_unitario FROM detalle_venta_presencial
              UNION ALL SELECT id, venta_digital_id, precio_unitario FROM detalle_venta_digital)"""
_TIPO_VENTA = "CASE v.tipo WHEN 'venta_presencial' THEN 'Mostrador' ELSE 'En línea' END"

FUENTES_TIENDA: dict[str, Fuente] = {
    "ventas": Fuente(
        "Ventas", "Cada venta (en línea y de mostrador) con su total y forma de pago.",
        "venta v JOIN sucursal s ON s.id = v.sucursal_id", "v.fecha",
        {**_tiempo("v.fecha"), "sucursal": ("Sucursal", "s.nombre"), "tipo": ("Tipo", _TIPO_VENTA),
         "origen": ("Online/Offline", "upper(v.origen)"), "estado": ("Estado", "v.estado"),
         "metodo": ("Método de pago", "coalesce((SELECT p.metodo FROM pago p WHERE p.venta_id = v.id LIMIT 1), '-')")},
        {"cantidad": ("Ventas", "count(*)", "numero"), "total": ("Total vendido (Bs)", "sum(v.total)", "moneda"),
         "promedio": ("Ticket promedio (Bs)", "avg(v.total)", "moneda")},
        donde="v.estado <> 'cancelada'", sucursal="v.sucursal_id", defecto=(["mes"], ["cantidad", "total"]),
    ),
    "productos": Fuente(
        "Prendas vendidas", "Cada prenda vendida: producto, categoría, talla, color y lo que se cobró.",
        f"item_linea il JOIN {_LINEAS} d ON d.id = il.id JOIN venta v ON v.id = d.venta_id "
        "JOIN sucursal s ON s.id = v.sucursal_id JOIN producto pr ON pr.id = il.producto_id "
        "LEFT JOIN categoria c ON c.id = pr.categoria_id JOIN talla t ON t.id = il.talla_id JOIN color co ON co.id = il.color_id",
        "v.fecha",
        {**_tiempo("v.fecha"), "producto": ("Producto", "pr.nombre"), "categoria": ("Categoría", "coalesce(c.nombre, 'Sin categoría')"),
         "talla": ("Talla", "t.codigo"), "color": ("Color", "co.nombre"), "sucursal": ("Sucursal", "s.nombre"),
         "tipo": ("Tipo de venta", _TIPO_VENTA)},
        {"unidades": ("Unidades", "sum(il.cantidad)", "numero"),
         "ingresos": ("Ingresos (Bs)", "sum(il.cantidad * d.precio_unitario)", "moneda"),
         "ventas": ("Ventas", "count(DISTINCT v.id)", "numero")},
        donde="v.estado = 'pagada'", sucursal="v.sucursal_id", defecto=(["producto"], ["unidades", "ingresos"]),
    ),
    "reservas": Fuente(
        "Reservas", "Reservas de clientes por estado, sucursal y origen.",
        "reserva r JOIN sucursal s ON s.id = r.sucursal_id", "r.fecha_creacion",
        {**_tiempo("r.fecha_creacion"), "estado": ("Estado", "r.estado"), "sucursal": ("Sucursal", "s.nombre"),
         "origen": ("Online/Offline", "upper(r.origen)")},
        {"cantidad": ("Reservas", "count(*)", "numero")},
        sucursal="r.sucursal_id", defecto=(["estado"], ["cantidad"]),
    ),
    "inventario": Fuente(
        "Inventario", "Stock actual por sucursal, producto, categoría, talla y color (sin fechas).",
        "inventario i JOIN producto pr ON pr.id = i.producto_id JOIN sucursal s ON s.id = i.sucursal_id "
        "LEFT JOIN categoria c ON c.id = pr.categoria_id JOIN talla t ON t.id = i.talla_id JOIN color co ON co.id = i.color_id",
        None,
        {"sucursal": ("Sucursal", "s.nombre"), "producto": ("Producto", "pr.nombre"),
         "categoria": ("Categoría", "coalesce(c.nombre, 'Sin categoría')"), "talla": ("Talla", "t.codigo"), "color": ("Color", "co.nombre")},
        {"stock": ("Stock (unidades)", "sum(i.cantidad)", "numero"), "variantes": ("Variantes", "count(*)", "numero"),
         "agotadas": ("Agotadas", "count(*) FILTER (WHERE i.cantidad = 0)", "numero"),
         "valor": ("Valor del stock (Bs)", "sum(i.cantidad * pr.precio)", "moneda")},
        donde="pr.estado = 'activo'", sucursal="i.sucursal_id", defecto=(["sucursal"], ["stock", "valor"]),
    ),
}

FUENTES_PLATAFORMA: dict[str, Fuente] = {
    "suscripciones": Fuente(
        "Pagos de suscripción", "Lo que pagan las tiendas por su plan.",
        "pago_suscripcion ps JOIN empresa e ON e.id = ps.empresa_id LEFT JOIN suscripcion su ON su.id = ps.suscripcion_id "
        "LEFT JOIN plan_suscripcion pl ON pl.id = su.plan_id", "ps.fecha",
        {**_tiempo("ps.fecha"), "tienda": ("Tienda", "e.nombre"), "plan": ("Plan", "coalesce(pl.nombre, '-')"),
         "periodo": ("Periodo", "coalesce(su.periodo, '-')"), "metodo": ("Método", "ps.metodo")},
        {"pagos": ("Pagos", "count(*)", "numero"), "total_bob": ("Total (Bs)", "sum(ps.monto_bob)", "moneda"),
         "total_usd": ("Total (US$)", "sum(ps.monto_usd)", "moneda")},
        donde="ps.estado = 'completado'", empresa="ps.empresa_id", defecto=(["mes"], ["pagos", "total_bob"]),
    ),
    "comisiones": Fuente(
        "Comisiones por ventas", "Lo que gana Arlani por las ventas en línea de cada tienda.",
        "cuenta_tienda_movimiento m JOIN empresa e ON e.id = m.empresa_id", "m.fecha",
        {**_tiempo("m.fecha"), "tienda": ("Tienda", "e.nombre")},
        {"ventas": ("Ventas", "count(*)", "numero"), "vendido": ("Vendido (Bs)", "sum(m.base_bob)", "moneda"),
         "comision": ("Comisión (Bs)", "sum(m.monto_bob)", "moneda")},
        donde="m.tipo = 'comision'", empresa="m.empresa_id", defecto=(["tienda"], ["ventas", "vendido", "comision"]),
    ),
    "ventas": Fuente(
        "Ventas de las tiendas (GMV)", "Todo lo que venden las tiendas de la plataforma.",
        "venta v JOIN sucursal s ON s.id = v.sucursal_id JOIN empresa e ON e.id = s.empresa_id", "v.fecha",
        {**_tiempo("v.fecha"), "tienda": ("Tienda", "e.nombre"), "tipo": ("Tipo", _TIPO_VENTA),
         "origen": ("Online/Offline", "upper(v.origen)")},
        {"cantidad": ("Ventas", "count(*)", "numero"), "total": ("Total vendido (Bs)", "sum(v.total)", "moneda"),
         "promedio": ("Ticket promedio (Bs)", "avg(v.total)", "moneda")},
        donde="v.estado <> 'cancelada'", empresa="e.id", defecto=(["tienda"], ["cantidad", "total"]),
    ),
    "empresas": Fuente(
        "Tiendas (empresas)", "Las tiendas de la plataforma por plan, estado y ciudad.",
        "empresa e LEFT JOIN suscripcion su ON su.empresa_id = e.id AND su.estado = 'activa' "
        "LEFT JOIN plan_suscripcion pl ON pl.id = su.plan_id", "e.fecha_creacion",
        {"mes": ("Mes de alta", "to_char(e.fecha_creacion, 'YYYY-MM')"), "plan": ("Plan", "coalesce(pl.nombre, 'Sin plan')"),
         "estado": ("Estado", "e.estado"), "ciudad": ("Ciudad", "coalesce(e.ciudad, '-')")},
        {"cantidad": ("Tiendas", "count(DISTINCT e.id)", "numero"),
         "mrr": ("Ingreso mensual (Bs)", "sum(fn_mrr_suscripcion(su.periodo, su.monto))", "moneda")},
        empresa="e.id", defecto=(["plan"], ["cantidad", "mrr"]),
    ),
}


def catalogo(fuentes: dict[str, Fuente]) -> list[dict]:
    return [
        {
            "clave": k, "etiqueta": f.etiqueta, "descripcion": f.descripcion, "con_fechas": f.fecha is not None,
            "dimensiones": [{"clave": d, "etiqueta": v[0]} for d, v in f.dimensiones.items()],
            "metricas": [{"clave": m, "etiqueta": v[0]} for m, v in f.metricas.items()],
            "defecto": {"agrupar": f.defecto[0], "metricas": f.defecto[1]},
        }
        for k, f in fuentes.items()
    ]


def ejecutar(
    db: Session,
    fuentes: dict[str, Fuente],
    fuente: str,
    agrupar: list[str],
    metricas: list[str],
    desde: date | None,
    hasta: date | None,
    sucursal_id: int | None = None,
    empresa_id: int | None = None,
    marca: str = "Arlani Boutiques",
) -> Reporte:
    f = fuentes.get(fuente)
    if f is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Elige una fuente de datos válida.")
    agrupar = [a for a in dict.fromkeys(agrupar) if a in f.dimensiones][:2]
    metricas = [m for m in dict.fromkeys(metricas) if m in f.metricas]
    if not agrupar or not metricas:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Elige cómo agrupar y al menos una medida.")

    condiciones, params = [f.donde], {}
    sub = []
    if f.fecha and desde:
        condiciones.append(f"({f.fecha} {BO})::date >= :desde")
        params["desde"] = desde
    if f.fecha and hasta:
        condiciones.append(f"({f.fecha} {BO})::date <= :hasta")
        params["hasta"] = hasta
    if f.fecha and (desde or hasta):
        sub.append(f"Del {desde:%d/%m/%Y}" if desde else "Hasta")
        sub[-1] += f" al {hasta:%d/%m/%Y}" if hasta and desde else (f" {hasta:%d/%m/%Y}" if hasta else "")
    if sucursal_id is not None and f.sucursal:
        condiciones.append(f"{f.sucursal} = :sucursal")
        params["sucursal"] = sucursal_id
    if empresa_id is not None and f.empresa:
        condiciones.append(f"{f.empresa} = :empresa")
        params["empresa"] = empresa_id

    dims_sql = [f"{f.dimensiones[a][1]} AS d{i}" for i, a in enumerate(agrupar)]
    mets_sql = [f"coalesce({f.metricas[m][1]}, 0) AS {m}" for m in metricas]
    grupos = ", ".join(str(i + 1) for i in range(len(agrupar)))
    # Tiempo en orden cronologico; si no, de mayor a menor en la primera medida.
    orden = grupos if agrupar[0] in ("dia", "semana", "mes") else f"{len(agrupar) + 1} DESC"
    sql = (
        f"SELECT {', '.join(dims_sql + mets_sql)} FROM {f.origen} WHERE {' AND '.join(condiciones)} "
        f"GROUP BY {grupos} ORDER BY {orden} LIMIT 1000"
    )
    filas = [dict(r) for r in db.execute(text(sql), params).mappings()]

    columnas = [Columna(f"d{i}", f.dimensiones[a][0]) for i, a in enumerate(agrupar)]
    columnas += [Columna(m, f.metricas[m][0], f.metricas[m][2]) for m in metricas]
    totales = {"d0": "Total"}
    for m in metricas:
        if not m.startswith("promedio"):
            totales[m] = sum((r[m] or 0) for r in filas)
    titulo = f"{f.etiqueta} por " + " y ".join(f.dimensiones[a][0].lower() for a in agrupar)
    return Reporte(titulo, columnas, filas, subtitulo=" · ".join(sub) or None, totales=totales, marca=marca)


def periodo_por_defecto(hoy: date) -> tuple[date, date]:
    """Ultimos 6 meses (desde el dia 1)."""
    inicio = (hoy.replace(day=1) - timedelta(days=150)).replace(day=1)
    return inicio, hoy
