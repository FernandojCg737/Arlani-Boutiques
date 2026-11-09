from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permiso
from app.db.session import get_db
from app.models import Calificacion, Cliente, Usuario, Venta
from app.schemas.calificaciones import (
    CalificacionAdminOut,
    CalificacionIn,
    CalificacionOut,
    CalificacionPage,
    CalificacionResumen,
    DistribucionEstrellas,
)

router = APIRouter()

# CU20 "Reputacion y Calificaciones": el cliente califica con estrellas +
# comentario opcional una compra ya completada (una calificacion por venta,
# la columna venta_id es UNIQUE); el admin ve el promedio general, el
# desglose por estrellas y el listado completo con quien califico que
# venta -- eso deja cruzar una mala calificacion con el empleado/sucursal
# que atendio esa venta puntual.


def _get_cliente_o_403(db: Session, usuario: Usuario) -> Cliente:
    cliente = db.query(Cliente).filter(Cliente.id == usuario.id).first()
    if cliente is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo los clientes pueden calificar una compra.")
    return cliente


# ---------- Cliente ----------


@router.post("/venta/{venta_id}", response_model=CalificacionOut, status_code=status.HTTP_201_CREATED)
def calificar_venta(
    venta_id: int,
    payload: CalificacionIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> CalificacionOut:
    cliente = _get_cliente_o_403(db, usuario)

    venta = db.query(Venta).filter(Venta.id == venta_id, Venta.cliente_id == cliente.id).first()
    if venta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compra no encontrada.")
    if not venta.pago or venta.pago.estado != "completado":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se pueden calificar compras completadas.")

    existente = db.query(Calificacion).filter(Calificacion.venta_id == venta_id).first()
    if existente is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya calificaste esta compra.")

    calificacion = Calificacion(
        venta_id=venta_id, cliente_id=cliente.id, estrellas=payload.estrellas, comentario=payload.comentario
    )
    db.add(calificacion)
    db.commit()
    db.refresh(calificacion)

    return CalificacionOut(
        id=calificacion.id, venta_id=venta_id, estrellas=calificacion.estrellas,
        comentario=calificacion.comentario, fecha=calificacion.fecha,
    )


# ---------- Staff: Administrador (CU20) ----------


@router.get("", response_model=CalificacionPage)
def listar_calificaciones(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    estrellas: int | None = Query(default=None, ge=1, le=5),
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU20")),
) -> CalificacionPage:
    where = "1=1" if estrellas is None else "c.estrellas = :estrellas"
    params: dict = {"estrellas": estrellas} if estrellas is not None else {}

    # El resumen (promedio/total/distribucion) siempre es global -- el
    # filtro de estrellas solo acota la tabla de detalle, no la reputacion
    # general que se muestra arriba.
    resumen_row = db.execute(text("SELECT COALESCE(AVG(estrellas), 0), COUNT(*) FROM calificacion")).one()
    promedio, total = round(float(resumen_row[0]), 2), int(resumen_row[1])

    distribucion_rows = db.execute(
        text("SELECT estrellas, COUNT(*) FROM calificacion GROUP BY estrellas ORDER BY estrellas DESC")
    ).all()
    mapa_distribucion = {int(r[0]): int(r[1]) for r in distribucion_rows}
    distribucion = [
        DistribucionEstrellas(estrellas=e, cantidad=mapa_distribucion.get(e, 0)) for e in (5, 4, 3, 2, 1)
    ]

    total_filtrado = db.execute(text(f"SELECT COUNT(*) FROM calificacion c WHERE {where}"), params).scalar_one()

    rows = db.execute(
        text(
            f"""
            SELECT c.id, c.venta_id, c.estrellas, c.comentario, c.fecha,
                   u.nombre, u.email, s.nombre, emp_u.nombre, v.numero
            FROM calificacion c
            JOIN venta v ON v.id = c.venta_id
            JOIN sucursal s ON s.id = v.sucursal_id
            JOIN cliente cl ON cl.id = c.cliente_id
            JOIN usuario u ON u.id = cl.id
            LEFT JOIN venta_presencial vp ON vp.id = v.id
            LEFT JOIN usuario emp_u ON emp_u.id = vp.empleado_id
            WHERE {where}
            ORDER BY c.fecha DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    items = [
        CalificacionAdminOut(
            id=r[0], venta_id=r[1], venta_numero=r[9], estrellas=r[2], comentario=r[3], fecha=r[4],
            cliente_nombre=r[5], cliente_email=r[6], sucursal_nombre=r[7], empleado_nombre=r[8],
        )
        for r in rows
    ]

    return CalificacionPage(
        resumen=CalificacionResumen(promedio=promedio, total=total, distribucion=distribucion),
        items=items,
        total=int(total_filtrado),
        page=page,
        page_size=page_size,
    )
