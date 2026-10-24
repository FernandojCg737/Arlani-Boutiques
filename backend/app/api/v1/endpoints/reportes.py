from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import require_permiso
from app.core.email import nombre_marca
from app.core.rate_limit import verificar_limite
from app.core.reporte_export import descargar, desde_listas, enviar
from app.db.session import get_db
from app.models import Usuario
from app.schemas.reportes import (
    AsistenciaFila,
    AsistenciaResumen,
    DashboardOut,
    InventarioResumen,
    MovimientoFila,
    ProductosResumen,
    ProductoVentaFila,
    ReporteAsistenciaOut,
    ReporteInventarioOut,
    ReporteProductosOut,
    ReporteReservasOut,
    ReporteVentasOut,
    ReservaDetalleFila,
    ReservaResumen,
    SerieCategoria,
    SerieDia,
    StockFila,
    VentaDetalleFila,
    VentaResumen,
)

router = APIRouter()

# CU16 "Gestion Reportes y Dashboards": panel de solo lectura para
# Administrador (unico rol con este permiso en el seed) con un dashboard
# general con KPIs/graficos y 4 reportes filtrables (ventas, asistencia de
# empleados, inventario, reservas), cada uno exportable a CSV/Excel. El
# "PDF"/"HTML" los resuelve el frontend imprimiendo la misma vista (igual
# que la factura de CU11), asi que aca solo hace falta JSON + CSV + Excel.


def _rango_fechas(desde: date | None, hasta: date | None, dias_default: int = 30) -> tuple[datetime, datetime]:
    hasta_d = hasta or date.today()
    desde_d = desde or (hasta_d - timedelta(days=dias_default - 1))
    inicio = datetime.combine(desde_d, time.min)
    fin_exclusivo = datetime.combine(hasta_d + timedelta(days=1), time.min)
    return inicio, fin_exclusivo


def _dec(v: object) -> Decimal:
    return Decimal(str(v)) if v is not None else Decimal("0")


# ---------------------------------------------------------------- dashboard --


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU16")),
) -> DashboardOut:
    hoy = date.today()
    hoy_inicio = datetime.combine(hoy, time.min)
    hoy_fin = datetime.combine(hoy + timedelta(days=1), time.min)
    mes_inicio_d = hoy.replace(day=1)
    mes_inicio = datetime.combine(mes_inicio_d, time.min)
    desde_30, _ = _rango_fechas(None, hoy, 30)

    ventas_hoy = db.execute(
        text(
            "SELECT COALESCE(SUM(v.total),0), COUNT(*) FROM venta v JOIN pago p ON p.venta_id=v.id "
            "WHERE v.fecha >= :inicio AND v.fecha < :fin AND p.estado='completado'"
        ),
        {"inicio": hoy_inicio, "fin": hoy_fin},
    ).one()

    ventas_mes = db.execute(
        text(
            "SELECT COALESCE(SUM(v.total),0), COUNT(*) FROM venta v JOIN pago p ON p.venta_id=v.id "
            "WHERE v.fecha >= :inicio AND v.fecha < :fin AND p.estado='completado'"
        ),
        {"inicio": mes_inicio, "fin": hoy_fin},
    ).one()

    reservas_activas = db.execute(
        text("SELECT COUNT(*) FROM reserva WHERE estado IN ('pendiente','confirmada')")
    ).scalar_one()

    clientes_nuevos = db.execute(
        text("SELECT COUNT(*) FROM usuario WHERE tipo='cliente' AND fecha_registro >= :inicio"),
        {"inicio": mes_inicio_d},
    ).scalar_one()

    por_dia = db.execute(
        text(
            "SELECT date_trunc('day', v.fecha)::date AS dia, COALESCE(SUM(v.total),0), COUNT(*) "
            "FROM venta v JOIN pago p ON p.venta_id=v.id "
            "WHERE v.fecha >= :inicio AND v.fecha < :fin AND p.estado='completado' "
            "GROUP BY dia ORDER BY dia"
        ),
        {"inicio": desde_30, "fin": hoy_fin},
    ).all()

    por_metodo = db.execute(
        text(
            "SELECT p.metodo, COALESCE(SUM(v.total),0), COUNT(*) "
            "FROM venta v JOIN pago p ON p.venta_id=v.id "
            "WHERE v.fecha >= :inicio AND v.fecha < :fin AND p.estado='completado' "
            "GROUP BY p.metodo ORDER BY 2 DESC"
        ),
        {"inicio": desde_30, "fin": hoy_fin},
    ).all()

    por_sucursal = db.execute(
        text(
            "SELECT s.nombre, COALESCE(SUM(v.total),0), COUNT(*) "
            "FROM venta v JOIN pago p ON p.venta_id=v.id JOIN sucursal s ON s.id=v.sucursal_id "
            "WHERE v.fecha >= :inicio AND v.fecha < :fin AND p.estado='completado' "
            "GROUP BY s.nombre ORDER BY 2 DESC"
        ),
        {"inicio": desde_30, "fin": hoy_fin},
    ).all()

    top_productos = db.execute(
        text(_SQL_TOP_PRODUCTOS.format(where="v.fecha >= :inicio AND v.fecha < :fin")),
        {"inicio": desde_30, "fin": hoy_fin},
    ).all()

    total_mes, cant_mes = _dec(ventas_mes[0]), int(ventas_mes[1])
    ticket_prom = (total_mes / cant_mes) if cant_mes else Decimal("0")

    return DashboardOut(
        ventas_hoy_total=_dec(ventas_hoy[0]),
        ventas_hoy_cantidad=int(ventas_hoy[1]),
        ventas_mes_total=total_mes,
        ventas_mes_cantidad=cant_mes,
        ticket_promedio_mes=ticket_prom,
        reservas_activas=int(reservas_activas),
        clientes_nuevos_mes=int(clientes_nuevos),
        ventas_por_dia=[SerieDia(fecha=r[0], total=_dec(r[1]), cantidad=int(r[2])) for r in por_dia],
        ventas_por_metodo=[SerieCategoria(etiqueta=r[0], total=_dec(r[1]), cantidad=int(r[2])) for r in por_metodo],
        ventas_por_sucursal=[SerieCategoria(etiqueta=r[0], total=_dec(r[1]), cantidad=int(r[2])) for r in por_sucursal],
        top_productos=[SerieCategoria(etiqueta=r[0], total=_dec(r[2]), cantidad=int(r[1])) for r in top_productos],
    )


# ------------------------------------------------------------------ ventas --

_SQL_TOP_PRODUCTOS = """
SELECT prod.nombre, SUM(il.cantidad) AS cantidad, SUM(il.cantidad * d.precio_unitario) AS total
FROM (
    SELECT dvp.id, dvp.precio_unitario, vp.id AS venta_id FROM detalle_venta_presencial dvp
    JOIN venta_presencial vp ON vp.id = dvp.venta_presencial_id
    UNION ALL
    SELECT dvd.id, dvd.precio_unitario, vd.id AS venta_id FROM detalle_venta_digital dvd
    JOIN venta_digital vd ON vd.id = dvd.venta_digital_id
) d
JOIN item_linea il ON il.id = d.id
JOIN producto prod ON prod.id = il.producto_id
JOIN venta v ON v.id = d.venta_id
JOIN pago p ON p.venta_id = v.id
WHERE {where} AND p.estado = 'completado'
GROUP BY prod.nombre ORDER BY cantidad DESC LIMIT 5
"""

_WHERE_VENTAS = (
    "v.fecha >= :desde AND v.fecha < :hasta "
    "AND (:sucursal_id IS NULL OR v.sucursal_id = :sucursal_id) "
    "AND (:tipo IS NULL OR v.tipo = :tipo) "
    "AND (:metodo IS NULL OR p.metodo = :metodo)"
)


def _datos_ventas(
    db: Session, desde: datetime, hasta: datetime, sucursal_id: int | None, tipo: str | None, metodo: str | None
) -> ReporteVentasOut:
    params = {"desde": desde, "hasta": hasta, "sucursal_id": sucursal_id, "tipo": tipo, "metodo": metodo}

    resumen_row = db.execute(
        text(
            f"SELECT COALESCE(SUM(v.total),0), COUNT(*) FROM venta v JOIN pago p ON p.venta_id=v.id "
            f"WHERE {_WHERE_VENTAS} AND p.estado='completado'"
        ),
        params,
    ).one()
    total_vendido, cantidad = _dec(resumen_row[0]), int(resumen_row[1])
    ticket_prom = (total_vendido / cantidad) if cantidad else Decimal("0")

    por_metodo = db.execute(
        text(
            f"SELECT p.metodo, COALESCE(SUM(v.total),0), COUNT(*) FROM venta v JOIN pago p ON p.venta_id=v.id "
            f"WHERE {_WHERE_VENTAS} AND p.estado='completado' GROUP BY p.metodo ORDER BY 2 DESC"
        ),
        params,
    ).all()

    por_sucursal = db.execute(
        text(
            f"SELECT s.nombre, COALESCE(SUM(v.total),0), COUNT(*) FROM venta v JOIN pago p ON p.venta_id=v.id "
            f"JOIN sucursal s ON s.id=v.sucursal_id "
            f"WHERE {_WHERE_VENTAS} AND p.estado='completado' GROUP BY s.nombre ORDER BY 2 DESC"
        ),
        params,
    ).all()

    top_productos = db.execute(text(_SQL_TOP_PRODUCTOS.format(where=_WHERE_VENTAS)), params).all()

    detalle = db.execute(
        text(
            "SELECT v.id, v.fecha, u.nombre, s.nombre, v.tipo, p.metodo, p.estado, v.total "
            "FROM venta v JOIN pago p ON p.venta_id=v.id JOIN sucursal s ON s.id=v.sucursal_id "
            "JOIN cliente c ON c.id=v.cliente_id JOIN usuario u ON u.id=c.id "
            f"WHERE {_WHERE_VENTAS} ORDER BY v.fecha DESC LIMIT 500"
        ),
        params,
    ).all()

    return ReporteVentasOut(
        resumen=VentaResumen(total_vendido=total_vendido, cantidad_ventas=cantidad, ticket_promedio=ticket_prom),
        por_metodo=[SerieCategoria(etiqueta=r[0], total=_dec(r[1]), cantidad=int(r[2])) for r in por_metodo],
        por_sucursal=[SerieCategoria(etiqueta=r[0], total=_dec(r[1]), cantidad=int(r[2])) for r in por_sucursal],
        top_productos=[SerieCategoria(etiqueta=r[0], total=_dec(r[2]), cantidad=int(r[1])) for r in top_productos],
        detalle=[
            VentaDetalleFila(
                id=r[0], fecha=r[1], cliente_nombre=r[2], sucursal_nombre=r[3], tipo=r[4],
                metodo_pago=r[5], estado_pago=r[6], total=_dec(r[7]),
            )
            for r in detalle
        ],
    )


@router.get("/ventas", response_model=ReporteVentasOut)
def reporte_ventas(
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    tipo: str | None = Query(default=None),
    metodo: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU16")),
) -> ReporteVentasOut:
    desde, hasta = _rango_fechas(fecha_desde, fecha_hasta)
    return _datos_ventas(db, desde, hasta, sucursal_id, tipo, metodo)


@router.get("/ventas/exportar")
def exportar_ventas(
    formato: str = Query(pattern="^(csv|excel|html|pdf)$"),
    # Con correo, el reporte se envia como adjunto en vez de descargarse.
    correo: str | None = Query(default=None, max_length=150, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    tipo: str | None = Query(default=None),
    metodo: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU16")),
) -> Response:
    desde, hasta = _rango_fechas(fecha_desde, fecha_hasta)
    datos = _datos_ventas(db, desde, hasta, sucursal_id, tipo, metodo)
    headers = ["ID", "Fecha", "Cliente", "Sucursal", "Tipo", "Metodo de pago", "Estado de pago", "Total (Bs)"]
    filas = [
        [d.id, d.fecha.strftime("%d/%m/%Y %H:%M"), d.cliente_nombre, d.sucursal_nombre, d.tipo, d.metodo_pago,
         d.estado_pago, float(d.total)]
        for d in datos.detalle
    ]
    return _responder(db, _empleado, "Reporte de Ventas", headers, filas, formato, correo)


# --------------------------------------------------------------- asistencia --


def _responder(db: Session, usuario: Usuario, titulo: str, headers: list[str], filas: list[list], formato: str, correo: str | None):
    """Descarga el reporte o lo envia por correo como adjunto (CU07)."""
    r = desde_listas(titulo, headers, filas, marca=nombre_marca(db, _empresa_de(db, usuario)))
    if correo:
        verificar_limite("reporte_correo", str(usuario.id), 10, 600)
        return enviar(r, formato, correo)
    return descargar(r, formato)


def _empresa_de(db: Session, usuario: Usuario) -> int | None:
    """La tienda del personal, o la que eligio el SuperAdministrador (X-Empresa)."""
    return usuario.empresa_id if usuario.empresa_id is not None else db.info.get("empresa_scope")


def _datos_asistencia(
    db: Session,
    desde: datetime,
    hasta: datetime,
    sucursal_id: int | None,
    empleado_id: int | None,
    empresa_id: int | None = None,
) -> ReporteAsistenciaOut:
    # empresa_id: el personal de una tienda solo ve a su empresa; None (el
    # SuperAdministrador) ve el personal de todas.
    filas = db.execute(
        text(
            "SELECT b.usuario_id, u.nombre, COALESCE(s.nombre, 'Sin sucursal'), b.accion, b.fecha "
            "FROM bitacora b JOIN usuario u ON u.id = b.usuario_id JOIN empleado emp ON emp.id = u.id "
            "LEFT JOIN sucursal s ON s.id = emp.sucursal_id "
            "WHERE b.accion IN ('LOGIN','LOGOUT') AND b.fecha >= :desde AND b.fecha < :hasta "
            "AND (:sucursal_id IS NULL OR emp.sucursal_id = :sucursal_id) "
            "AND (:empleado_id IS NULL OR b.usuario_id = :empleado_id) "
            "AND (CAST(:empresa_id AS INTEGER) IS NULL OR u.empresa_id = :empresa_id) "
            "AND u.tipo <> 'superadministrador' "
            "ORDER BY b.usuario_id, b.fecha"
        ),
        {
            "desde": desde,
            "hasta": hasta,
            "sucursal_id": sucursal_id,
            "empleado_id": empleado_id,
            "empresa_id": empresa_id,
        },
    ).all()

    grupos: dict[tuple[int, date], dict] = {}
    for usuario_id, nombre, sucursal_nombre, accion, fecha in filas:
        clave = (usuario_id, fecha.date())
        grupo = grupos.setdefault(
            clave,
            {"empleado_id": usuario_id, "empleado_nombre": nombre, "sucursal_nombre": sucursal_nombre, "eventos": []},
        )
        grupo["eventos"].append((accion, fecha))

    detalle: list[AsistenciaFila] = []
    for (usuario_id, dia), grupo in sorted(grupos.items(), key=lambda kv: (kv[1]["empleado_nombre"], kv[0][1])):
        eventos = grupo["eventos"]
        logins = [f for a, f in eventos if a == "LOGIN"]
        logouts = [f for a, f in eventos if a == "LOGOUT"]

        segundos = 0.0
        entrada_pendiente: datetime | None = None
        for accion, fecha in eventos:
            if accion == "LOGIN":
                entrada_pendiente = fecha
            elif accion == "LOGOUT" and entrada_pendiente is not None:
                segundos += (fecha - entrada_pendiente).total_seconds()
                entrada_pendiente = None

        detalle.append(
            AsistenciaFila(
                empleado_id=usuario_id,
                empleado_nombre=grupo["empleado_nombre"],
                sucursal_nombre=grupo["sucursal_nombre"],
                fecha=dia,
                hora_entrada=min(logins) if logins else None,
                hora_salida=max(logouts) if logouts else None,
                horas_conectado=round(segundos / 3600, 2),
            )
        )

    empleados_activos = len({d.empleado_id for d in detalle})
    dias_con_actividad = len({(d.empleado_id, d.fecha) for d in detalle})
    promedio = round(sum(d.horas_conectado for d in detalle) / len(detalle), 2) if detalle else 0.0

    return ReporteAsistenciaOut(
        resumen=AsistenciaResumen(
            empleados_activos=empleados_activos, dias_con_actividad=dias_con_actividad, promedio_horas_por_dia=promedio
        ),
        detalle=detalle,
    )


@router.get("/asistencia", response_model=ReporteAsistenciaOut)
def reporte_asistencia(
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    empleado_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU16")),
) -> ReporteAsistenciaOut:
    desde, hasta = _rango_fechas(fecha_desde, fecha_hasta)
    return _datos_asistencia(db, desde, hasta, sucursal_id, empleado_id, _empresa_de(db, _empleado))


@router.get("/asistencia/exportar")
def exportar_asistencia(
    formato: str = Query(pattern="^(csv|excel|html|pdf)$"),
    # Con correo, el reporte se envia como adjunto en vez de descargarse.
    correo: str | None = Query(default=None, max_length=150, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    empleado_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU16")),
) -> Response:
    desde, hasta = _rango_fechas(fecha_desde, fecha_hasta)
    datos = _datos_asistencia(db, desde, hasta, sucursal_id, empleado_id, _empresa_de(db, _empleado))
    headers = ["Empleado", "Sucursal", "Fecha", "Hora entrada", "Hora salida", "Horas conectado"]
    filas = [
        [
            d.empleado_nombre, d.sucursal_nombre, d.fecha.strftime("%d/%m/%Y"),
            d.hora_entrada.strftime("%H:%M") if d.hora_entrada else "-",
            d.hora_salida.strftime("%H:%M") if d.hora_salida else "En curso",
            d.horas_conectado,
        ]
        for d in datos.detalle
    ]
    return _responder(db, _empleado, "Reporte de Asistencia", headers, filas, formato, correo)


# --------------------------------------------------------------- inventario --


def _datos_inventario(db: Session, sucursal_id: int | None, umbral: int, desde: datetime, hasta: datetime) -> ReporteInventarioOut:
    stock_rows = db.execute(
        text(
            "SELECT prod.nombre, t.codigo, col.nombre, s.nombre, i.cantidad "
            "FROM inventario i JOIN producto prod ON prod.id=i.producto_id JOIN talla t ON t.id=i.talla_id "
            "JOIN color col ON col.id=i.color_id JOIN sucursal s ON s.id=i.sucursal_id "
            "WHERE (:sucursal_id IS NULL OR i.sucursal_id = :sucursal_id) "
            "ORDER BY i.cantidad ASC, prod.nombre ASC LIMIT 500"
        ),
        {"sucursal_id": sucursal_id},
    ).all()

    resumen_row = db.execute(
        text(
            "SELECT COUNT(DISTINCT i.producto_id), COALESCE(SUM(i.cantidad),0), "
            "COUNT(*) FILTER (WHERE i.cantidad <= :umbral) "
            "FROM inventario i WHERE (:sucursal_id IS NULL OR i.sucursal_id = :sucursal_id)"
        ),
        {"sucursal_id": sucursal_id, "umbral": umbral},
    ).one()

    movimientos = db.execute(
        text(
            "SELECT mi.fecha, mi.tipo, mi.cantidad, prod.nombre, t.codigo, col.nombre, s.nombre, "
            "emp_u.nombre, mi.documento_referencia "
            "FROM movimiento_inventario mi JOIN inventario i ON i.id = mi.inventario_id "
            "JOIN producto prod ON prod.id=i.producto_id JOIN talla t ON t.id=i.talla_id "
            "JOIN color col ON col.id=i.color_id JOIN sucursal s ON s.id=i.sucursal_id "
            "LEFT JOIN usuario emp_u ON emp_u.id = mi.empleado_id "
            "WHERE mi.fecha >= :desde AND mi.fecha < :hasta "
            "AND (:sucursal_id IS NULL OR i.sucursal_id = :sucursal_id) "
            "ORDER BY mi.fecha DESC LIMIT 300"
        ),
        {"desde": desde, "hasta": hasta, "sucursal_id": sucursal_id},
    ).all()

    stock = [
        StockFila(producto_nombre=r[0], talla_codigo=r[1], color_nombre=r[2], sucursal_nombre=r[3], cantidad=r[4])
        for r in stock_rows
    ]

    return ReporteInventarioOut(
        resumen=InventarioResumen(
            productos_distintos=int(resumen_row[0]), unidades_en_stock=int(resumen_row[1]),
            alertas_stock_bajo=int(resumen_row[2]),
        ),
        stock=stock,
        alertas=[f for f in stock if f.cantidad <= umbral],
        movimientos=[
            MovimientoFila(
                fecha=r[0], tipo=r[1], cantidad=r[2], producto_nombre=r[3], talla_codigo=r[4], color_nombre=r[5],
                sucursal_nombre=r[6], empleado_nombre=r[7], documento_referencia=r[8],
            )
            for r in movimientos
        ],
    )


@router.get("/inventario", response_model=ReporteInventarioOut)
def reporte_inventario(
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    umbral: int = Query(default=5, ge=0),
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU16")),
) -> ReporteInventarioOut:
    desde, hasta = _rango_fechas(fecha_desde, fecha_hasta)
    return _datos_inventario(db, sucursal_id, umbral, desde, hasta)


@router.get("/inventario/exportar")
def exportar_inventario(
    formato: str = Query(pattern="^(csv|excel|html|pdf)$"),
    # Con correo, el reporte se envia como adjunto en vez de descargarse.
    correo: str | None = Query(default=None, max_length=150, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    sucursal_id: int | None = Query(default=None),
    umbral: int = Query(default=5, ge=0),
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU16")),
) -> Response:
    desde, hasta = _rango_fechas(None, None)
    datos = _datos_inventario(db, sucursal_id, umbral, desde, hasta)
    headers = ["Producto", "Talla", "Color", "Sucursal", "Cantidad en stock"]
    filas = [[f.producto_nombre, f.talla_codigo, f.color_nombre, f.sucursal_nombre, f.cantidad] for f in datos.stock]
    return _responder(db, _empleado, "Reporte de Inventario", headers, filas, formato, correo)


# ---------------------------------------------------------------- productos --

_SQL_PRODUCTOS = """
SELECT prod.id, prod.nombre, cat.nombre, marca.nombre,
       SUM(il.cantidad) AS cantidad, SUM(il.cantidad * d.precio_unitario) AS total,
       ROUND(AVG(d.precio_unitario)::numeric, 2) AS precio_promedio
FROM (
    SELECT dvp.id, dvp.precio_unitario, vp.id AS venta_id FROM detalle_venta_presencial dvp
    JOIN venta_presencial vp ON vp.id = dvp.venta_presencial_id
    UNION ALL
    SELECT dvd.id, dvd.precio_unitario, vd.id AS venta_id FROM detalle_venta_digital dvd
    JOIN venta_digital vd ON vd.id = dvd.venta_digital_id
) d
JOIN item_linea il ON il.id = d.id
JOIN producto prod ON prod.id = il.producto_id
JOIN categoria cat ON cat.id = prod.categoria_id
JOIN marca ON marca.id = prod.marca_id
JOIN venta v ON v.id = d.venta_id
JOIN pago p ON p.venta_id = v.id
WHERE {where} AND p.estado = 'completado'
GROUP BY prod.id, prod.nombre, cat.nombre, marca.nombre
ORDER BY cantidad {orden}
"""


def _datos_productos(
    db: Session, desde: datetime, hasta: datetime, sucursal_id: int | None, tipo: str | None, orden: str
) -> ReporteProductosOut:
    params = {"desde": desde, "hasta": hasta, "sucursal_id": sucursal_id, "tipo": tipo, "metodo": None}
    orden_sql = "ASC" if orden == "menos" else "DESC"

    filas = db.execute(text(_SQL_PRODUCTOS.format(where=_WHERE_VENTAS, orden=orden_sql)), params).all()

    total_unidades = sum(int(f[4]) for f in filas)
    total_vendido = sum((_dec(f[5]) for f in filas), Decimal("0"))

    detalle = [
        ProductoVentaFila(
            producto_id=f[0],
            producto_nombre=f[1],
            categoria=f[2],
            marca=f[3],
            cantidad_vendida=int(f[4]),
            total_vendido=_dec(f[5]),
            precio_promedio=_dec(f[6]),
            porcentaje_unidades=round((int(f[4]) / total_unidades * 100), 1) if total_unidades else 0.0,
        )
        for f in filas
    ]

    return ReporteProductosOut(
        resumen=ProductosResumen(
            productos_distintos=len(detalle), total_unidades=total_unidades, total_vendido=total_vendido
        ),
        detalle=detalle,
    )


@router.get("/productos", response_model=ReporteProductosOut)
def reporte_productos(
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    tipo: str | None = Query(default=None),
    orden: str = Query(default="mas", pattern="^(mas|menos)$"),
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU16")),
) -> ReporteProductosOut:
    desde, hasta = _rango_fechas(fecha_desde, fecha_hasta)
    return _datos_productos(db, desde, hasta, sucursal_id, tipo, orden)


@router.get("/productos/exportar")
def exportar_productos(
    formato: str = Query(pattern="^(csv|excel|html|pdf)$"),
    # Con correo, el reporte se envia como adjunto en vez de descargarse.
    correo: str | None = Query(default=None, max_length=150, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    tipo: str | None = Query(default=None),
    orden: str = Query(default="mas", pattern="^(mas|menos)$"),
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU16")),
) -> Response:
    desde, hasta = _rango_fechas(fecha_desde, fecha_hasta)
    datos = _datos_productos(db, desde, hasta, sucursal_id, tipo, orden)
    headers = ["Producto", "Categoria", "Marca", "Unidades vendidas", "% del total", "Precio promedio", "Total vendido (Bs)"]
    filas = [
        [f.producto_nombre, f.categoria, f.marca, f.cantidad_vendida, f.porcentaje_unidades,
         float(f.precio_promedio), float(f.total_vendido)]
        for f in datos.detalle
    ]
    return _responder(db, _empleado, "Productos Mas Vendidos", headers, filas, formato, correo)


# ----------------------------------------------------------------- reservas --


def _datos_reservas(db: Session, desde: datetime, hasta: datetime, sucursal_id: int | None, estado: str | None) -> ReporteReservasOut:
    where = (
        "r.fecha_creacion >= :desde AND r.fecha_creacion < :hasta "
        "AND (:sucursal_id IS NULL OR r.sucursal_id = :sucursal_id) "
        "AND (:estado IS NULL OR r.estado = :estado)"
    )
    params = {"desde": desde, "hasta": hasta, "sucursal_id": sucursal_id, "estado": estado}

    conteos = db.execute(
        text(f"SELECT r.estado, COUNT(*) FROM reserva r WHERE {where} GROUP BY r.estado"), params
    ).all()
    mapa = {estado_: int(cant) for estado_, cant in conteos}
    total = sum(mapa.values())
    completadas = mapa.get("completada", 0)
    tasa = round((completadas / total * 100), 1) if total else 0.0

    detalle = db.execute(
        text(
            "SELECT r.id, r.fecha_creacion, u.nombre, s.nombre, r.horario_atencion, r.estado "
            "FROM reserva r JOIN sucursal s ON s.id=r.sucursal_id JOIN cliente c ON c.id=r.cliente_id "
            f"JOIN usuario u ON u.id=c.id WHERE {where} ORDER BY r.fecha_creacion DESC LIMIT 500"
        ),
        params,
    ).all()

    return ReporteReservasOut(
        resumen=ReservaResumen(
            total=total, pendientes=mapa.get("pendiente", 0), confirmadas=mapa.get("confirmada", 0),
            completadas=completadas, canceladas=mapa.get("cancelada", 0), vencidas=mapa.get("vencida", 0),
            tasa_conversion=tasa,
        ),
        detalle=[
            ReservaDetalleFila(
                id=r[0], fecha_creacion=r[1], cliente_nombre=r[2], sucursal_nombre=r[3], horario_atencion=r[4],
                estado=r[5],
            )
            for r in detalle
        ],
    )


@router.get("/reservas", response_model=ReporteReservasOut)
def reporte_reservas(
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    estado: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU16")),
) -> ReporteReservasOut:
    desde, hasta = _rango_fechas(fecha_desde, fecha_hasta)
    return _datos_reservas(db, desde, hasta, sucursal_id, estado)


@router.get("/reservas/exportar")
def exportar_reservas(
    formato: str = Query(pattern="^(csv|excel|html|pdf)$"),
    # Con correo, el reporte se envia como adjunto en vez de descargarse.
    correo: str | None = Query(default=None, max_length=150, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    estado: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU16")),
) -> Response:
    desde, hasta = _rango_fechas(fecha_desde, fecha_hasta)
    datos = _datos_reservas(db, desde, hasta, sucursal_id, estado)
    headers = ["ID", "Fecha de creacion", "Cliente", "Sucursal", "Horario de atencion", "Estado"]
    filas = [
        [
            d.id, d.fecha_creacion.strftime("%d/%m/%Y %H:%M"), d.cliente_nombre, d.sucursal_nombre,
            d.horario_atencion.strftime("%d/%m/%Y %H:%M"), d.estado,
        ]
        for d in datos.detalle
    ]
    return _responder(db, _empleado, "Reporte de Reservas", headers, filas, formato, correo)
