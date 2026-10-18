from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.api.deps import (
    require_permiso,
    require_permiso_cliente,
    sucursal_restringida,
    verificar_acceso_sucursal,
)
from app.core.audit import log_bitacora
from app.db.session import get_db
from app.models import (
    Cliente,
    Color,
    DetalleReserva,
    Empleado,
    Inventario,
    MovimientoInventario,
    Producto,
    Reserva,
    Sucursal,
    Talla,
    Usuario,
)
from app.schemas.reservas import (
    DetalleReservaOut,
    DisponibilidadItem,
    ReservaAdminOut,
    ReservaCreate,
    ReservaEstadoUpdate,
    ReservaOut,
    ReservaPage,
)

router = APIRouter()


@router.get("/disponibilidad/{producto_id}", response_model=list[DisponibilidadItem])
def disponibilidad_producto(producto_id: int, db: Session = Depends(get_db)) -> list[DisponibilidadItem]:
    """Combinaciones talla/color/sucursal con stock real para este producto,
    para que el cliente elija una opcion valida al reservar (publico, no
    requiere sesion: es solo para armar el formulario)."""
    # Antes de mostrar stock, liberar lo que tengan retenido reservas ya
    # vencidas: si no, el producto figuraria agotado hasta que alguien abra
    # el listado de reservas.
    _vencer_reservas_expiradas(db)
    filas = (
        db.query(Inventario)
        .options(joinedload(Inventario.sucursal), joinedload(Inventario.talla), joinedload(Inventario.color))
        .filter(Inventario.producto_id == producto_id, Inventario.cantidad > 0)
        .all()
    )
    return [
        DisponibilidadItem(
            sucursal_id=i.sucursal_id,
            sucursal_nombre=i.sucursal.nombre,
            talla_id=i.talla_id,
            talla_codigo=i.talla.codigo,
            color_id=i.color_id,
            color_nombre=i.color.nombre,
            cantidad=i.cantidad,
        )
        for i in filas
    ]


def _to_detalle_out(d: DetalleReserva) -> DetalleReservaOut:
    return DetalleReservaOut(
        id=d.id,
        producto_id=d.producto_id,
        producto_nombre=d.producto.nombre,
        talla_codigo=d.talla.codigo,
        color_nombre=d.color.nombre,
        cantidad=d.cantidad,
    )


def _to_out(r: Reserva) -> ReservaOut:
    return ReservaOut(
        id=r.id,
        cliente_id=r.cliente_id,
        sucursal_id=r.sucursal_id,
        sucursal_nombre=r.sucursal.nombre,
        horario_atencion=r.horario_atencion,
        estado=r.estado,
        fecha_creacion=r.fecha_creacion,
        detalles=[_to_detalle_out(d) for d in r.detalles],
    )


def _to_admin_out(r: Reserva) -> ReservaAdminOut:
    return ReservaAdminOut(
        **_to_out(r).model_dump(),
        cliente_nombre=r.cliente.nombre,
        cliente_email=r.cliente.email,
    )


def _query_con_detalles(db: Session):
    return db.query(Reserva).options(
        joinedload(Reserva.sucursal),
        joinedload(Reserva.cliente),
        joinedload(Reserva.detalles).joinedload(DetalleReserva.producto),
        joinedload(Reserva.detalles).joinedload(DetalleReserva.talla),
        joinedload(Reserva.detalles).joinedload(DetalleReserva.color),
    )


def _get_reserva_or_404(db: Session, reserva_id: int) -> Reserva:
    reserva = _query_con_detalles(db).filter(Reserva.id == reserva_id).first()
    if reserva is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reserva no encontrada.")
    return reserva


def _vencer_reservas_expiradas(db: Session) -> None:
    """Se llama antes de listar reservas (barrido perezoso, sin necesitar
    un scheduler aparte): cualquier reserva pendiente/confirmada cuyo
    horario_atencion ya paso sin llegar a "completada" (pagada) se marca
    "vencida" y su stock retenido se devuelve solo (sp_vencer_reservas_expiradas)."""
    db.execute(text("SELECT sp_vencer_reservas_expiradas()"))
    db.commit()


def _mover_stock_reserva(db: Session, reserva: Reserva, tipo: str, empleado_id: int | None, motivo: str) -> None:
    """tipo="salida": retiene stock al reservar. tipo="entrada": lo libera
    (cancelacion o vencimiento). Cada item de la reserva mueve su propia
    fila de inventario, con su movimiento para dejar rastro en la
    auditoria (empleado_id es None cuando lo dispara el sistema, no una
    persona -- ver comentario en el modelo)."""
    signo = -1 if tipo == "salida" else 1
    for d in reserva.detalles:
        inventario = (
            db.query(Inventario)
            .filter(
                Inventario.producto_id == d.producto_id,
                Inventario.talla_id == d.talla_id,
                Inventario.color_id == d.color_id,
                Inventario.sucursal_id == reserva.sucursal_id,
            )
            .with_for_update()
            .first()
        )
        if inventario is None:
            continue
        inventario.cantidad += signo * d.cantidad
        db.add(
            MovimientoInventario(
                inventario_id=inventario.id,
                empleado_id=empleado_id,
                tipo=tipo,
                cantidad=d.cantidad,
                documento_referencia=f"Reserva #{reserva.id} ({motivo})",
            )
        )


# ---------- Cliente ----------


@router.post("", response_model=ReservaOut, status_code=status.HTTP_201_CREATED)
def crear_reserva(
    payload: ReservaCreate,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU10")),
) -> ReservaOut:
    cliente = db.query(Cliente).filter(Cliente.id == usuario.id).first()
    if cliente is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo los clientes pueden hacer reservas.")

    sucursal = db.query(Sucursal).filter(Sucursal.id == payload.sucursal_id).first()
    if sucursal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sucursal no encontrada.")

    _vencer_reservas_expiradas(db)

    # Al reservar se retiene el stock de una (no es solo un chequeo de
    # disponibilidad): mientras la reserva siga viva, esa cantidad no la
    # puede tomar otro cliente. Se libera sola si vence sin pagar, o al
    # cancelarla.
    for item in payload.items:
        producto = db.query(Producto).filter(Producto.id == item.producto_id).first()
        if producto is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Producto {item.producto_id} no encontrado.")
        talla = db.query(Talla).filter(Talla.id == item.talla_id).first()
        color = db.query(Color).filter(Color.id == item.color_id).first()
        if talla is None or color is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Talla o color no encontrado.")
        inventario = (
            db.query(Inventario)
            .filter(
                Inventario.producto_id == item.producto_id,
                Inventario.talla_id == item.talla_id,
                Inventario.color_id == item.color_id,
                Inventario.sucursal_id == payload.sucursal_id,
            )
            .with_for_update()
            .first()
        )
        if inventario is None or inventario.cantidad < item.cantidad:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f'No hay suficiente stock de "{producto.nombre}" ({talla.codigo}, {color.nombre}) en esa sucursal.',
            )

    reserva = Reserva(cliente_id=cliente.id, sucursal_id=payload.sucursal_id, horario_atencion=payload.horario_atencion)
    for item in payload.items:
        reserva.detalles.append(
            DetalleReserva(
                producto_id=item.producto_id,
                talla_id=item.talla_id,
                color_id=item.color_id,
                cantidad=item.cantidad,
            )
        )
    db.add(reserva)
    db.flush()  # asigna reserva.id / detalle.id antes de mover stock, sin cerrar la transaccion

    _mover_stock_reserva(db, reserva, "salida", None, "retenido al reservar")
    db.commit()

    reserva = _get_reserva_or_404(db, reserva.id)
    log_bitacora(db, usuario, "CREAR", "reserva", reserva.id, f"Reserva creada en {sucursal.nombre}", request)
    return _to_out(reserva)


@router.get("/mias", response_model=list[ReservaOut])
def mis_reservas(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU10")),
) -> list[ReservaOut]:
    _vencer_reservas_expiradas(db)
    reservas = (
        _query_con_detalles(db).filter(Reserva.cliente_id == usuario.id).order_by(Reserva.fecha_creacion.desc()).all()
    )
    return [_to_out(r) for r in reservas]


@router.post("/{reserva_id}/cancelar", response_model=ReservaOut)
def cancelar_mi_reserva(
    reserva_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU10")),
) -> ReservaOut:
    reserva = _get_reserva_or_404(db, reserva_id)
    if reserva.cliente_id != usuario.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta reserva no te pertenece.")
    if reserva.estado not in ("pendiente", "confirmada"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta reserva ya no se puede cancelar.")

    _mover_stock_reserva(db, reserva, "entrada", None, "liberado, cancelada por el cliente")
    reserva.estado = "cancelada"
    db.commit()
    log_bitacora(db, usuario, "ACTUALIZAR", "reserva", reserva.id, "Reserva cancelada por el cliente", request)

    reserva = _get_reserva_or_404(db, reserva_id)
    return _to_out(reserva)


# ---------- Admin (CU10) ----------


@router.get("", response_model=ReservaPage)
def listar_reservas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    estado: str | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU10", "CU11")),
) -> ReservaPage:
    _vencer_reservas_expiradas(db)

    query = _query_con_detalles(db)
    restringida = sucursal_restringida(usuario)
    if restringida is not None:
        query = query.filter(Reserva.sucursal_id == restringida)
    if estado:
        query = query.filter(Reserva.estado == estado)
    if sucursal_id:
        query = query.filter(Reserva.sucursal_id == sucursal_id)

    total = query.count()
    rows = (
        query.order_by(Reserva.horario_atencion.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ReservaPage(items=[_to_admin_out(r) for r in rows], total=total, page=page, page_size=page_size)


@router.put("/{reserva_id}/estado", response_model=ReservaAdminOut)
def cambiar_estado_reserva(
    reserva_id: int,
    payload: ReservaEstadoUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU10")),
) -> ReservaAdminOut:
    reserva = _get_reserva_or_404(db, reserva_id)
    verificar_acceso_sucursal(admin, reserva.sucursal_id)
    if reserva.estado not in ("pendiente", "confirmada"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta reserva ya esta cerrada.")

    empleado = db.query(Empleado).filter(Empleado.id == admin.id).first()
    if payload.estado == "cancelada":
        _mover_stock_reserva(
            db, reserva, "entrada", empleado.id if empleado else None, "liberado, cancelada por administracion"
        )

    reserva.estado = payload.estado
    db.commit()
    log_bitacora(db, admin, "ACTUALIZAR", "reserva", reserva.id, f"Reserva marcada como {payload.estado}", request)

    reserva = _get_reserva_or_404(db, reserva_id)
    return _to_admin_out(reserva)


@router.post("/{reserva_id}/completar", response_model=ReservaAdminOut)
def completar_reserva(
    reserva_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU10", "CU11")),
) -> ReservaAdminOut:
    """Marca la reserva como pagada/entregada -- "atender la reserva" en
    sucursal (CU11): el cliente paga en efectivo al recogerla, asi que esto
    genera una VentaPresencial + Pago igual que cualquier otra venta de
    mostrador, dejando registrado que empleado la atendio. El stock ya se
    retuvo al reservar (ver crear_reserva), asi que aca no se vuelve a
    tocar inventario."""
    reserva = _get_reserva_or_404(db, reserva_id)
    verificar_acceso_sucursal(admin, reserva.sucursal_id)
    if reserva.estado not in ("pendiente", "confirmada"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta reserva ya esta cerrada o vencida.")

    empleado = db.query(Empleado).filter(Empleado.id == admin.id).first()
    if empleado is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el personal de sucursal puede atender reservas.")

    result = db.execute(
        text("SELECT sp_atender_reserva(:reserva_id, :empleado_id)"),
        {"reserva_id": reserva_id, "empleado_id": empleado.id},
    )
    venta_id = result.scalar_one()
    db.commit()
    log_bitacora(db, admin, "ACTUALIZAR", "reserva", reserva.id, f"Reserva completada (pagada/entregada en efectivo, venta #{venta_id})", request)

    reserva = _get_reserva_or_404(db, reserva_id)
    return _to_admin_out(reserva)


@router.put("/{reserva_id}", response_model=ReservaAdminOut)
def editar_reserva(
    reserva_id: int,
    payload: ReservaCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU10")),
) -> ReservaAdminOut:
    """Edicion completa (sucursal, horario, prendas) para corregir una
    reserva mal cargada. Si estaba activa (pendiente/confirmada) se libera
    el stock que tenia retenido con los datos VIEJOS y se retiene de nuevo
    con los datos NUEVOS -- todo en la misma transaccion, asi que si el
    nuevo pedido no tiene stock suficiente no se llega a confirmar nada (ni
    siquiera se pierde el stock viejo). Si ya estaba cerrada
    (completada/cancelada/vencida) no se toca inventario: esa parte ya
    quedo resuelta, esto solo corrige los datos."""
    reserva = _get_reserva_or_404(db, reserva_id)
    verificar_acceso_sucursal(admin, reserva.sucursal_id)
    verificar_acceso_sucursal(admin, payload.sucursal_id)
    activa = reserva.estado in ("pendiente", "confirmada")

    if activa:
        _mover_stock_reserva(db, reserva, "entrada", None, "liberado, se va a editar la reserva")

    sucursal = db.query(Sucursal).filter(Sucursal.id == payload.sucursal_id).first()
    if sucursal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sucursal no encontrada.")

    reserva.sucursal_id = payload.sucursal_id
    reserva.horario_atencion = payload.horario_atencion
    reserva.detalles.clear()
    db.flush()
    for item in payload.items:
        reserva.detalles.append(
            DetalleReserva(
                producto_id=item.producto_id,
                talla_id=item.talla_id,
                color_id=item.color_id,
                cantidad=item.cantidad,
            )
        )
    db.flush()

    if activa:
        for item in payload.items:
            inventario = (
                db.query(Inventario)
                .filter(
                    Inventario.producto_id == item.producto_id,
                    Inventario.talla_id == item.talla_id,
                    Inventario.color_id == item.color_id,
                    Inventario.sucursal_id == payload.sucursal_id,
                )
                .with_for_update()
                .first()
            )
            if inventario is None or inventario.cantidad < item.cantidad:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "No hay suficiente stock para los nuevos datos de la reserva.",
                )
        _mover_stock_reserva(db, reserva, "salida", None, "retenido, se edito la reserva")

    db.commit()
    log_bitacora(db, admin, "ACTUALIZAR", "reserva", reserva.id, "Reserva editada por administracion", request)

    reserva = _get_reserva_or_404(db, reserva_id)
    return _to_admin_out(reserva)


@router.delete("/{reserva_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_reserva(
    reserva_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU10")),
) -> None:
    """Borra la reserva por completo (limpieza de historial). Si estaba
    activa, primero libera el stock que tenia retenido -- si no, esa
    cantidad quedaria retenida para siempre sin ninguna reserva real
    detras."""
    reserva = _get_reserva_or_404(db, reserva_id)
    verificar_acceso_sucursal(admin, reserva.sucursal_id)
    if reserva.estado in ("pendiente", "confirmada"):
        _mover_stock_reserva(db, reserva, "entrada", None, "liberado, la reserva se elimino")

    nombre_cliente = reserva.cliente.nombre
    db.delete(reserva)
    db.commit()
    log_bitacora(db, admin, "ELIMINAR", "reserva", reserva_id, f"Reserva de {nombre_cliente} eliminada", request)
