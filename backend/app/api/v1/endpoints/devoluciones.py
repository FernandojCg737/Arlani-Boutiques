"""CU11: Devoluciones -- flujo de devolucion total o parcial de una venta
ya pagada. El empleado registra la devolucion, y al completarla se reingresa
el stock al inventario y se actualiza el estado de la venta."""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.api.deps import (
    require_encargado_o_admin,
    require_permiso,
    require_permiso_cliente,
    sucursal_restringida,
    verificar_acceso_sucursal,
)
from app.core.audit import log_bitacora
from app.core.aviso_cliente import programar_correo
from app.db.session import get_db
from app.models import (
    Cliente,
    DetalleVentaDigital,
    DetalleVentaPresencial,
    Empleado,
    Inventario,
    ItemLinea,
    Notificacion,
    Usuario,
    Venta,
    VentaDigital,
    VentaPresencial,
)
from app.models.p4_ventas import DetalleDevolucion, Devolucion
from app.schemas.devoluciones import (
    DetalleDevolucionOut,
    DevolucionAdminOut,
    DevolucionClienteOut,
    DevolucionCreate,
    DevolucionOut,
    DevolucionRechazoIn,
)

router = APIRouter()

# Plazo maximo para que el CLIENTE solicite una devolucion (regla del CU11).
PLAZO_DEVOLUCION_HORAS = 24.0
# Estados que bloquean abrir otra devolucion sobre la misma venta.
ESTADOS_DEVOLUCION_VIGENTE = ("solicitada", "aprobada", "completada")


# ---------------------------------------------------------------- helpers --


def _reembolsar_paypal(db: Session, venta_id: int, monto_bob: Decimal) -> None:
    """Devuelve `monto_bob` (en US$ al cambio oficial) por PayPal si la venta
    se cobro con PayPal y se guardo su captura. Si PayPal lo rechaza, la
    devolucion no se completa."""
    from app.api.v1.endpoints.ventas import _a_usd, _paypal_de_tienda
    from app.core.paypal import reembolsar_captura

    fila = db.execute(
        text(
            "SELECT p.metodo, p.liquidacion_id, t.captura_id, s.empresa_id FROM pago p "
            "JOIN venta v ON v.id = p.venta_id JOIN sucursal s ON s.id = v.sucursal_id "
            "LEFT JOIN transaccion t ON t.pago_id = p.id WHERE p.venta_id = :v"
        ),
        {"v": venta_id},
    ).mappings().first()
    if fila is None or fila["metodo"] != "paypal" or not fila["captura_id"]:
        return
    cuenta = None if fila["liquidacion_id"] else _paypal_de_tienda(db, fila["empresa_id"])[1]
    monto_usd, _ = _a_usd(db, monto_bob)
    if not reembolsar_captura(fila["captura_id"], cuenta, monto_usd):
        db.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "PayPal no aceptó el reembolso. Inténtalo de nuevo o elige otro método de reembolso.",
        )

def _get_empleado_o_403(db: Session, usuario: Usuario) -> Empleado:
    empleado = db.query(Empleado).filter(Empleado.id == usuario.id).first()
    if empleado is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el personal de sucursal puede hacer esto.")
    return empleado


def _get_cliente_o_403(db: Session, usuario: Usuario) -> Cliente:
    cliente = db.query(Cliente).filter(Cliente.id == usuario.id).first()
    if cliente is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo los clientes pueden realizar esta accion.")
    return cliente


def _query_devolucion(db: Session):
    return db.query(Devolucion).options(
        joinedload(Devolucion.venta).joinedload(Venta.sucursal),
        joinedload(Devolucion.venta).joinedload(Venta.cliente),
        joinedload(Devolucion.venta).joinedload(Venta.pago),
        joinedload(Devolucion.empleado),
        joinedload(Devolucion.detalles).joinedload(DetalleDevolucion.item_linea).joinedload(ItemLinea.producto),
        joinedload(Devolucion.detalles).joinedload(DetalleDevolucion.item_linea).joinedload(ItemLinea.talla),
        joinedload(Devolucion.detalles).joinedload(DetalleDevolucion.item_linea).joinedload(ItemLinea.color),
    )


def _get_devolucion_bloqueada(db: Session, devolucion_id: int) -> Devolucion:
    """Bloquea la fila (FOR UPDATE) antes de leerla: si dos empleados
    completan/rechazan la misma devolucion a la vez, el segundo espera y ve
    el estado ya actualizado -- en vez de reingresar el stock dos veces.
    El lock va en una consulta aparte porque Postgres no permite FOR UPDATE
    sobre el lado opcional de los LEFT JOIN que arma el joinedload."""
    bloqueada = db.query(Devolucion.id).filter(Devolucion.id == devolucion_id).with_for_update().first()
    if bloqueada is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Devolucion no encontrada.")
    return _query_devolucion(db).filter(Devolucion.id == devolucion_id).populate_existing().first()


def _query_venta_con_detalles(db: Session):
    return db.query(Venta).options(
        joinedload(Venta.sucursal),
        joinedload(Venta.cliente),
        joinedload(Venta.pago),
        joinedload(Venta.devoluciones),
        joinedload(VentaDigital.detalles).joinedload(DetalleVentaDigital.producto),
        joinedload(VentaDigital.detalles).joinedload(DetalleVentaDigital.talla),
        joinedload(VentaDigital.detalles).joinedload(DetalleVentaDigital.color),
        joinedload(VentaPresencial.detalles).joinedload(DetalleVentaPresencial.producto),
        joinedload(VentaPresencial.detalles).joinedload(DetalleVentaPresencial.talla),
        joinedload(VentaPresencial.detalles).joinedload(DetalleVentaPresencial.color),
    )


def _precio_unitario_desde_item(db: Session, item_linea_id: int) -> Decimal:
    """Busca el precio unitario del item en detalle_venta_presencial o
    detalle_venta_digital."""
    row = db.execute(
        text(
            "SELECT COALESCE("
            "  (SELECT precio_unitario FROM detalle_venta_presencial WHERE id = :id),"
            "  (SELECT precio_unitario FROM detalle_venta_digital WHERE id = :id),"
            "  0"
            ")"
        ),
        {"id": item_linea_id},
    ).scalar()
    return Decimal(str(row))


def _armar_detalles(db: Session, venta: Venta, payload: DevolucionCreate) -> tuple[Decimal, list[DetalleDevolucion]]:
    """Valida los items contra la venta y calcula el monto a reembolsar.
    Compartido por la solicitud del cliente y el registro del staff (antes
    estaba duplicado en ambos endpoints)."""
    detalles_venta = getattr(venta, "detalles", [])
    por_id = {d.id: d for d in detalles_venta}

    monto_total = Decimal("0")
    detalles_devolucion = []
    for item_in in payload.items:
        detalle_original = por_id.get(item_in.item_linea_id)
        if detalle_original is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"El item {item_in.item_linea_id} no pertenece a esta compra.",
            )
        if item_in.cantidad_devuelta > detalle_original.cantidad:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f'No puedes devolver {item_in.cantidad_devuelta} unidades de "{detalle_original.producto.nombre}" '
                f"({detalle_original.talla.codigo}, {detalle_original.color.nombre}) — "
                f"solo se compraron {detalle_original.cantidad}.",
            )
        precio = _precio_unitario_desde_item(db, item_in.item_linea_id)
        monto_total += precio * item_in.cantidad_devuelta
        detalles_devolucion.append(
            DetalleDevolucion(
                item_linea_id=item_in.item_linea_id,
                cantidad_devuelta=item_in.cantidad_devuelta,
            )
        )

    if payload.tipo == "total":
        pedidos = {i.item_linea_id: i.cantidad_devuelta for i in payload.items}
        if any(pedidos.get(d.id) != d.cantidad for d in detalles_venta):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Una devolucion total debe incluir todos los items con sus cantidades completas.",
            )

    return monto_total, detalles_devolucion


def _rechazar_si_hay_devolucion_vigente(venta: Venta) -> None:
    vigentes = [d for d in venta.devoluciones if d.estado in ESTADOS_DEVOLUCION_VIGENTE]
    if vigentes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Esta compra ya cuenta con una devolucion en estado '{vigentes[-1].estado}'.",
        )


def _rechazar_si_prendas_ya_solicitadas(db: Session, payload: DevolucionCreate, incluir_devoluciones: bool = True) -> None:
    """Politica: una sola solicitud por prenda. Una prenda que ya tuvo un
    cambio (aunque se haya rechazado) o una devolucion no admite otra. El
    personal (incluir_devoluciones=False) puede registrar una devolucion de
    una prenda cuya solicitud se rechazo (ej. defecto), pero nunca de una
    prenda que se cambio."""
    ids = [i.item_linea_id for i in payload.items]
    if db.execute(
        text("SELECT 1 FROM cambio_prenda WHERE item_linea_id = ANY(:ids) AND estado <> 'cancelado' LIMIT 1"),
        {"ids": ids},
    ).first():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Esa prenda ya tuvo una solicitud de cambio: no admite devolución."
        )
    if incluir_devoluciones and db.execute(
        text("SELECT 1 FROM detalle_devolucion WHERE item_linea_id = ANY(:ids) LIMIT 1"), {"ids": ids}
    ).first():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Ya pediste la devolución de esa prenda: solo se permite una solicitud."
        )


def _inventario_de(db: Session, item: ItemLinea, sucursal_id: int) -> Inventario | None:
    return (
        db.query(Inventario)
        .filter(
            Inventario.producto_id == item.producto_id,
            Inventario.talla_id == item.talla_id,
            Inventario.color_id == item.color_id,
            Inventario.sucursal_id == sucursal_id,
        )
        .with_for_update()
        .first()
    )


def _registrar_movimiento(db: Session, inventario_id: int, empleado_id: int, tipo: str, cantidad: int, doc: str) -> None:
    db.execute(
        text(
            "INSERT INTO movimiento_inventario "
            "(inventario_id, empleado_id, tipo, cantidad, fecha, documento_referencia) "
            "VALUES (:inv_id, :emp_id, :tipo, :cant, now(), :doc)"
        ),
        {"inv_id": inventario_id, "emp_id": empleado_id, "tipo": tipo, "cant": cantidad, "doc": doc},
    )


# Avisos que ademas llegan por correo (la resolucion de la tienda).
_TITULOS_CORREO = {
    "devolucion_completada": "Tu devolución fue aprobada",
    "devolucion_rechazada": "Tu devolución fue rechazada",
}


def _notificar(db: Session, cliente_id: int, tipo_evento: str, mensaje: str, devolucion_id: int) -> None:
    titulo = _TITULOS_CORREO.get(tipo_evento)
    if titulo:
        empresa_id = db.execute(
            text(
                "SELECT s.empresa_id FROM devolucion d JOIN venta v ON v.id = d.venta_id "
                "JOIN sucursal s ON s.id = v.sucursal_id WHERE d.id = :id"
            ),
            {"id": devolucion_id},
        ).scalar()
        programar_correo(db, cliente_id, empresa_id, titulo, mensaje)
    db.add(
        Notificacion(
            cliente_id=cliente_id,
            canal="sistema",
            tipo_evento=tipo_evento,
            mensaje=mensaje,
            estado="enviada",
            leida=False,
            entidad_tipo="devolucion",
            entidad_id=devolucion_id,
        )
    )


def _to_detalle_out(d: DetalleDevolucion, db: Session) -> DetalleDevolucionOut:
    item = d.item_linea
    return DetalleDevolucionOut(
        id=d.id,
        item_linea_id=d.item_linea_id,
        producto_nombre=item.producto.nombre,
        talla_codigo=item.talla.codigo,
        color_nombre=item.color.nombre,
        cantidad_devuelta=d.cantidad_devuelta,
        precio_unitario=_precio_unitario_desde_item(db, d.item_linea_id),
    )


def _to_out(dev: Devolucion, db: Session) -> DevolucionOut:
    return DevolucionOut(
        id=dev.id,
        venta_id=dev.venta_id,
        empleado_nombre=dev.empleado.nombre if dev.empleado else None,
        motivo=dev.motivo,
        tipo=dev.tipo,
        monto_reembolso=dev.monto_reembolso,
        metodo_reembolso=dev.metodo_reembolso,
        estado=dev.estado,
        fecha_solicitud=dev.fecha_solicitud,
        fecha_resolucion=dev.fecha_resolucion,
        observaciones=dev.observaciones,
        motivo_rechazo=dev.motivo_rechazo,
        detalles=[_to_detalle_out(d, db) for d in dev.detalles],
    )


def _to_admin_out(dev: Devolucion, db: Session) -> DevolucionAdminOut:
    return DevolucionAdminOut(
        **_to_out(dev, db).model_dump(),
        cliente_nombre=dev.venta.cliente.nombre,
        cliente_email=dev.venta.cliente.email,
        venta_total=dev.venta.total,
        venta_fecha=dev.venta.fecha,
        sucursal_nombre=dev.venta.sucursal.nombre,
    )


# --------------------------------------------------------------- endpoints --


@router.get("", response_model=list[DevolucionAdminOut])
def listar_devoluciones(
    estado: str | None = Query(default=None),
    venta_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    empleado: Usuario = Depends(require_permiso("CU11")),
) -> list[DevolucionAdminOut]:
    query = _query_devolucion(db)
    restringida = sucursal_restringida(empleado)
    if restringida is not None:
        query = query.join(Venta, Venta.id == Devolucion.venta_id).filter(Venta.sucursal_id == restringida)
    if estado:
        query = query.filter(Devolucion.estado == estado)
    if venta_id:
        query = query.filter(Devolucion.venta_id == venta_id)
    devoluciones = query.order_by(Devolucion.fecha_solicitud.desc()).all()
    return [_to_admin_out(d, db) for d in devoluciones]


@router.get("/mias", response_model=list[DevolucionClienteOut])
def mis_devoluciones(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> list[DevolucionClienteOut]:
    """Devoluciones del cliente (Mi cuenta > Mis Devoluciones)."""
    cliente = _get_cliente_o_403(db, usuario)
    devoluciones = (
        _query_devolucion(db)
        .join(Venta, Venta.id == Devolucion.venta_id)
        .filter(Venta.cliente_id == cliente.id)
        .order_by(Devolucion.fecha_solicitud.desc())
        .all()
    )
    return [
        DevolucionClienteOut(
            **_to_out(d, db).model_dump(),
            tienda_nombre=d.venta.sucursal.empresa.nombre if d.venta.sucursal.empresa else "",
            sucursal_nombre=d.venta.sucursal.nombre,
            venta_fecha=d.venta.fecha,
        )
        for d in devoluciones
    ]


@router.get("/{devolucion_id}", response_model=DevolucionAdminOut)
def obtener_devolucion(
    devolucion_id: int,
    db: Session = Depends(get_db),
    empleado: Usuario = Depends(require_permiso("CU11")),
) -> DevolucionAdminOut:
    dev = _query_devolucion(db).filter(Devolucion.id == devolucion_id).first()
    if dev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Devolucion no encontrada.")
    verificar_acceso_sucursal(empleado, dev.venta.sucursal_id)
    return _to_admin_out(dev, db)


@router.post("/solicitar/{venta_id}", response_model=DevolucionOut, status_code=status.HTTP_201_CREATED)
def solicitar_devolucion_cliente(
    venta_id: int,
    payload: DevolucionCreate,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> DevolucionOut:
    """CU11: Un cliente solicita la devolucion de una compra suya pagada.
    Restriccion obligatoria: solo es valida dentro de las 24 horas a partir
    de realizada la compra."""
    cliente = _get_cliente_o_403(db, usuario)

    venta = _query_venta_con_detalles(db).filter(Venta.id == venta_id, Venta.cliente_id == cliente.id).first()
    if venta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compra no encontrada.")

    if venta.estado != "pagada":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se pueden solicitar devoluciones de compras pagadas.")

    horas_transcurridas = (datetime.utcnow() - venta.fecha).total_seconds() / 3600.0 if venta.fecha else 999.0
    if horas_transcurridas > PLAZO_DEVOLUCION_HORAS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "El plazo maximo de 24 horas para solicitar una devolucion ha vencido.",
        )

    _rechazar_si_hay_devolucion_vigente(venta)
    _rechazar_si_prendas_ya_solicitadas(db, payload)
    monto_total, detalles_devolucion = _armar_detalles(db, venta, payload)

    devolucion = Devolucion(
        venta_id=venta_id,
        empleado_id=None,
        motivo=payload.motivo,
        tipo=payload.tipo,
        monto_reembolso=monto_total,
        metodo_reembolso=payload.metodo_reembolso,
        estado="solicitada",
        observaciones=payload.observaciones,
        detalles=detalles_devolucion,
    )
    db.add(devolucion)
    db.flush()
    _notificar(
        db,
        cliente.id,
        "devolucion_solicitada",
        f"Has solicitado una devolucion {payload.tipo} para tu compra #{venta_id} "
        f"por {monto_total} Bs. Nuestro personal la revisara a la brevedad.",
        devolucion.id,
    )
    db.commit()

    log_bitacora(
        db, usuario, "CREAR", "devolucion", devolucion.id,
        f"Cliente #{cliente.id} solicito devolucion {payload.tipo} para compra #{venta_id} por {monto_total} Bs (plazo 24h)",
        request,
    )

    dev = _query_devolucion(db).filter(Devolucion.id == devolucion.id).first()
    return _to_out(dev, db)


@router.post("/{venta_id}", response_model=DevolucionAdminOut, status_code=status.HTTP_201_CREATED)
def registrar_devolucion(
    venta_id: int,
    payload: DevolucionCreate,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> DevolucionAdminOut:
    """Registra una devolucion para una venta pagada. El empleado selecciona
    los items y cantidades a devolver. La devolucion queda en estado
    'solicitada' hasta que se complete (se aprueba y reingresa el stock en
    un solo paso, ver completar_devolucion). El plazo de 24h es una regla
    para la solicitud del cliente; el staff puede registrar una fuera de
    plazo (ej. producto con defecto), pero tampoco puede abrir una segunda
    devolucion sobre la misma venta."""
    empleado = _get_empleado_o_403(db, usuario)

    venta = _query_venta_con_detalles(db).filter(Venta.id == venta_id).first()
    if venta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venta no encontrada.")
    verificar_acceso_sucursal(usuario, venta.sucursal_id)
    if venta.estado != "pagada":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se pueden devolver ventas pagadas.")

    _rechazar_si_hay_devolucion_vigente(venta)
    _rechazar_si_prendas_ya_solicitadas(db, payload, incluir_devoluciones=False)
    monto_total, detalles_devolucion = _armar_detalles(db, venta, payload)

    devolucion = Devolucion(
        venta_id=venta_id,
        empleado_id=empleado.id,
        motivo=payload.motivo,
        tipo=payload.tipo,
        monto_reembolso=monto_total,
        metodo_reembolso=payload.metodo_reembolso,
        estado="solicitada",
        observaciones=payload.observaciones,
        detalles=detalles_devolucion,
    )
    db.add(devolucion)
    db.flush()
    _notificar(
        db,
        venta.cliente_id,
        "devolucion_registrada",
        f"Se ha registrado una devolucion {payload.tipo} para tu compra #{venta_id} "
        f"por {monto_total} Bs. Te avisaremos cuando se procese.",
        devolucion.id,
    )
    db.commit()

    log_bitacora(
        db, usuario, "CREAR", "devolucion", devolucion.id,
        f"Devolucion {payload.tipo} registrada para venta #{venta_id} por {monto_total} Bs",
        request,
    )

    dev = _query_devolucion(db).filter(Devolucion.id == devolucion.id).first()
    return _to_admin_out(dev, db)


@router.post("/{devolucion_id}/completar", response_model=DevolucionAdminOut)
def completar_devolucion(
    devolucion_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> DevolucionAdminOut:
    """Completa la devolucion: reingresa el stock al inventario y actualiza
    el estado de la venta. Si la venta estaba pagada y se devuelve todo,
    queda como 'devuelto'; si se devuelve parcialmente, 'devuelto_parcial'."""
    empleado = _get_empleado_o_403(db, usuario)

    dev = _get_devolucion_bloqueada(db, devolucion_id)
    verificar_acceso_sucursal(usuario, dev.venta.sucursal_id)
    if dev.estado != "solicitada":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta devolucion ya fue procesada.")

    venta = dev.venta
    sucursal_id = venta.sucursal_id

    # Reingresar stock al inventario. Si la combinacion ya no tiene fila en
    # esa sucursal (ej. se borro del inventario), se crea: antes el stock
    # devuelto simplemente se perdia sin aviso.
    for detalle in dev.detalles:
        item = detalle.item_linea
        inventario = _inventario_de(db, item, sucursal_id)
        if inventario is None:
            inventario = Inventario(
                producto_id=item.producto_id,
                talla_id=item.talla_id,
                color_id=item.color_id,
                sucursal_id=sucursal_id,
                cantidad=0,
            )
            db.add(inventario)
            db.flush()
        inventario.cantidad += detalle.cantidad_devuelta
        db.flush()
        _registrar_movimiento(
            db, inventario.id, empleado.id, "entrada", detalle.cantidad_devuelta,
            f"Devolucion #{dev.id} de venta #{venta.id}",
        )

    dev.empleado_id = empleado.id
    dev.estado = "completada"
    dev.fecha_resolucion = datetime.utcnow()

    nuevo_estado = "devuelto" if dev.tipo == "total" else "devuelto_parcial"
    venta.estado = nuevo_estado
    # Reembolso "al mismo medio" de una venta pagada con PayPal: sale de la
    # cuenta que cobro (la de la tienda, o la de Arlani si fue "Pagar todo";
    # en ese caso la tienda queda debiendo el monto, ver trg_devolucion_deuda).
    if dev.metodo_reembolso == "mismo_medio":
        _reembolsar_paypal(db, venta.id, Decimal(dev.monto_reembolso))

    _notificar(
        db,
        venta.cliente_id,
        "devolucion_completada",
        f"Tu devolucion para la compra #{venta.id} fue aprobada. "
        f"Se te reembolsaran {dev.monto_reembolso} Bs via {dev.metodo_reembolso.replace('_', ' ')}.",
        dev.id,
    )
    db.commit()

    log_bitacora(
        db, usuario, "ACTUALIZAR", "devolucion", dev.id,
        f"Devolucion #{dev.id} completada — stock reingresado, venta #{venta.id} marcada como {nuevo_estado}",
        request,
    )

    dev = _query_devolucion(db).filter(Devolucion.id == dev.id).first()
    return _to_admin_out(dev, db)


@router.post("/{devolucion_id}/rechazar", response_model=DevolucionAdminOut)
def rechazar_devolucion(
    devolucion_id: int,
    request: Request,
    payload: DevolucionRechazoIn | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> DevolucionAdminOut:
    """Rechaza la devolucion. No se reingresa stock ni se cambia el estado
    de la venta."""
    empleado = _get_empleado_o_403(db, usuario)

    dev = _get_devolucion_bloqueada(db, devolucion_id)
    verificar_acceso_sucursal(usuario, dev.venta.sucursal_id)
    if dev.estado != "solicitada":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta devolucion ya fue procesada.")

    motivo = (payload.motivo or "").strip() if payload else ""
    dev.empleado_id = empleado.id
    dev.estado = "rechazada"
    dev.fecha_resolucion = datetime.utcnow()
    dev.motivo_rechazo = motivo or None
    _notificar(
        db,
        dev.venta.cliente_id,
        "devolucion_rechazada",
        f"Tu solicitud de devolución para la compra #{dev.venta_id} fue rechazada"
        + (f": {motivo}" if motivo else ".")
        + " Si tienes dudas, comunícate con la tienda.",
        dev.id,
    )
    db.commit()

    log_bitacora(
        db, usuario, "ACTUALIZAR", "devolucion", dev.id,
        f"Devolucion #{dev.id} rechazada para venta #{dev.venta_id}",
        request,
    )

    dev = _query_devolucion(db).filter(Devolucion.id == dev.id).first()
    return _to_admin_out(dev, db)


@router.delete("/{devolucion_id}")
def eliminar_devolucion(
    devolucion_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
):
    """Elimina una devolucion. Si la devolucion estaba completada, se revierte
    el reingreso de stock en el inventario y se restaura el estado de la venta
    a 'pagada'. Solo Administrador o Encargado (el Cajero no borra registros
    financieros). Registra la accion en la bitacora."""
    require_encargado_o_admin(usuario)
    empleado = _get_empleado_o_403(db, usuario)

    dev = _get_devolucion_bloqueada(db, devolucion_id)
    verificar_acceso_sucursal(usuario, dev.venta.sucursal_id)

    venta = dev.venta
    estado_previo = dev.estado

    # Si estaba completada, revertir el reingreso de stock en la sucursal de
    # la venta. Si esas unidades ya se volvieron a vender, no alcanza el
    # stock para revertir: antes se recortaba a 0 en silencio (descuadrando
    # el inventario); ahora se rechaza.
    if estado_previo == "completada":
        for detalle in dev.detalles:
            item = detalle.item_linea
            inventario = _inventario_de(db, item, venta.sucursal_id)
            if inventario is None or inventario.cantidad < detalle.cantidad_devuelta:
                db.rollback()
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f'No se puede revertir: el stock devuelto de "{item.producto.nombre}" '
                    f"({item.talla.codigo}, {item.color.nombre}) ya no esta disponible en la sucursal.",
                )
            inventario.cantidad -= detalle.cantidad_devuelta
            db.flush()
            _registrar_movimiento(
                db, inventario.id, empleado.id, "salida", detalle.cantidad_devuelta,
                f"Reversion Devolucion #{dev.id} de venta #{venta.id}",
            )

        otras_completadas = (
            db.query(Devolucion)
            .filter(
                Devolucion.venta_id == venta.id,
                Devolucion.id != dev.id,
                Devolucion.estado == "completada",
            )
            .first()
        )
        if not otras_completadas:
            venta.estado = "pagada"

    db.delete(dev)
    db.commit()

    log_bitacora(
        db,
        usuario,
        "ELIMINAR",
        "devolucion",
        devolucion_id,
        f"Devolucion #{devolucion_id} (estado previo: {estado_previo}) eliminada para venta #{venta.id}",
        request,
    )

    return {"message": f"Devolucion #{devolucion_id} eliminada exitosamente."}
