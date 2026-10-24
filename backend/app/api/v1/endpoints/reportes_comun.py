"""Reportes dinamicos y exportacion comun.

- /reportes/dinamico: el reporte que arma el usuario en el CU07 (de su tienda;
  el SuperAdministrador, de la tienda elegida).
- /reportes/exportar-tabla: cualquier tabla de reporte (estatica o dinamica,
  de la tienda o de la plataforma) en PDF, Excel, CSV o HTML, para descargar
  o enviar por correo.
- /reportes-saas/...: CU20 Gestionar reportes de la plataforma (SaaS).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import require_permiso, require_superadmin, sucursal_restringida
from app.core.email import nombre_marca
from app.core.rate_limit import verificar_limite
from app.core.reporte_dinamico import FUENTES_PLATAFORMA, FUENTES_TIENDA, catalogo, ejecutar, periodo_por_defecto
from app.core.reporte_export import Columna, Reporte, descargar, enviar
from app.db.session import get_db
from app.models import Usuario
from app.schemas.reportes_comun import DinamicoIn, ExportarTablaIn, TablaReporte

router = APIRouter()
saas_router = APIRouter()

MARCA_PLATAFORMA = "Arlani Boutiques"


def _empresa_scope(db: Session, usuario: Usuario) -> int | None:
    return usuario.empresa_id if usuario.empresa_id is not None else db.info.get("empresa_scope")


def _tabla(r: Reporte) -> TablaReporte:
    return TablaReporte(
        titulo=r.titulo, subtitulo=r.subtitulo,
        columnas=[{"clave": c.clave, "etiqueta": c.etiqueta, "tipo": c.tipo} for c in r.columnas],
        filas=r.filas, totales=r.totales,
    )


def _hoy(db: Session) -> date:
    return db.execute(text("SELECT (now() AT TIME ZONE 'America/La_Paz')::date")).scalar()


# ============================================================ tienda (CU07)


@router.get("/dinamico/fuentes")
def fuentes_tienda(_: Usuario = Depends(require_permiso("CU16"))) -> list[dict]:
    return catalogo(FUENTES_TIENDA)


@router.post("/dinamico", response_model=TablaReporte)
def dinamico_tienda(
    payload: DinamicoIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU16")),
) -> TablaReporte:
    empresa = _empresa_scope(db, usuario)
    if empresa is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Elige primero la tienda.")
    sucursal = sucursal_restringida(usuario) or payload.sucursal_id
    r = ejecutar(
        db, FUENTES_TIENDA, payload.fuente, payload.agrupar, payload.metricas, payload.desde, payload.hasta,
        sucursal_id=sucursal, marca=nombre_marca(db, empresa),
    )
    return _tabla(r)


@router.post("/exportar-tabla", response_model=None)
def exportar_tabla(
    payload: ExportarTablaIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU16")),
) -> Response | dict:
    """Descarga (sin correo) o envia por correo una tabla de reporte."""
    t = payload.tabla
    empresa = _empresa_scope(db, usuario)
    r = Reporte(
        t.titulo, [Columna(c.clave, c.etiqueta, c.tipo) for c in t.columnas], t.filas, subtitulo=t.subtitulo,
        totales=t.totales, marca=nombre_marca(db, empresa) if empresa else MARCA_PLATAFORMA,
    )
    if payload.correo:
        verificar_limite("reporte_correo", str(usuario.id), 10, 600)
        return enviar(r, payload.formato, payload.correo)
    return descargar(r, payload.formato)


# ======================================================= plataforma (CU20)


@saas_router.get("/dinamico/fuentes")
def fuentes_plataforma(_: Usuario = Depends(require_superadmin)) -> list[dict]:
    return catalogo(FUENTES_PLATAFORMA)


@saas_router.post("/dinamico", response_model=TablaReporte)
def dinamico_plataforma(
    payload: DinamicoIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin),
) -> TablaReporte:
    r = ejecutar(
        db, FUENTES_PLATAFORMA, payload.fuente, payload.agrupar, payload.metricas, payload.desde, payload.hasta,
        empresa_id=payload.empresa_id, marca=MARCA_PLATAFORMA,
    )
    return _tabla(r)


def _periodo(db: Session, desde: date | None, hasta: date | None) -> tuple[date, date]:
    defecto = periodo_por_defecto(_hoy(db))
    return desde or defecto[0], hasta or defecto[1]


_DIA = "(({col}) AT TIME ZONE 'UTC' AT TIME ZONE 'America/La_Paz')::date"


@saas_router.get("/resumen")
def resumen_saas(
    desde: date | None = None,
    hasta: date | None = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin),
) -> dict:
    """Lo que gana Arlani en el periodo (suscripciones + comisiones), MRR,
    tiendas por estado, ingresos por mes y por plan."""
    desde, hasta = _periodo(db, desde, hasta)
    p = {"d": desde, "h": hasta}
    plataforma = dict(db.execute(text("SELECT * FROM fn_resumen_plataforma()")).mappings().one())
    sus = db.execute(
        text(f"SELECT coalesce(sum(monto_bob), 0) AS total, count(*) AS pagos FROM pago_suscripcion "
             f"WHERE estado = 'completado' AND {_DIA.format(col='fecha')} BETWEEN :d AND :h"), p
    ).mappings().one()
    com = db.execute(
        text(f"SELECT coalesce(sum(monto_bob), 0) AS total, coalesce(sum(base_bob), 0) AS vendido, count(*) AS ventas "
             f"FROM cuenta_tienda_movimiento WHERE tipo = 'comision' AND {_DIA.format(col='fecha')} BETWEEN :d AND :h"), p
    ).mappings().one()
    gmv = db.execute(
        text(f"SELECT coalesce(sum(total), 0) AS total, count(*) AS ventas FROM venta "
             f"WHERE estado <> 'cancelada' AND {_DIA.format(col='fecha')} BETWEEN :d AND :h"), p
    ).mappings().one()
    por_mes = db.execute(
        text(
            f"""WITH meses AS (SELECT to_char(m, 'YYYY-MM') AS mes FROM generate_series(date_trunc('month', CAST(:d AS date)),
                                     date_trunc('month', CAST(:h AS date)), interval '1 month') m),
                     s AS (SELECT to_char({_DIA.format(col='fecha')}, 'YYYY-MM') AS mes, sum(monto_bob) AS v FROM pago_suscripcion
                           WHERE estado = 'completado' AND {_DIA.format(col='fecha')} BETWEEN :d AND :h GROUP BY 1),
                     c AS (SELECT to_char({_DIA.format(col='fecha')}, 'YYYY-MM') AS mes, sum(monto_bob) AS v FROM cuenta_tienda_movimiento
                           WHERE tipo = 'comision' AND {_DIA.format(col='fecha')} BETWEEN :d AND :h GROUP BY 1)
                SELECT meses.mes, coalesce(s.v, 0) AS suscripciones, coalesce(c.v, 0) AS comisiones,
                       coalesce(s.v, 0) + coalesce(c.v, 0) AS total
                FROM meses LEFT JOIN s USING (mes) LEFT JOIN c USING (mes) ORDER BY meses.mes"""
        ), p,
    ).mappings().all()
    por_plan = db.execute(
        text(
            """SELECT pl.nombre AS plan, count(su.id) AS tiendas,
                      coalesce(sum(fn_mrr_suscripcion(su.periodo, su.monto)), 0) AS mrr
               FROM plan_suscripcion pl LEFT JOIN suscripcion su ON su.plan_id = pl.id AND su.estado = 'activa'
               GROUP BY pl.id, pl.nombre, pl.orden ORDER BY pl.orden"""
        )
    ).mappings().all()
    return {
        "desde": desde, "hasta": hasta,
        "ingreso_total": sus["total"] + com["total"], "ingreso_suscripciones": sus["total"], "pagos_suscripcion": sus["pagos"],
        "ingreso_comisiones": com["total"], "ventas_con_comision": com["ventas"], "gmv": gmv["total"], "ventas_tiendas": gmv["ventas"],
        "mrr": plataforma["mrr"], "empresas_activas": plataforma["empresas_activas"], "empresas_prueba": plataforma["empresas_prueba"],
        "empresas_suspendidas": plataforma["empresas_suspendidas"], "empresas_total": plataforma["empresas_total"],
        "por_mes": [dict(f) for f in por_mes], "por_plan": [dict(f) for f in por_plan],
    }


TABLAS_SAAS = {
    "suscripciones": "Pagos de suscripción",
    "comisiones": "Comisiones por tienda",
    "tiendas": "Ranking de tiendas",
    "planes": "Ingresos por plan",
    "vencimientos": "Suscripciones por vencer",
}


@saas_router.get("/tabla/{tipo}", response_model=TablaReporte)
def tabla_saas(
    tipo: str,
    desde: date | None = None,
    hasta: date | None = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin),
) -> TablaReporte:
    """Reportes fijos de la plataforma (CU20)."""
    if tipo not in TABLAS_SAAS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reporte no encontrado.")
    desde, hasta = _periodo(db, desde, hasta)
    p = {"d": desde, "h": hasta}
    sub = f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}"
    dia = _DIA.format(col="{c}")
    if tipo == "suscripciones":
        filas = db.execute(text(
            f"""SELECT to_char(ps.fecha - interval '4 hours', 'DD/MM/YYYY HH24:MI') AS fecha, e.nombre AS tienda,
                       coalesce(pl.nombre, '-') AS plan, coalesce(su.periodo, '-') AS periodo, ps.metodo,
                       ps.monto_bob, ps.monto_usd
                FROM pago_suscripcion ps JOIN empresa e ON e.id = ps.empresa_id
                LEFT JOIN suscripcion su ON su.id = ps.suscripcion_id LEFT JOIN plan_suscripcion pl ON pl.id = su.plan_id
                WHERE ps.estado = 'completado' AND {dia.format(c='ps.fecha')} BETWEEN :d AND :h ORDER BY ps.fecha DESC"""), p).mappings().all()
        cols = [Columna("fecha", "Fecha"), Columna("tienda", "Tienda"), Columna("plan", "Plan"), Columna("periodo", "Periodo"),
                Columna("metodo", "Método"), Columna("monto_bob", "Monto (Bs)", "moneda"), Columna("monto_usd", "Monto (US$)", "moneda")]
        tot = {"fecha": "Total", "monto_bob": sum(f["monto_bob"] or 0 for f in filas), "monto_usd": sum(f["monto_usd"] or 0 for f in filas)}
    elif tipo == "comisiones":
        filas = db.execute(text(
            f"""SELECT e.nombre AS tienda, coalesce(pl.nombre, '-') AS plan, coalesce(pl.comision_pct, 0) AS porcentaje,
                       count(m.id) AS ventas, coalesce(sum(m.base_bob), 0) AS vendido, coalesce(sum(m.monto_bob), 0) AS comision,
                       coalesce((SELECT sum(x.monto_bob) FROM cuenta_tienda_movimiento x WHERE x.empresa_id = e.id), 0) AS saldo
                FROM empresa e
                LEFT JOIN suscripcion su ON su.empresa_id = e.id AND su.estado = 'activa'
                LEFT JOIN plan_suscripcion pl ON pl.id = su.plan_id
                LEFT JOIN cuenta_tienda_movimiento m ON m.empresa_id = e.id AND m.tipo = 'comision'
                     AND {dia.format(c='m.fecha')} BETWEEN :d AND :h
                GROUP BY e.id, e.nombre, pl.nombre, pl.comision_pct ORDER BY comision DESC, e.nombre"""), p).mappings().all()
        cols = [Columna("tienda", "Tienda"), Columna("plan", "Plan"), Columna("porcentaje", "Comisión %", "numero"),
                Columna("ventas", "Ventas", "numero"), Columna("vendido", "Vendido (Bs)", "moneda"),
                Columna("comision", "Comisión (Bs)", "moneda"), Columna("saldo", "Saldo por cobrar (Bs)", "moneda")]
        tot = {"tienda": "Total", **{k: sum(f[k] or 0 for f in filas) for k in ("ventas", "vendido", "comision", "saldo")}}
    elif tipo == "tiendas":
        filas = db.execute(text(
            f"""SELECT e.nombre AS tienda, coalesce(pl.nombre, 'Sin plan') AS plan, e.estado,
                       (SELECT count(*) FROM venta v JOIN sucursal s ON s.id = v.sucursal_id WHERE s.empresa_id = e.id
                          AND v.estado <> 'cancelada' AND {dia.format(c='v.fecha')} BETWEEN :d AND :h) AS ventas,
                       (SELECT coalesce(sum(v.total), 0) FROM venta v JOIN sucursal s ON s.id = v.sucursal_id WHERE s.empresa_id = e.id
                          AND v.estado <> 'cancelada' AND {dia.format(c='v.fecha')} BETWEEN :d AND :h) AS gmv,
                       (SELECT coalesce(sum(m.monto_bob), 0) FROM cuenta_tienda_movimiento m WHERE m.empresa_id = e.id
                          AND m.tipo = 'comision' AND {dia.format(c='m.fecha')} BETWEEN :d AND :h) AS comision,
                       (SELECT coalesce(sum(ps.monto_bob), 0) FROM pago_suscripcion ps WHERE ps.empresa_id = e.id
                          AND ps.estado = 'completado' AND {dia.format(c='ps.fecha')} BETWEEN :d AND :h) AS suscripcion
                FROM empresa e LEFT JOIN suscripcion su ON su.empresa_id = e.id AND su.estado = 'activa'
                LEFT JOIN plan_suscripcion pl ON pl.id = su.plan_id ORDER BY gmv DESC, e.nombre"""), p).mappings().all()
        filas = [{**f, "aporte": (f["comision"] or 0) + (f["suscripcion"] or 0)} for f in filas]
        cols = [Columna("tienda", "Tienda"), Columna("plan", "Plan"), Columna("estado", "Estado"), Columna("ventas", "Ventas", "numero"),
                Columna("gmv", "Vendido (Bs)", "moneda"), Columna("comision", "Comisión (Bs)", "moneda"),
                Columna("suscripcion", "Suscripción (Bs)", "moneda"), Columna("aporte", "Aporte a Arlani (Bs)", "moneda")]
        tot = {"tienda": "Total", **{k: sum(f[k] or 0 for f in filas) for k in ("ventas", "gmv", "comision", "suscripcion", "aporte")}}
    elif tipo == "planes":
        filas = db.execute(text(
            f"""SELECT pl.nombre AS plan, pl.precio_mensual, pl.comision_pct,
                       count(DISTINCT su.empresa_id) FILTER (WHERE su.estado = 'activa') AS tiendas,
                       coalesce(sum(fn_mrr_suscripcion(su.periodo, su.monto)) FILTER (WHERE su.estado = 'activa'), 0) AS mrr,
                       (SELECT coalesce(sum(ps.monto_bob), 0) FROM pago_suscripcion ps JOIN suscripcion s2 ON s2.id = ps.suscripcion_id
                          WHERE s2.plan_id = pl.id AND ps.estado = 'completado' AND {dia.format(c='ps.fecha')} BETWEEN :d AND :h) AS cobrado
                FROM plan_suscripcion pl LEFT JOIN suscripcion su ON su.plan_id = pl.id
                GROUP BY pl.id ORDER BY pl.orden"""), p).mappings().all()
        cols = [Columna("plan", "Plan"), Columna("precio_mensual", "Precio mensual (Bs)", "moneda"),
                Columna("comision_pct", "Comisión %", "numero"), Columna("tiendas", "Tiendas activas", "numero"),
                Columna("mrr", "Ingreso mensual (Bs)", "moneda"), Columna("cobrado", "Cobrado en el periodo (Bs)", "moneda")]
        tot = {"plan": "Total", **{k: sum(f[k] or 0 for f in filas) for k in ("tiendas", "mrr", "cobrado")}}
    else:
        filas = db.execute(text(
            """SELECT e.nombre AS tienda, pl.nombre AS plan, su.periodo, to_char(su.fecha_fin, 'DD/MM/YYYY') AS vence,
                      (su.fecha_fin - (now() AT TIME ZONE 'America/La_Paz')::date) AS dias, su.monto,
                      coalesce(e.email_contacto, '-') AS contacto
               FROM suscripcion su JOIN empresa e ON e.id = su.empresa_id JOIN plan_suscripcion pl ON pl.id = su.plan_id
               WHERE su.estado = 'activa' AND su.fecha_fin IS NOT NULL
                 AND su.fecha_fin <= (now() AT TIME ZONE 'America/La_Paz')::date + 30
               ORDER BY su.fecha_fin""")).mappings().all()
        cols = [Columna("tienda", "Tienda"), Columna("plan", "Plan"), Columna("periodo", "Periodo"), Columna("vence", "Vence"),
                Columna("dias", "Días que faltan", "numero"), Columna("monto", "Monto a renovar (Bs)", "moneda"),
                Columna("contacto", "Contacto")]
        tot = {"tienda": "Total", "monto": sum(f["monto"] or 0 for f in filas)}
        sub = "Vencen en los próximos 30 días (o ya vencieron)"
    return _tabla(Reporte(TABLAS_SAAS[tipo], cols, [dict(f) for f in filas], subtitulo=sub, totales=tot, marca=MARCA_PLATAFORMA))
