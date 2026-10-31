"""CU Cambio de prendas.

El cliente pide cambiar una prenda comprada por otra de la misma tienda
dentro de las 24 horas de su compra. La nueva puede salir de cualquier
sucursal de la tienda: ahi la recoge y entrega la que devuelve. El personal (Administrador, Encargado
o Cajero) aprueba o rechaza. Si la prenda nueva cuesta mas que lo que el
cliente PAGO, paga la diferencia con los metodos de la tienda; si cuesta
menos, se le devuelve (por PayPal si pago con PayPal; si no, en tienda).
Al completarse, sale del stock la prenda nueva y la devuelta va a su
destino (reingreso, merma o proveedor). Las reglas viven en los PA
sp_*_cambio (ver migracion f1b3d5e7a908).
"""

from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.deps import require_permiso, require_permiso_cliente, sucursal_restringida, verificar_acceso_sucursal
from app.api.v1.endpoints.metodos_pago import _publico
from app.api.v1.endpoints.ventas import (
    _a_usd,
    _error_sp,
    _get_cliente_o_403,
    _get_empleado_o_403,
    _monto_coincide,
    _paypal_de_tienda,
)
from app.core.audit import log_bitacora
from app.core.aviso_cliente import programar_correo
from app.api.v1.endpoints.paypal_guardado import registrar_paypal_usado
from app.core.paypal import captura_de, capturar_orden, crear_orden, obtener_orden, reembolsar_captura
from app.core.storage import upload_comprobante_pago
from app.db.session import get_db
from app.models import MetodoPagoEmpresa, Notificacion, Usuario
from app.schemas.cambios import (
    AprobarCambioIn,
    CambioOut,
    LineaCambiableOut,
    MotivoIn,
    OpcionesCambioOut,
    PrendaCambioOut,
    SolicitudCambioIn,
    StockSucursalOut,
    VarianteOut,
)
from app.schemas.metodos_pago import MetodoPagoPublicoOut
from app.schemas.ventas import OrdenPaypalOut, TiendaFacturaOut

router = APIRouter()

PLAZO_CAMBIO = timedelta(hours=24)

_SQL_CAMBIO = """
    SELECT c.*, v.fecha AS venta_fecha, s.nombre AS sucursal_nombre, s.empresa_id,
           e.nombre AS e_nombre, e.subdominio AS e_subdominio, e.logo_url AS e_logo_url, e.color_marca AS e_color_marca,
           e.ciudad AS e_ciudad, e.email_contacto AS e_email_contacto, e.razon_social AS e_razon_social,
           e.nit AS e_nit, e.direccion_fiscal AS e_direccion_fiscal, e.telefono AS e_telefono,
           u.nombre AS cliente_nombre, u.email AS cliente_email,
           po.nombre AS producto_original, tor.codigo AS talla_original, cor.nombre AS color_original,
           pn.nombre AS producto_nuevo, tn.codigo AS talla_nueva, cn.nombre AS color_nuevo,
           mp.nombre AS metodo_pago_nombre, ue.nombre AS empleado_nombre
    FROM cambio_prenda c
    JOIN venta v ON v.id = c.venta_id
    JOIN sucursal s ON s.id = c.sucursal_id
    JOIN empresa e ON e.id = s.empresa_id
    JOIN usuario u ON u.id = c.cliente_id
    JOIN item_linea il ON il.id = c.item_linea_id
    JOIN producto po ON po.id = il.producto_id
    JOIN talla tor ON tor.id = il.talla_id
    JOIN color cor ON cor.id = il.color_id
    JOIN producto pn ON pn.id = c.producto_nuevo_id
    JOIN talla tn ON tn.id = c.talla_nueva_id
    JOIN color cn ON cn.id = c.color_nuevo_id
    LEFT JOIN metodo_pago_empresa mp ON mp.id = c.metodo_pago_id
    LEFT JOIN usuario ue ON ue.id = c.empleado_id
"""

_CAMPOS_CAMBIO = (
    "id venta_id item_linea_id venta_fecha estado motivo observaciones cantidad sucursal_id sucursal_nombre cliente_nombre "
    "cliente_email producto_original talla_original color_original producto_nuevo talla_nueva color_nuevo "
    "precio_pagado precio_nuevo diferencia destino motivo_rechazo reembolso_metodo metodo_pago_nombre "
    "comprobante_url empleado_nombre fecha_solicitud fecha_resolucion fecha_completado"
).split()


def _to_out(db: Session, fila, con_metodos: bool = False) -> CambioOut:
    out = CambioOut(
        **{k: fila[k] for k in _CAMPOS_CAMBIO},
        tienda=TiendaFacturaOut(
            id=fila["empresa_id"],
            **{k: fila[f"e_{k}"] for k in (
                "nombre", "subdominio", "logo_url", "color_marca", "ciudad", "email_contacto",
                "razon_social", "nit", "direccion_fiscal", "telefono",
            )},
        ),
    )
    if con_metodos and fila["estado"] == "por_pagar":
        metodos = (
            db.query(MetodoPagoEmpresa)
            .filter(MetodoPagoEmpresa.empresa_id == fila["empresa_id"], MetodoPagoEmpresa.activo.is_(True))
            .order_by(MetodoPagoEmpresa.orden, MetodoPagoEmpresa.id)
            .all()
        )
        out.metodos = [MetodoPagoPublicoOut(**_publico(m)) for m in metodos]
        out.diferencia_usd = _a_usd(db, Decimal(fila["diferencia"]))[0]
    return out


def _cambio(db: Session, cambio_id: int, cliente_id: int | None = None):
    sql = _SQL_CAMBIO + " WHERE c.id = :id" + (" AND c.cliente_id = :cli" if cliente_id else "")
    fila = db.execute(text(sql), {"id": cambio_id, "cli": cliente_id}).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cambio no encontrado.")
    return fila


# Avisos que ademas llegan por correo (lo que resuelve la tienda).
_TITULOS_CORREO = {
    "cambio_aprobado": "Tu cambio de prenda fue aprobado",
    "cambio_rechazado": "Tu cambio de prenda fue rechazado",
    "cambio_completado": "Tu cambio de prenda está completo",
    "cambio_pago_rechazado": "Revisamos el pago de tu cambio",
}


def _notificar(db: Session, cliente_id: int, evento: str, mensaje: str, cambio_id: int) -> None:
    titulo = _TITULOS_CORREO.get(evento)
    if titulo:
        empresa_id = db.execute(
            text("SELECT s.empresa_id FROM cambio_prenda c JOIN sucursal s ON s.id = c.sucursal_id WHERE c.id = :id"),
            {"id": cambio_id},
        ).scalar()
        programar_correo(db, cliente_id, empresa_id, titulo, mensaje)
    db.add(
        Notificacion(
            cliente_id=cliente_id,
            canal="sistema",
            tipo_evento=evento,
            mensaje=mensaje,
            estado="enviada",
            leida=False,
            entidad_tipo="cambio_prenda",
            entidad_id=cambio_id,
        )
    )


def _ejecutar(db: Session, sql: str, params: dict):
    try:
        return db.execute(text(sql), params)
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)


# =============================================================== cliente


@router.get("/opciones/{venta_id}", response_model=OpcionesCambioOut)
def opciones_de_cambio(
    venta_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> OpcionesCambioOut:
    cliente = _get_cliente_o_403(db, usuario)
    venta = db.execute(
        text(
            "SELECT v.id, v.fecha, v.estado, v.sucursal_id, s.nombre AS sucursal, s.empresa_id, e.nombre AS tienda, "
            "fn_empresa_operativa(e.id) AS operativa, now() AT TIME ZONE 'UTC' AS ahora "
            "FROM venta v JOIN sucursal s ON s.id = v.sucursal_id JOIN empresa e ON e.id = s.empresa_id "
            "WHERE v.id = :v AND v.cliente_id = :c"
        ),
        {"v": venta_id, "c": cliente.id},
    ).mappings().first()
    if venta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compra no encontrada.")

    plazo = venta["fecha"] + PLAZO_CAMBIO
    en_plazo = venta["ahora"] <= plazo
    motivo_no = None
    if venta["estado"] != "pagada":
        motivo_no = "Solo se pueden cambiar prendas de compras pagadas."
    elif not en_plazo:
        motivo_no = "Pasaron más de 24 horas desde tu compra: ya no se puede cambiar."
    elif not venta["operativa"]:
        motivo_no = "La tienda no está atendiendo por ahora."

    lineas = db.execute(
        text(
            """
            SELECT il.id AS item_linea_id, il.producto_id, p.nombre AS producto_nombre, t.codigo AS talla_codigo,
                   c.nombre AS color_nombre, il.cantidad,
                   COALESCE(dvd.precio_unitario, dvp.precio_unitario) AS precio_pagado,
                   (SELECT url FROM producto_imagen pi WHERE pi.producto_id = p.id ORDER BY pi.orden LIMIT 1) AS imagen_url,
                   -- Una sola solicitud por prenda: con un cambio (no cancelado) o
                   -- una devolucion, en cualquier estado, ya no se puede cambiar.
                   CASE WHEN EXISTS (SELECT 1 FROM cambio_prenda cp WHERE cp.item_linea_id = il.id AND cp.estado <> 'cancelado')
                          OR EXISTS (SELECT 1 FROM detalle_devolucion dd WHERE dd.item_linea_id = il.id)
                        THEN 0 ELSE il.cantidad END AS disponibles
            FROM item_linea il
            JOIN producto p ON p.id = il.producto_id
            JOIN talla t ON t.id = il.talla_id
            JOIN color c ON c.id = il.color_id
            LEFT JOIN detalle_venta_digital dvd ON dvd.id = il.id AND dvd.venta_digital_id = :v
            LEFT JOIN detalle_venta_presencial dvp ON dvp.id = il.id AND dvp.venta_presencial_id = :v
            WHERE dvd.id IS NOT NULL OR dvp.id IS NOT NULL
            ORDER BY il.id
            """
        ),
        {"v": venta_id},
    ).mappings().all()

    # Stock de TODA la tienda (todas sus sucursales activas): el cliente elige
    # talla, color y en que sucursal recoge la prenda nueva.
    prendas: dict[int, PrendaCambioOut] = {}
    if motivo_no is None:
        filas = db.execute(
            text(
                """
                SELECT p.id, p.nombre, p.precio,
                       (SELECT url FROM producto_imagen pi WHERE pi.producto_id = p.id ORDER BY pi.orden LIMIT 1) AS imagen_url,
                       i.talla_id, t.codigo AS talla_codigo, i.color_id, c.nombre AS color_nombre,
                       s.id AS sucursal_id, s.nombre AS sucursal_nombre, i.cantidad AS stock
                FROM inventario i
                JOIN producto p ON p.id = i.producto_id
                JOIN sucursal s ON s.id = i.sucursal_id
                JOIN talla t ON t.id = i.talla_id
                JOIN color c ON c.id = i.color_id
                WHERE s.empresa_id = :e AND s.estado = 'activa' AND i.cantidad > 0
                  AND p.empresa_id = :e AND p.estado = 'activo'
                ORDER BY p.nombre, t.id, c.nombre, (s.id = :s) DESC, s.nombre
                """
            ),
            {"s": venta["sucursal_id"], "e": venta["empresa_id"]},
        ).mappings().all()
        variantes: dict[tuple[int, int, int], VarianteOut] = {}
        for f in filas:
            prenda = prendas.setdefault(
                f["id"],
                PrendaCambioOut(producto_id=f["id"], nombre=f["nombre"], precio=f["precio"], imagen_url=f["imagen_url"], variantes=[]),
            )
            clave = (f["id"], f["talla_id"], f["color_id"])
            variante = variantes.get(clave)
            if variante is None:
                variante = VarianteOut(
                    talla_id=f["talla_id"], talla_codigo=f["talla_codigo"], color_id=f["color_id"],
                    color_nombre=f["color_nombre"], stock=0, sucursales=[],
                )
                variantes[clave] = variante
                prenda.variantes.append(variante)
            variante.stock += f["stock"]
            variante.sucursales.append(
                StockSucursalOut(sucursal_id=f["sucursal_id"], sucursal_nombre=f["sucursal_nombre"], stock=f["stock"])
            )

    return OpcionesCambioOut(
        venta_id=venta["id"],
        fecha=venta["fecha"],
        plazo_hasta=plazo,
        en_plazo=en_plazo,
        puede_cambiar=motivo_no is None and any(l["disponibles"] > 0 for l in lineas),
        motivo_no=motivo_no,
        tienda_nombre=venta["tienda"],
        sucursal_id=venta["sucursal_id"],
        sucursal_nombre=venta["sucursal"],
        lineas=[LineaCambiableOut(**l) for l in lineas],
        prendas=list(prendas.values()),
    )


@router.post("", response_model=CambioOut, status_code=status.HTTP_201_CREATED)
def solicitar_cambio(
    payload: SolicitudCambioIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> CambioOut:
    cliente = _get_cliente_o_403(db, usuario)
    cambio_id = _ejecutar(
        db,
        "SELECT sp_solicitar_cambio(:cli, :venta, :linea, :cant, :prod, :talla, :color, :suc, :motivo, :obs)",
        {
            "cli": cliente.id, "venta": payload.venta_id, "linea": payload.item_linea_id, "cant": payload.cantidad,
            "prod": payload.producto_id, "talla": payload.talla_id, "color": payload.color_id,
            "suc": payload.sucursal_id, "motivo": payload.motivo, "obs": payload.observaciones,
        },
    ).scalar_one()
    db.commit()
    log_bitacora(db, usuario, "CREAR", "cambio_prenda", cambio_id, f"Solicitud de cambio de prenda (venta #{payload.venta_id})", request)
    return _to_out(db, _cambio(db, cambio_id), con_metodos=True)


@router.get("/mios", response_model=list[CambioOut])
def mis_cambios(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> list[CambioOut]:
    cliente = _get_cliente_o_403(db, usuario)
    filas = db.execute(
        text(_SQL_CAMBIO + " WHERE c.cliente_id = :c ORDER BY c.fecha_solicitud DESC"), {"c": cliente.id}
    ).mappings().all()
    return [_to_out(db, f, con_metodos=True) for f in filas]


@router.get("/mios/{cambio_id}", response_model=CambioOut)
def mi_cambio(
    cambio_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> CambioOut:
    cliente = _get_cliente_o_403(db, usuario)
    return _to_out(db, _cambio(db, cambio_id, cliente.id), con_metodos=True)


@router.post("/{cambio_id}/cancelar", response_model=CambioOut)
def cancelar_cambio(
    cambio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> CambioOut:
    cliente = _get_cliente_o_403(db, usuario)
    _ejecutar(db, "SELECT sp_cancelar_cambio(:id, :cli)", {"id": cambio_id, "cli": cliente.id})
    db.commit()
    log_bitacora(db, usuario, "ACTUALIZAR", "cambio_prenda", cambio_id, "El cliente canceló su cambio de prenda", request)
    return _to_out(db, _cambio(db, cambio_id, cliente.id))


# ---------------------------------------------- pagar la diferencia (cliente)


def _por_pagar(db: Session, cambio_id: int, cliente_id: int):
    fila = _cambio(db, cambio_id, cliente_id)
    if fila["estado"] != "por_pagar":
        raise HTTPException(status.HTTP_409_CONFLICT, "Este cambio no tiene una diferencia por pagar.")
    return fila


@router.post("/{cambio_id}/paypal/orden", response_model=OrdenPaypalOut)
def orden_diferencia(
    cambio_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> OrdenPaypalOut:
    cliente = _get_cliente_o_403(db, usuario)
    fila = _por_pagar(db, cambio_id, cliente.id)
    _, cuenta = _paypal_de_tienda(db, fila["empresa_id"])
    usd, _ = _a_usd(db, Decimal(fila["diferencia"]))
    orden = crear_orden(usd, referencia=f"cambio-{cambio_id}", cuenta=cuenta)
    return OrdenPaypalOut(order_id=orden["id"], total=usd, approve_url=None)


@router.post("/{cambio_id}/paypal/capturar/{order_id}", response_model=CambioOut)
def capturar_diferencia(
    cambio_id: int,
    order_id: str,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> CambioOut:
    cliente = _get_cliente_o_403(db, usuario)
    fila = _por_pagar(db, cambio_id, cliente.id)
    metodo, cuenta = _paypal_de_tienda(db, fila["empresa_id"])
    usd, _ = _a_usd(db, Decimal(fila["diferencia"]))
    unidad = (obtener_orden(order_id, cuenta).get("purchase_units") or [{}])[0]
    if unidad.get("reference_id") != f"cambio-{cambio_id}" or not _monto_coincide(unidad.get("amount"), usd):
        raise HTTPException(status.HTTP_409_CONFLICT, "El pago no corresponde a este cambio. Vuelve a intentarlo.")

    # Primero se valida y mueve el stock (sin confirmar); despues se cobra.
    _ejecutar(
        db,
        "SELECT sp_pagar_diferencia_cambio(:id, :cli, :metodo, NULL, :orden, 'pendiente')",
        {"id": cambio_id, "cli": cliente.id, "metodo": metodo.id, "orden": order_id},
    )
    try:
        resultado = capturar_orden(order_id, cuenta)
    except HTTPException:
        db.rollback()
        raise
    captura = captura_de(resultado)
    if resultado.get("status") != "COMPLETED" or captura is None or not _monto_coincide(captura.get("amount"), usd):
        db.rollback()
        if captura:
            reembolsar_captura(captura["id"], cuenta)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "PayPal no confirmó el pago de la diferencia.")
    db.execute(text("UPDATE cambio_prenda SET captura_id = :c WHERE id = :id"), {"c": captura["id"], "id": cambio_id})
    db.commit()
    registrar_paypal_usado(db, cliente.id, resultado, fila["empresa_id"])
    log_bitacora(db, usuario, "ACTUALIZAR", "cambio_prenda", cambio_id, f"Diferencia del cambio pagada con PayPal (orden {order_id})", request)
    return _to_out(db, _cambio(db, cambio_id, cliente.id))


@router.post("/{cambio_id}/comprobante", response_model=CambioOut)
async def comprobante_diferencia(
    cambio_id: int,
    request: Request,
    metodo_pago_id: int = Form(...),
    file: UploadFile = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> CambioOut:
    cliente = _get_cliente_o_403(db, usuario)
    _por_pagar(db, cambio_id, cliente.id)
    if file is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sube la foto de tu comprobante de pago.")
    url = upload_comprobante_pago(cliente.id, await file.read(), file.content_type or "")
    _ejecutar(
        db,
        "SELECT sp_pagar_diferencia_cambio(:id, :cli, :metodo, :url, NULL, NULL)",
        {"id": cambio_id, "cli": cliente.id, "metodo": metodo_pago_id, "url": url},
    )
    db.commit()
    log_bitacora(db, usuario, "ACTUALIZAR", "cambio_prenda", cambio_id, "Comprobante de la diferencia del cambio enviado", request)
    return _to_out(db, _cambio(db, cambio_id, cliente.id))


# =============================================================== personal


@router.get("", response_model=list[CambioOut])
def listar_cambios(
    estado: str | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> list[CambioOut]:
    sql = _SQL_CAMBIO + " WHERE TRUE"
    params: dict = {}
    if estado:
        sql += " AND c.estado = :estado"
        params["estado"] = estado
    restringida = sucursal_restringida(usuario)
    if restringida is not None:
        sql += " AND c.sucursal_id = :suc"
        params["suc"] = restringida
    filas = db.execute(text(sql + " ORDER BY c.fecha_solicitud DESC LIMIT 300"), params).mappings().all()
    return [_to_out(db, f) for f in filas]


@router.get("/{cambio_id}", response_model=CambioOut)
def ver_cambio(
    cambio_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> CambioOut:
    fila = _cambio(db, cambio_id)
    verificar_acceso_sucursal(usuario, fila["sucursal_id"])
    return _to_out(db, fila)


def _reembolso_de(db: Session, venta_id: int) -> tuple[str, str | None, bool, int]:
    """Como se devuelve la diferencia: por PayPal si la venta se cobro con
    PayPal (y se guardo la captura); si no, en tienda."""
    fila = db.execute(
        text(
            "SELECT p.metodo, p.liquidacion_id, t.captura_id, s.empresa_id FROM pago p "
            "JOIN venta v ON v.id = p.venta_id JOIN sucursal s ON s.id = v.sucursal_id "
            "LEFT JOIN transaccion t ON t.pago_id = p.id WHERE p.venta_id = :v"
        ),
        {"v": venta_id},
    ).mappings().first()
    if fila and fila["metodo"] == "paypal" and fila["captura_id"]:
        return "paypal", fila["captura_id"], fila["liquidacion_id"] is not None, fila["empresa_id"]
    return "en_tienda", None, False, fila["empresa_id"] if fila else 0


@router.post("/{cambio_id}/aprobar", response_model=CambioOut)
def aprobar_cambio(
    cambio_id: int,
    payload: AprobarCambioIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> CambioOut:
    empleado = _get_empleado_o_403(db, usuario)
    fila = _cambio(db, cambio_id)
    verificar_acceso_sucursal(usuario, fila["sucursal_id"])
    diferencia = Decimal(fila["diferencia"])
    metodo_reembolso, captura_id, cobro_arlani, empresa_id = _reembolso_de(db, fila["venta_id"])

    estado = _ejecutar(
        db,
        "SELECT sp_aprobar_cambio(:id, :emp, :destino, :obs, :reembolso)",
        {"id": cambio_id, "emp": empleado.id, "destino": payload.destino, "obs": payload.observacion, "reembolso": metodo_reembolso},
    ).scalar_one()

    # La prenda nueva cuesta menos: se devuelve la diferencia por PayPal desde
    # la cuenta que cobro (si fue "Pagar todo", la de Arlani y la tienda la debe).
    if estado == "completado" and diferencia < 0 and metodo_reembolso == "paypal":
        cuenta = None if cobro_arlani else _paypal_de_tienda(db, empresa_id)[1]
        usd, _ = _a_usd(db, -diferencia)
        if not reembolsar_captura(captura_id, cuenta, usd):
            db.rollback()
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "PayPal no aceptó devolver la diferencia. Inténtalo de nuevo en unos minutos."
            )

    if estado == "por_pagar":
        mensaje = (
            f"Tu cambio de prenda #{cambio_id} fue aprobado. Paga la diferencia de Bs {diferencia} "
            "desde Mi cuenta para completarlo."
        )
    elif diferencia < 0:
        mensaje = (
            f"Tu cambio de prenda #{cambio_id} está listo. Te devolvemos Bs {-diferencia}"
            + (" a tu PayPal." if metodo_reembolso == "paypal" else " en la tienda al recoger tu prenda.")
        )
    else:
        mensaje = f"Tu cambio de prenda #{cambio_id} está listo. Recoge tu prenda nueva en {fila['sucursal_nombre']}."
    _notificar(db, fila["cliente_id"], "cambio_aprobado", mensaje, cambio_id)
    db.commit()
    log_bitacora(db, usuario, "ACTUALIZAR", "cambio_prenda", cambio_id, f"Cambio de prenda aprobado ({estado}, destino {payload.destino})", request)
    return _to_out(db, _cambio(db, cambio_id))


@router.post("/{cambio_id}/rechazar", response_model=CambioOut)
def rechazar_cambio(
    cambio_id: int,
    payload: MotivoIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> CambioOut:
    empleado = _get_empleado_o_403(db, usuario)
    fila = _cambio(db, cambio_id)
    verificar_acceso_sucursal(usuario, fila["sucursal_id"])
    _ejecutar(db, "SELECT sp_rechazar_cambio(:id, :emp, :motivo)", {"id": cambio_id, "emp": empleado.id, "motivo": payload.motivo})
    _notificar(db, fila["cliente_id"], "cambio_rechazado", f"Tu cambio de prenda #{cambio_id} fue rechazado: {payload.motivo}", cambio_id)
    db.commit()
    log_bitacora(db, usuario, "ACTUALIZAR", "cambio_prenda", cambio_id, f"Cambio de prenda rechazado: {payload.motivo}", request)
    return _to_out(db, _cambio(db, cambio_id))


@router.post("/{cambio_id}/aprobar-pago", response_model=CambioOut)
def aprobar_pago_cambio(
    cambio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> CambioOut:
    empleado = _get_empleado_o_403(db, usuario)
    fila = _cambio(db, cambio_id)
    verificar_acceso_sucursal(usuario, fila["sucursal_id"])
    _ejecutar(db, "SELECT sp_revisar_pago_cambio(:id, :emp, TRUE, NULL)", {"id": cambio_id, "emp": empleado.id})
    _notificar(db, fila["cliente_id"], "cambio_completado",
               f"Recibimos el pago de tu cambio #{cambio_id}. Recoge tu prenda nueva en {fila['sucursal_nombre']}.", cambio_id)
    db.commit()
    log_bitacora(db, usuario, "ACTUALIZAR", "cambio_prenda", cambio_id, "Pago de la diferencia del cambio aprobado", request)
    return _to_out(db, _cambio(db, cambio_id))


@router.post("/{cambio_id}/rechazar-pago", response_model=CambioOut)
def rechazar_pago_cambio(
    cambio_id: int,
    payload: MotivoIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> CambioOut:
    empleado = _get_empleado_o_403(db, usuario)
    fila = _cambio(db, cambio_id)
    verificar_acceso_sucursal(usuario, fila["sucursal_id"])
    _ejecutar(db, "SELECT sp_revisar_pago_cambio(:id, :emp, FALSE, :m)", {"id": cambio_id, "emp": empleado.id, "m": payload.motivo})
    _notificar(db, fila["cliente_id"], "cambio_pago_rechazado",
               f"El comprobante de tu cambio #{cambio_id} no fue aceptado: {payload.motivo}. Puedes volver a pagar.", cambio_id)
    db.commit()
    log_bitacora(db, usuario, "ACTUALIZAR", "cambio_prenda", cambio_id, f"Comprobante del cambio rechazado: {payload.motivo}", request)
    return _to_out(db, _cambio(db, cambio_id))
