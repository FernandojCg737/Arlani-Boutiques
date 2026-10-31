import base64
import binascii
from datetime import datetime
import json
import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, joinedload, object_session

from app.api.deps import (
    require_encargado_o_admin,
    require_permiso,
    require_permiso_cliente,
    sucursal_restringida,
    verificar_acceso_sucursal,
)
from app.core.audit import log_bitacora
from app.core.cifrado import descifrar
from app.core.errores_db import http_desde_pg
from app.core.liquidaciones import enviar_liquidaciones
from app.api.v1.endpoints.paypal_guardado import registrar_paypal_usado
from app.core.config import settings
from app.core.paypal import (
    CuentaPaypal,
    PAYPAL_CURRENCY,
    captura_de,
    capturar_orden,
    crear_orden,
    obtener_orden,
    reembolsar_captura,
)
from app.core.storage import upload_comprobante_pago
from app.db.session import get_db
from app.models import (
    Carrito,
    Cliente,
    Color,
    DetalleCarrito,
    DetalleVentaDigital,
    DetalleVentaPresencial,
    Empleado,
    Inventario,
    MetodoPagoEmpresa,
    Pago,
    Producto,
    Sucursal,
    Talla,
    Usuario,
    Venta,
    VentaDigital,
    VentaPresencial,
)
from app.schemas.metodos_pago import MetodoPagoPublicoOut
from app.schemas.ventas import (
    ClienteBusquedaOut,
    EnvioEstadoIn,
    EnvioOut,
    ItemCheckoutOut,
    ProductoMostradorOut,
    RechazoPagoIn,
    VarianteMostradorOut,
    TiendaCheckoutOut,
    TiendaFacturaOut,
    DetalleVentaOut,
    OrdenPaypalIn,
    OrdenPaypalOut,
    VentaAdminOut,
    VentaEditIn,
    VentaOut,
    VentaPage,
    VentaPresencialCreate,
    VerificarStockItemOut,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Cliente generico de las ventas de mostrador a personas sin cuenta
# (migracion f2b4d6e8a091): la venta guarda el nombre y el NIT reales.
CONSUMIDOR_FINAL_EMAIL = "consumidor.final@arlaniboutiques.com"

# Mensajes de las RAISE EXCEPTION de las funciones sp_* que tienen sentido
# para el usuario (el resto se responde como error generico).
_ERRORES_SP = {
    "stock_insuficiente": "No hay suficiente stock para completar la operacion. Revisa las cantidades.",
    "producto_no_encontrado": "Uno de los productos ya no existe.",
    "venta_no_encontrada": "Venta no encontrada.",
    "pago_no_pendiente": "Esta venta no tiene un pago QR pendiente de verificacion.",
}


def _error_sp(exc: DBAPIError) -> HTTPException:
    mensaje = str(getattr(exc, "orig", exc))
    for codigo, texto in _ERRORES_SP.items():
        if codigo in mensaje:
            return HTTPException(status.HTTP_400_BAD_REQUEST, texto)
    if "ck_inventario_cantidad_no_negativa" in mensaje:
        return HTTPException(status.HTTP_400_BAD_REQUEST, _ERRORES_SP["stock_insuficiente"])
    # Codigos de los PA nuevos (metodos de pago, comprobantes...).
    traducido = http_desde_pg(exc)
    if traducido is not None:
        return traducido
    logger.exception("Error inesperado de la base de datos en ventas")
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No se pudo completar la operacion.")


def _get_cliente_o_403(db: Session, usuario: Usuario) -> Cliente:
    cliente = db.query(Cliente).filter(Cliente.id == usuario.id).first()
    if cliente is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo los clientes pueden comprar.")
    return cliente


def _get_empleado_o_403(db: Session, usuario: Usuario) -> Empleado:
    empleado = db.query(Empleado).filter(Empleado.id == usuario.id).first()
    if empleado is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el personal de sucursal puede hacer esto.")
    return empleado


def _get_carrito_activo_no_vacio(db: Session, cliente_id: int, empresa_id: int | None = None) -> Carrito:
    carrito = (
        db.query(Carrito)
        .options(
            joinedload(Carrito.detalles).joinedload(DetalleCarrito.producto),
            joinedload(Carrito.detalles).joinedload(DetalleCarrito.talla),
            joinedload(Carrito.detalles).joinedload(DetalleCarrito.color),
            joinedload(Carrito.detalles).joinedload(DetalleCarrito.sucursal),
        )
        .filter(Carrito.cliente_id == cliente_id, Carrito.estado == "activo")
        .first()
    )
    if carrito is None or not carrito.detalles:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tu carrito esta vacio.")
    # Una tienda suspendida o con la suscripcion vencida no recibe pedidos.
    # Al pagar por tienda solo importa la tienda que se esta pagando.
    empresas = {empresa_id} if empresa_id is not None else {d.producto.empresa_id for d in carrito.detalles}
    cerradas = db.execute(
        text("SELECT nombre FROM empresa WHERE id = ANY(:ids) AND NOT fn_empresa_operativa(id)"),
        {"ids": list(empresas)},
    ).scalars().all()
    if cerradas:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{', '.join(cerradas)} no está recibiendo pedidos por ahora. Quita sus productos del carrito para continuar.",
        )
    return carrito


def _calcular_total(carrito: Carrito) -> Decimal:
    """Total con el precio VIGENTE de cada producto -- el mismo que usan
    sp_crear_venta_digital_* para registrar la venta. Si se usara el precio
    guardado al agregar al carrito, un cambio de precio en el medio haria
    que PayPal cobre un monto y la venta quede registrada con otro."""
    return sum((d.producto.precio * d.cantidad for d in carrito.detalles), Decimal("0")).quantize(Decimal("0.01"))


def _agrupar_por_sucursal(detalles: list["DetalleCarrito"]) -> dict[int, list["DetalleCarrito"]]:
    """Pedido del usuario: la sucursal de retiro se elige POR PRODUCTO al
    agregarlo al carrito (DetalleCarrito.sucursal_id), no una sola vez en el
    checkout -- si el carrito queda con productos de sucursales distintas,
    se reparte en una venta por sucursal, todas fondeadas por el mismo pago
    (un solo PayPal/comprobante QR)."""
    grupos: dict[int, list["DetalleCarrito"]] = {}
    for d in detalles:
        grupos.setdefault(d.sucursal_id, []).append(d)
    return grupos


def _items_json(items) -> str:
    """Arma el JSONB que reciben las funciones sp_crear_venta_*/sp_editar_venta:
    [{"producto_id":..,"talla_id":..,"color_id":..,"cantidad":..}, ...]."""
    return json.dumps(
        [
            {
                "producto_id": i.producto_id,
                "talla_id": i.talla_id,
                "color_id": i.color_id,
                "cantidad": i.cantidad,
            }
            for i in items
        ]
    )


def _imagen_de_data_url(data_url: str) -> tuple[bytes, str]:
    # Foto tomada en el mostrador (data:image/jpeg;base64,...).
    cabecera, _, datos = data_url.partition(",")
    tipo = cabecera.removeprefix("data:").split(";")[0] or "image/jpeg"
    try:
        return base64.b64decode(datos or data_url), tipo
    except (binascii.Error, ValueError) as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La foto del comprobante no es válida.") from err


def _monto_coincide(amount: dict | None, total: Decimal) -> bool:
    if not amount or amount.get("currency_code") != PAYPAL_CURRENCY:
        return False
    try:
        return Decimal(str(amount.get("value"))).quantize(Decimal("0.01")) == total
    except (InvalidOperation, TypeError):
        return False


def _reembolsar_o_loguear(captura: dict, order_id: str, motivo: str) -> None:
    capture_id = captura.get("id")
    if capture_id and reembolsar_captura(capture_id):
        logger.warning("Captura PayPal %s (orden %s) reembolsada: %s", capture_id, order_id, motivo)
    else:
        logger.error(
            "REVISAR A MANO: no se pudo reembolsar la captura %s (orden %s) -- %s", capture_id, order_id, motivo
        )


def _verificar_stock_carrito(db: Session, carrito: Carrito) -> None:
    """Chequeo 'amigable' en Python (con el nombre real del producto en el
    mensaje) antes de llamar a la funcion -- la funcion vuelve a validar con
    lock por su cuenta como resguardo de bajo nivel ante condiciones de
    carrera, igual que ya hace sp_actualizar_inventario_cantidad. Cada item
    se valida contra SU PROPIA sucursal (la que se eligio al agregarlo al
    carrito), no una sola sucursal global."""
    for d in carrito.detalles:
        inventario = (
            db.query(Inventario)
            .filter(
                Inventario.producto_id == d.producto_id,
                Inventario.talla_id == d.talla_id,
                Inventario.color_id == d.color_id,
                Inventario.sucursal_id == d.sucursal_id,
            )
            .first()
        )
        if inventario is None or inventario.cantidad < d.cantidad:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f'No hay suficiente stock de "{d.producto.nombre}" ({d.talla.codigo}, {d.color.nombre}) '
                f"en {d.sucursal.nombre}.",
            )


def _query_venta_con_detalles(db: Session):
    return db.query(Venta).options(
        joinedload(Venta.sucursal).joinedload(Sucursal.empresa),
        joinedload(Venta.cliente),
        joinedload(Venta.pago).joinedload(Pago.metodo_pago),
        joinedload(Venta.envio),
        joinedload(Venta.calificacion),
        joinedload(Venta.devoluciones),
        joinedload(VentaDigital.detalles).joinedload(DetalleVentaDigital.producto),
        joinedload(VentaDigital.detalles).joinedload(DetalleVentaDigital.talla),
        joinedload(VentaDigital.detalles).joinedload(DetalleVentaDigital.color),
        joinedload(VentaPresencial.atendido_por),
        joinedload(VentaPresencial.detalles).joinedload(DetalleVentaPresencial.producto),
        joinedload(VentaPresencial.detalles).joinedload(DetalleVentaPresencial.talla),
        joinedload(VentaPresencial.detalles).joinedload(DetalleVentaPresencial.color),
    )


def _lineas_ya_solicitadas(venta: Venta) -> set[int]:
    """Lineas de la venta que ya tuvieron una solicitud de cambio (no
    cancelada por el cliente) o de devolucion (en cualquier estado)."""
    ids = {det.item_linea_id for dev in getattr(venta, "devoluciones", []) for det in dev.detalles}
    sesion = object_session(venta)
    if sesion is not None:
        ids |= set(
            sesion.execute(
                text("SELECT item_linea_id FROM cambio_prenda WHERE venta_id = :v AND estado <> 'cancelado'"),
                {"v": venta.id},
            ).scalars()
        )
    return ids


def _to_out(venta: Venta) -> VentaOut:
    detalles = getattr(venta, "detalles", [])
    atendido_por = getattr(venta, "atendido_por", None)
    calificacion = getattr(venta, "calificacion", None)
    # Devolucion info: la mas reciente (si existe)
    devoluciones = getattr(venta, "devoluciones", [])
    ultima_dev = devoluciones[-1] if devoluciones else None

    # Plazo maximo de devolucion: 24 horas desde la fecha de compra
    ahora = datetime.utcnow()
    horas_transcurridas = (ahora - venta.fecha).total_seconds() / 3600.0 if venta.fecha else 999.0
    horas_restantes = max(0.0, round(24.0 - horas_transcurridas, 1))
    devolucion_activa = ultima_dev is not None and ultima_dev.estado in ("solicitada", "aprobada", "completada")
    # Politica: una sola solicitud por prenda. Una prenda con un cambio (no
    # cancelado por el cliente) o con una devolucion, en cualquier estado,
    # ya no admite otro cambio ni devolucion.
    bloqueadas = _lineas_ya_solicitadas(venta)
    libres = any(d.id not in bloqueadas for d in detalles)
    en_plazo = venta.estado == "pagada" and horas_transcurridas <= 24.0
    puede_devolver = en_plazo and not devolucion_activa and libres
    puede_cambiar = en_plazo and libres

    return VentaOut(
        id=venta.id,
        tipo=venta.tipo,
        sucursal_id=venta.sucursal_id,
        sucursal_nombre=venta.sucursal.nombre,
        fecha=venta.fecha,
        total=venta.total,
        estado=venta.estado,
        metodo_pago=venta.pago.metodo if venta.pago else "",
        estado_pago=venta.pago.estado if venta.pago else "",
        atendido_por_nombre=atendido_por.nombre if atendido_por else None,
        calificacion_estrellas=calificacion.estrellas if calificacion else None,
        calificacion_comentario=calificacion.comentario if calificacion else None,
        detalles=[
            DetalleVentaOut(
                id=d.id,
                producto_id=d.producto_id,
                producto_nombre=d.producto.nombre,
                talla_id=d.talla_id,
                talla_codigo=d.talla.codigo,
                color_id=d.color_id,
                color_nombre=d.color.nombre,
                cantidad=d.cantidad,
                precio_unitario=d.precio_unitario,
                ya_solicitada=d.id in bloqueadas,
            )
            for d in detalles
        ],
        tiene_devolucion=ultima_dev is not None,
        estado_devolucion=ultima_dev.estado if ultima_dev else None,
        monto_devolucion=ultima_dev.monto_reembolso if ultima_dev else None,
        puede_devolver=puede_devolver,
        puede_cambiar=puede_cambiar,
        horas_restantes_devolucion=horas_restantes if (horas_transcurridas <= 24.0 and not devolucion_activa) else None,
        tienda=_tienda_factura(venta),
        metodo_pago_nombre=(venta.pago.metodo_pago.nombre if venta.pago and venta.pago.metodo_pago else None),
        motivo_rechazo=venta.pago.motivo_rechazo if venta.pago else None,
        envio=EnvioOut.model_validate(venta.envio) if venta.envio else None,
        factura_nombre=venta.factura_nombre,
        factura_nit=venta.factura_nit,
    )


def _tienda_factura(venta: Venta) -> TiendaFacturaOut | None:
    e = venta.sucursal.empresa if venta.sucursal else None
    if e is None:
        return None
    return TiendaFacturaOut(
        id=e.id,
        nombre=e.nombre,
        subdominio=e.subdominio,
        logo_url=e.logo_url,
        color_marca=e.color_marca,
        ciudad=e.ciudad,
        email_contacto=e.email_contacto,
        razon_social=e.razon_social,
        nit=e.nit,
        direccion_fiscal=e.direccion_fiscal,
        telefono=e.telefono,
    )


def _to_admin_out(venta: Venta) -> VentaAdminOut:
    # Venta de mostrador a alguien sin cuenta: se muestra el nombre que dio.
    sin_cuenta = venta.cliente.email == CONSUMIDOR_FINAL_EMAIL
    return VentaAdminOut(
        **_to_out(venta).model_dump(),
        cliente_nombre=(venta.factura_nombre or venta.cliente.nombre) if sin_cuenta else venta.cliente.nombre,
        cliente_email="Cliente sin cuenta" if sin_cuenta else venta.cliente.email,
        comprobante_url=venta.pago.comprobante_url if venta.pago else None,
    )


@router.get("/checkout/verificar-stock", response_model=list[VerificarStockItemOut])
def verificar_stock_checkout(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> list[VerificarStockItemOut]:
    """Chequeo proactivo, ANTES de pagar (pedido del usuario): antes esto
    solo se validaba recien al capturar el pago (_verificar_stock_carrito).
    Cada item del carrito ya trae SU sucursal (elegida al agregarlo, ver
    DetalleCarrito.sucursal_id) -- esto solo re-confirma que el stock siga
    estando, por si cambio desde que se agrego al carrito."""
    cliente = _get_cliente_o_403(db, usuario)
    carrito = _get_carrito_activo_no_vacio(db, cliente.id)

    resultado = []
    for d in carrito.detalles:
        inventario = (
            db.query(Inventario)
            .filter(
                Inventario.producto_id == d.producto_id,
                Inventario.talla_id == d.talla_id,
                Inventario.color_id == d.color_id,
                Inventario.sucursal_id == d.sucursal_id,
            )
            .first()
        )
        cantidad_disponible = inventario.cantidad if inventario else 0
        resultado.append(
            VerificarStockItemOut(
                detalle_id=d.id,
                producto_id=d.producto_id,
                producto_nombre=d.producto.nombre,
                talla_codigo=d.talla.codigo,
                color_nombre=d.color.nombre,
                sucursal_id=d.sucursal_id,
                sucursal_nombre=d.sucursal.nombre,
                cantidad_pedida=d.cantidad,
                cantidad_disponible=cantidad_disponible,
                disponible=cantidad_disponible >= d.cantidad,
            )
        )
    return resultado


@router.post("/checkout/paypal/crear-orden", response_model=OrdenPaypalOut)
def crear_orden_paypal(
    request: Request,
    payload: OrdenPaypalIn | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> OrdenPaypalOut:
    """Solo crea la orden en PayPal para que el frontend abra el checkout --
    no cobra nada ni toca el carrito todavia (eso recien pasa al capturar la
    orden). Asi, si el cliente cierra el boton de PayPal sin pagar, su
    carrito sigue intacto. La llaman tanto el checkout web (JS SDK) como el
    WebView inline del checkout movil (`/paypal-embed`, ver `paypal_embed.py`)
    -- mismo request para los dos, ninguno necesita nada especial aca."""
    cliente = _get_cliente_o_403(db, usuario)
    carrito = _get_carrito_activo_no_vacio(db, cliente.id)
    total = _calcular_total(carrito)

    base = str(request.base_url).rstrip("/")
    orden = crear_orden(
        total,
        referencia=f"carrito-{carrito.id}",
        return_url=f"{base}/paypal-embed/retorno",
        cancel_url=f"{base}/paypal-embed/cancelado",
        guardar_paypal=bool(payload and payload.guardar_paypal),
    )
    approve_url = next((link["href"] for link in orden.get("links", []) if link.get("rel") in ("approve", "payer-action")), None)
    return OrdenPaypalOut(order_id=orden["id"], total=total, approve_url=approve_url)


@router.post("/checkout/paypal/capturar/{order_id}", response_model=list[VentaOut])
def capturar_orden_paypal(
    order_id: str,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> list[VentaOut]:
    """Un solo pago de PayPal puede terminar repartido en varias ventas
    (pedido del usuario): la sucursal de cada item ya quedo fija al
    agregarlo al carrito (DetalleCarrito.sucursal_id), asi que aca solo se
    agrupa por sucursal y se crea una venta por grupo -- todas fondeadas por
    la MISMA orden de PayPal (mismo order_id como referencia_externa en
    cada una)."""
    cliente = _get_cliente_o_403(db, usuario)
    carrito = _get_carrito_activo_no_vacio(db, cliente.id)
    total = _calcular_total(carrito)

    _verificar_stock_carrito(db, carrito)

    # 1) Antes de cobrar: la orden tiene que ser de ESTE carrito y por el
    # total vigente. Sin esto se podia crear la orden con un carrito barato,
    # agregar productos y capturar -- se registraban ventas por todo el
    # carrito pero PayPal cobraba solo el monto original.
    orden = obtener_orden(order_id)
    unidad = (orden.get("purchase_units") or [{}])[0]
    if unidad.get("reference_id") != f"carrito-{carrito.id}" or not _monto_coincide(unidad.get("amount"), total):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Tu carrito cambio desde que iniciaste el pago. Vuelve a iniciar el pago con PayPal.",
        )

    # 2) Se registran las ventas SIN confirmar la transaccion: si falta stock
    # (sp_* valida con FOR UPDATE) se aborta aca, antes de cobrar nada.
    venta_ids = []
    try:
        for sucursal_id, detalles in _agrupar_por_sucursal(carrito.detalles).items():
            result = db.execute(
                text(
                    "SELECT sp_crear_venta_digital_paypal(:cliente_id, :sucursal_id, :carrito_id, CAST(:items AS JSONB), :referencia)"
                ),
                {
                    "cliente_id": cliente.id,
                    "sucursal_id": sucursal_id,
                    "carrito_id": carrito.id,
                    "items": _items_json(detalles),
                    "referencia": order_id,
                },
            )
            venta_ids.append(result.scalar_one())
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)

    # 3) Recien ahora se cobra. Si PayPal falla, se deshacen las ventas.
    try:
        resultado = capturar_orden(order_id)
    except HTTPException:
        db.rollback()
        raise
    captura = captura_de(resultado)
    if resultado.get("status") != "COMPLETED" or captura is None:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "PayPal no confirmo el pago.")
    if not _monto_coincide(captura.get("amount"), total):
        db.rollback()
        _reembolsar_o_loguear(captura, order_id, "el monto cobrado no coincide con el carrito")
        raise HTTPException(status.HTTP_409_CONFLICT, "El monto cobrado no coincide con tu carrito. Se revirtio el cobro.")

    # 4) Confirmar. Si justo aca falla la base, el cobro ya ocurrio: se
    # devuelve para no dejar un pago sin venta.
    try:
        db.commit()
    except Exception:
        db.rollback()
        _reembolsar_o_loguear(captura, order_id, "no se pudo guardar la venta")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No se pudo registrar tu compra. El cobro fue revertido; intenta de nuevo.",
        )

    registrar_paypal_usado(db, cliente.id, resultado)
    for venta_id in venta_ids:
        log_bitacora(db, usuario, "CREAR", "venta", venta_id, f"Venta digital pagada con PayPal (orden {order_id})", request)

    ventas = _query_venta_con_detalles(db).filter(Venta.id.in_(venta_ids)).all()
    return [_to_out(v) for v in ventas]


@router.post("/checkout/qr", response_model=list[VentaOut], status_code=status.HTTP_201_CREATED)
async def checkout_qr(
    request: Request,
    file: UploadFile = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> list[VentaOut]:
    """Pago por QR: no hay pasarela que lo verifique solo, asi que el
    cliente sube la foto del comprobante y la(s) venta(s) quedan pendientes
    de que un cajero/encargado las revise (el stock recien se descuenta
    cuando se aprueba, no aca). Si el carrito tiene items de mas de una
    sucursal, se crea una venta por sucursal, todas apuntando a la MISMA
    foto de comprobante -- cada sucursal revisa su propia parte."""
    cliente = _get_cliente_o_403(db, usuario)
    carrito = _get_carrito_activo_no_vacio(db, cliente.id)

    if file is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Debes subir una foto del comprobante.")

    content = await file.read()
    comprobante_url = upload_comprobante_pago(cliente.id, content, file.content_type or "")

    venta_ids = []
    try:
        for sucursal_id, detalles in _agrupar_por_sucursal(carrito.detalles).items():
            result = db.execute(
                text("SELECT sp_crear_venta_digital_qr(:cliente_id, :sucursal_id, :carrito_id, CAST(:items AS JSONB), :comprobante)"),
                {
                    "cliente_id": cliente.id,
                    "sucursal_id": sucursal_id,
                    "carrito_id": carrito.id,
                    "items": _items_json(detalles),
                    "comprobante": comprobante_url,
                },
            )
            venta_ids.append(result.scalar_one())
        db.commit()
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)

    for venta_id in venta_ids:
        log_bitacora(db, usuario, "CREAR", "venta", venta_id, "Venta digital con comprobante QR pendiente de verificacion", request)

    ventas = _query_venta_con_detalles(db).filter(Venta.id.in_(venta_ids)).all()
    return [_to_out(v) for v in ventas]


# ------------------------------------------------- checkout por tienda
# Cada tienda cobra en SU cuenta: el carrito se paga por partes, una por
# tienda, con los metodos que esa tienda registro.


def _tienda_del_carrito(carrito: Carrito, empresa_id: int) -> list[DetalleCarrito]:
    detalles = [d for d in carrito.detalles if d.producto.empresa_id == empresa_id]
    if not detalles:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No tienes productos de esta tienda en tu carrito.")
    return detalles


def _total_de(detalles: list[DetalleCarrito]) -> Decimal:
    return sum((d.producto.precio * d.cantidad for d in detalles), Decimal("0")).quantize(Decimal("0.01"))


def _a_usd(db: Session, bob: Decimal) -> tuple[Decimal, Decimal]:
    """PayPal no cobra en Bs: se cobra en US$ al cambio oficial (igual que las
    suscripciones). Devuelve (monto en US$, tipo de cambio)."""
    tc = Decimal(db.execute(text("SELECT fn_tipo_cambio_oficial()")).scalar())
    return (bob / tc).quantize(Decimal("0.01"), ROUND_HALF_UP), tc


def _validar_direccion(db: Session, cliente_id: int, direccion_id: int | None) -> None:
    # Antes de cobrar: la direccion de envio debe ser del cliente.
    if direccion_id is not None and not db.execute(
        text("SELECT 1 FROM direccion_cliente WHERE id = :d AND cliente_id = :c"), {"d": direccion_id, "c": cliente_id}
    ).first():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Elige una de tus direcciones para el envío.")


def _guardar_envio(db: Session, venta_ids: list[int], cliente_id: int, direccion_id: int | None) -> None:
    # Envio a domicilio: copia de la direccion en cada venta (sin direccion = recojo).
    if direccion_id is not None:
        from app.api.v1.endpoints.direcciones import guardar_envio

        guardar_envio(db, venta_ids, cliente_id, direccion_id)


def _guardar_captura(db: Session, venta_ids: list[int], capture_id: str) -> None:
    # Con el id de la captura se puede reembolsar despues (devoluciones).
    db.execute(
        text(
            "UPDATE transaccion SET captura_id = :c WHERE pago_id IN (SELECT id FROM pago WHERE venta_id = ANY(:v))"
        ),
        {"c": capture_id, "v": venta_ids},
    )


def _paypal_de_tienda(db: Session, empresa_id: int) -> tuple[MetodoPagoEmpresa, CuentaPaypal]:
    metodo = (
        db.query(MetodoPagoEmpresa)
        .filter(
            MetodoPagoEmpresa.empresa_id == empresa_id,
            MetodoPagoEmpresa.tipo == "paypal",
            MetodoPagoEmpresa.activo.is_(True),
        )
        .first()
    )
    secreto = descifrar(metodo.paypal_secret_cifrado) if metodo and metodo.paypal_secret_cifrado else None
    if metodo is None or not secreto:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta tienda no recibe pagos con PayPal. Elige otro método.")
    return metodo, CuentaPaypal(metodo.paypal_client_id, secreto, metodo.paypal_modo or "sandbox")


def _crear_ventas_tienda(
    db: Session,
    cliente_id: int,
    carrito: Carrito,
    detalles: list[DetalleCarrito],
    metodo_id: int,
    referencia: str | None,
    comprobante: str | None,
) -> list[int]:
    venta_ids = []
    for sucursal_id, grupo in _agrupar_por_sucursal(detalles).items():
        result = db.execute(
            text(
                "SELECT sp_crear_venta_tienda(:cliente_id, :sucursal_id, :carrito_id, CAST(:items AS JSONB), "
                ":detalle_ids, :metodo_id, :referencia, :comprobante)"
            ),
            {
                "cliente_id": cliente_id,
                "sucursal_id": sucursal_id,
                "carrito_id": carrito.id,
                "items": _items_json(grupo),
                "detalle_ids": [d.id for d in grupo],
                "metodo_id": metodo_id,
                "referencia": referencia,
                "comprobante": comprobante,
            },
        )
        venta_ids.append(result.scalar_one())
    return venta_ids


@router.get("/checkout/tiendas", response_model=list[TiendaCheckoutOut])
def checkout_por_tienda(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> list[TiendaCheckoutOut]:
    """El carrito separado por tienda, cada parte con sus metodos de pago."""
    cliente = _get_cliente_o_403(db, usuario)
    carrito = (
        db.query(Carrito)
        .options(
            joinedload(Carrito.detalles).joinedload(DetalleCarrito.producto).joinedload(Producto.empresa),
            joinedload(Carrito.detalles).joinedload(DetalleCarrito.producto).joinedload(Producto.imagenes),
            joinedload(Carrito.detalles).joinedload(DetalleCarrito.talla),
            joinedload(Carrito.detalles).joinedload(DetalleCarrito.color),
            joinedload(Carrito.detalles).joinedload(DetalleCarrito.sucursal),
        )
        .filter(Carrito.cliente_id == cliente.id, Carrito.estado == "activo")
        .first()
    )
    if carrito is None or not carrito.detalles:
        return []

    grupos: dict[int, list[DetalleCarrito]] = {}
    for d in carrito.detalles:
        grupos.setdefault(d.producto.empresa_id, []).append(d)
    operativas = {
        fila.id: fila.operativa
        for fila in db.execute(
            text("SELECT id, fn_empresa_operativa(id) AS operativa FROM empresa WHERE id = ANY(:ids)"),
            {"ids": list(grupos)},
        )
    }
    metodos: dict[int, list[MetodoPagoEmpresa]] = {}
    for m in (
        db.query(MetodoPagoEmpresa)
        .filter(
            MetodoPagoEmpresa.empresa_id.in_(list(grupos)),
            MetodoPagoEmpresa.activo.is_(True),
            # Contra entrega es solo para compras hechas sin conexion.
            MetodoPagoEmpresa.tipo != "contra_entrega",
        )
        .order_by(MetodoPagoEmpresa.orden, MetodoPagoEmpresa.id)
    ):
        metodos.setdefault(m.empresa_id, []).append(m)

    resultado = []
    for empresa_id, detalles in grupos.items():
        e = detalles[0].producto.empresa
        propios = metodos.get(empresa_id, [])
        resultado.append(
            TiendaCheckoutOut(
                empresa_id=empresa_id,
                nombre=e.nombre,
                subdominio=e.subdominio,
                logo_url=e.logo_url,
                color_marca=e.color_marca,
                operativa=bool(operativas.get(empresa_id)),
                items=[
                    ItemCheckoutOut(
                        detalle_id=d.id,
                        producto_id=d.producto_id,
                        producto_nombre=d.producto.nombre,
                        imagen_url=(sorted(d.producto.imagenes, key=lambda i: i.orden)[0].url if d.producto.imagenes else None),
                        talla_codigo=d.talla.codigo,
                        color_nombre=d.color.nombre,
                        sucursal_id=d.sucursal_id,
                        sucursal_nombre=d.sucursal.nombre,
                        cantidad=d.cantidad,
                        precio_unitario=d.producto.precio,
                        subtotal=(d.producto.precio * d.cantidad).quantize(Decimal("0.01")),
                    )
                    for d in detalles
                ],
                total=_total_de(detalles),
                total_usd=_a_usd(db, _total_de(detalles))[0],
                metodos=[MetodoPagoPublicoOut(**metodo_publico_cobro(m)) for m in propios],
                acepta_pagar_todo=any(m.tipo == "paypal" and m.paypal_email for m in propios),
            )
        )
    return sorted(resultado, key=lambda t: t.nombre)


# --------------------------------------------------------- "Pagar todo"
# El cliente paga el carrito completo (varias tiendas) en un solo cobro con
# el PayPal de Arlani. Se registra una venta por tienda y sucursal, y a cada
# tienda se le envia al instante lo suyo menos la comision (liquidacion).


def _grupos_pagar_todo(db: Session, carrito: Carrito) -> dict[int, tuple[MetodoPagoEmpresa, list[DetalleCarrito]]]:
    grupos: dict[int, list[DetalleCarrito]] = {}
    for d in carrito.detalles:
        grupos.setdefault(d.producto.empresa_id, []).append(d)
    if len(grupos) < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pagar todo es para carritos con prendas de varias tiendas.")
    resultado = {}
    for empresa_id, detalles in grupos.items():
        metodo = (
            db.query(MetodoPagoEmpresa)
            .filter(
                MetodoPagoEmpresa.empresa_id == empresa_id,
                MetodoPagoEmpresa.tipo == "paypal",
                MetodoPagoEmpresa.activo.is_(True),
                MetodoPagoEmpresa.paypal_email.isnot(None),
            )
            .first()
        )
        if metodo is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Una de las tiendas de tu carrito no recibe pagos con PayPal: págala por separado.",
            )
        resultado[empresa_id] = (metodo, detalles)
    return resultado


def _total_usd_pagar_todo(db: Session, grupos: dict[int, tuple[MetodoPagoEmpresa, list[DetalleCarrito]]]) -> tuple[Decimal, Decimal]:
    # Suma de lo de cada tienda ya convertido (igual que lo muestra el checkout).
    partes = [_a_usd(db, _total_de(detalles)) for _, detalles in grupos.values()]
    return sum((usd for usd, _ in partes), Decimal("0")), partes[0][1]


@router.post("/checkout/todo/paypal/orden", response_model=OrdenPaypalOut)
def crear_orden_pagar_todo(
    request: Request,
    payload: OrdenPaypalIn | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> OrdenPaypalOut:
    cliente = _get_cliente_o_403(db, usuario)
    carrito = _get_carrito_activo_no_vacio(db, cliente.id)
    total_usd, _ = _total_usd_pagar_todo(db, _grupos_pagar_todo(db, carrito))
    base = str(request.base_url).rstrip("/")
    orden = crear_orden(
        total_usd,
        referencia=f"carrito-{carrito.id}-todo",
        return_url=f"{base}/paypal-embed/retorno",
        cancel_url=f"{base}/paypal-embed/cancelado",
        guardar_paypal=bool(payload and payload.guardar_paypal),
    )
    approve_url = next((link["href"] for link in orden.get("links", []) if link.get("rel") in ("approve", "payer-action")), None)
    return OrdenPaypalOut(order_id=orden["id"], total=total_usd, approve_url=approve_url)


@router.post("/checkout/todo/paypal/capturar/{order_id}", response_model=list[VentaOut])
def capturar_pagar_todo(
    order_id: str,
    request: Request,
    direccion_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> list[VentaOut]:
    cliente = _get_cliente_o_403(db, usuario)
    _validar_direccion(db, cliente.id, direccion_id)
    carrito = _get_carrito_activo_no_vacio(db, cliente.id)
    grupos = _grupos_pagar_todo(db, carrito)
    total_usd, tc = _total_usd_pagar_todo(db, grupos)

    orden = obtener_orden(order_id)
    unidad = (orden.get("purchase_units") or [{}])[0]
    if unidad.get("reference_id") != f"carrito-{carrito.id}-todo" or not _monto_coincide(unidad.get("amount"), total_usd):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Tu carrito cambió desde que iniciaste el pago. Vuelve a iniciar el pago con PayPal.",
        )

    # 1) Ventas de cada tienda (sin confirmar): si falta stock no se cobra.
    ventas_por_tienda: dict[int, list[int]] = {}
    try:
        for empresa_id, (metodo, detalles) in grupos.items():
            ventas_por_tienda[empresa_id] = _crear_ventas_tienda(
                db, cliente.id, carrito, detalles, metodo.id, order_id, None
            )
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)

    # 2) Cobro unico con el PayPal de Arlani.
    try:
        resultado = capturar_orden(order_id)
    except HTTPException:
        db.rollback()
        raise
    captura = captura_de(resultado)
    if resultado.get("status") != "COMPLETED" or captura is None:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "PayPal no confirmó el pago.")
    if not _monto_coincide(captura.get("amount"), total_usd):
        db.rollback()
        _reembolsar_o_loguear(captura, order_id, "monto distinto en Pagar todo")
        raise HTTPException(status.HTTP_409_CONFLICT, "El monto cobrado no coincide con tu carrito. Se revirtió el cobro.")

    # 3) Liquidacion de cada tienda (comision retenida) y confirmacion.
    todas = [v for ids in ventas_por_tienda.values() for v in ids]
    try:
        _guardar_captura(db, todas, captura["id"])
        _guardar_envio(db, todas, cliente.id, direccion_id)
        liquidaciones = [
            db.execute(
                text("SELECT sp_registrar_liquidacion(:e, :orden, :captura, :ventas, :tc)"),
                {"e": empresa_id, "orden": order_id, "captura": captura["id"], "ventas": ids, "tc": tc},
            ).scalar_one()
            for empresa_id, ids in ventas_por_tienda.items()
        ]
        db.commit()
    except Exception:
        db.rollback()
        _reembolsar_o_loguear(captura, order_id, "no se pudo registrar Pagar todo")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No se pudo registrar tu compra. El cobro fue revertido; intenta de nuevo.",
        )

    registrar_paypal_usado(db, cliente.id, resultado)
    for venta_id in todas:
        log_bitacora(db, usuario, "CREAR", "venta", venta_id, f"Venta digital pagada con Pagar todo (orden {order_id})", request)

    # 4) Envio inmediato a cada tienda. Si PayPal falla, queda para reintentar:
    # la compra del cliente ya esta confirmada.
    try:
        enviar_liquidaciones(db, liquidaciones)
    except Exception:
        db.rollback()
        logger.exception("No se pudieron enviar las liquidaciones %s (orden %s)", liquidaciones, order_id)

    ventas = _query_venta_con_detalles(db).filter(Venta.id.in_(todas)).all()
    return [_to_out(v) for v in ventas]


def metodo_publico_cobro(m: MetodoPagoEmpresa) -> dict:
    """El metodo como lo ve el cliente al pagar: el PayPal de una tienda que
    cobra Arlani (ver _cobro_de_tienda) usa los botones de Arlani."""
    from app.api.v1.endpoints.metodos_pago import _publico

    datos = _publico(m)
    if m.tipo == "paypal" and m.paypal_email and settings.PAYPAL_CLIENT_ID:
        datos["paypal_client_id"] = settings.PAYPAL_CLIENT_ID
    return datos


def _cobro_de_tienda(db: Session, empresa_id: int) -> tuple[MetodoPagoEmpresa, CuentaPaypal | None]:
    """Quien cobra el PayPal de una tienda en el checkout: Arlani (cuenta
    None) si la tienda tiene su correo PayPal para recibir la liquidacion
    (como "Pagar todo"); asi la cuenta del cliente queda autorizada para
    comprar sin conexion en cualquier tienda. Si no, su propia cuenta."""
    metodo = (
        db.query(MetodoPagoEmpresa)
        .filter(
            MetodoPagoEmpresa.empresa_id == empresa_id,
            MetodoPagoEmpresa.tipo == "paypal",
            MetodoPagoEmpresa.activo.is_(True),
            MetodoPagoEmpresa.paypal_email.isnot(None),
        )
        .first()
    )
    if metodo is not None and settings.PAYPAL_CLIENT_ID:
        return metodo, None
    return _paypal_de_tienda(db, empresa_id)


@router.post("/checkout/tienda/{empresa_id}/paypal/orden", response_model=OrdenPaypalOut)
def crear_orden_paypal_tienda(
    empresa_id: int,
    request: Request,
    payload: OrdenPaypalIn | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> OrdenPaypalOut:
    """Orden de PayPal por lo de UNA tienda (la cobra Arlani o la tienda,
    ver _cobro_de_tienda)."""
    cliente = _get_cliente_o_403(db, usuario)
    carrito = _get_carrito_activo_no_vacio(db, cliente.id, empresa_id)
    detalles = _tienda_del_carrito(carrito, empresa_id)
    _, cuenta = _cobro_de_tienda(db, empresa_id)
    total_usd, _ = _a_usd(db, _total_de(detalles))
    base = str(request.base_url).rstrip("/")
    orden = crear_orden(
        total_usd,
        referencia=f"carrito-{carrito.id}-e{empresa_id}",
        return_url=f"{base}/paypal-embed/retorno",
        cancel_url=f"{base}/paypal-embed/cancelado",
        cuenta=cuenta,
        guardar_paypal=bool(payload and payload.guardar_paypal),
    )
    approve_url = next((link["href"] for link in orden.get("links", []) if link.get("rel") in ("approve", "payer-action")), None)
    return OrdenPaypalOut(order_id=orden["id"], total=total_usd, approve_url=approve_url)


@router.post("/checkout/tienda/{empresa_id}/paypal/capturar/{order_id}", response_model=list[VentaOut])
def capturar_orden_paypal_tienda(
    empresa_id: int,
    order_id: str,
    request: Request,
    direccion_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> list[VentaOut]:
    """Cobra lo de la tienda y registra sus ventas (una por sucursal). Si lo
    cobro Arlani, a la tienda se le liquida lo suyo al instante (como en
    "Pagar todo"). Lo de otras tiendas sigue en el carrito."""
    cliente = _get_cliente_o_403(db, usuario)
    _validar_direccion(db, cliente.id, direccion_id)
    carrito = _get_carrito_activo_no_vacio(db, cliente.id, empresa_id)
    detalles = _tienda_del_carrito(carrito, empresa_id)
    metodo, cuenta = _cobro_de_tienda(db, empresa_id)
    total, tc = _a_usd(db, _total_de(detalles))

    orden = obtener_orden(order_id, cuenta)
    unidad = (orden.get("purchase_units") or [{}])[0]
    if unidad.get("reference_id") != f"carrito-{carrito.id}-e{empresa_id}" or not _monto_coincide(unidad.get("amount"), total):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Tu carrito cambió desde que iniciaste el pago. Vuelve a iniciar el pago con PayPal.",
        )

    try:
        venta_ids = _crear_ventas_tienda(db, cliente.id, carrito, detalles, metodo.id, order_id, None)
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)

    try:
        resultado = capturar_orden(order_id, cuenta)
    except HTTPException:
        db.rollback()
        raise
    captura = captura_de(resultado)
    if resultado.get("status") != "COMPLETED" or captura is None:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "PayPal no confirmó el pago.")
    if not _monto_coincide(captura.get("amount"), total):
        db.rollback()
        reembolsar_captura(captura["id"], cuenta)
        raise HTTPException(status.HTTP_409_CONFLICT, "El monto cobrado no coincide con tu carrito. Se revirtió el cobro.")
    liquidacion = None
    try:
        _guardar_captura(db, venta_ids, captura["id"])
        _guardar_envio(db, venta_ids, cliente.id, direccion_id)
        if cuenta is None:
            liquidacion = db.execute(
                text("SELECT sp_registrar_liquidacion(:e, :orden, :captura, :ventas, :tc)"),
                {"e": empresa_id, "orden": order_id, "captura": captura["id"], "ventas": venta_ids, "tc": tc},
            ).scalar_one()
        db.commit()
    except Exception:
        db.rollback()
        reembolsar_captura(captura["id"], cuenta)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No se pudo registrar tu compra. El cobro fue revertido; intenta de nuevo.",
        )

    # Cobrado por Arlani: la cuenta del cliente queda autorizada en todas las tiendas.
    registrar_paypal_usado(db, cliente.id, resultado, empresa_id if cuenta is not None else None)
    if liquidacion is not None:
        try:
            enviar_liquidaciones(db, [liquidacion])
        except Exception:
            db.rollback()
            logger.exception("No se pudo enviar la liquidacion %s (orden %s)", liquidacion, order_id)
    for venta_id in venta_ids:
        log_bitacora(db, usuario, "CREAR", "venta", venta_id, f"Venta digital pagada con PayPal de la tienda (orden {order_id})", request)
    ventas = _query_venta_con_detalles(db).filter(Venta.id.in_(venta_ids)).all()
    return [_to_out(v) for v in ventas]


@router.post("/checkout/tienda/{empresa_id}/comprobante", response_model=list[VentaOut], status_code=status.HTTP_201_CREATED)
async def checkout_tienda_comprobante(
    empresa_id: int,
    request: Request,
    metodo_pago_id: int = Form(...),
    direccion_id: int | None = Form(default=None),
    file: UploadFile = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> list[VentaOut]:
    """QR, transferencia u otro: el cliente sube su comprobante y las ventas
    quedan pendientes hasta que el personal de la tienda las apruebe."""
    cliente = _get_cliente_o_403(db, usuario)
    _validar_direccion(db, cliente.id, direccion_id)
    carrito = _get_carrito_activo_no_vacio(db, cliente.id, empresa_id)
    detalles = _tienda_del_carrito(carrito, empresa_id)
    metodo = db.query(MetodoPagoEmpresa).filter(
        MetodoPagoEmpresa.id == metodo_pago_id,
        MetodoPagoEmpresa.empresa_id == empresa_id,
        MetodoPagoEmpresa.activo.is_(True),
    ).first()
    if metodo is None or metodo.tipo in ("paypal", "contra_entrega"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese método de pago no está disponible para esta tienda.")
    if file is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sube la foto de tu comprobante de pago.")
    content = await file.read()
    comprobante_url = upload_comprobante_pago(cliente.id, content, file.content_type or "")

    try:
        venta_ids = _crear_ventas_tienda(db, cliente.id, carrito, detalles, metodo.id, None, comprobante_url)
        _guardar_envio(db, venta_ids, cliente.id, direccion_id)
        db.commit()
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)

    for venta_id in venta_ids:
        log_bitacora(db, usuario, "CREAR", "venta", venta_id, f"Venta digital con comprobante ({metodo.nombre}) pendiente de revisión", request)
    ventas = _query_venta_con_detalles(db).filter(Venta.id.in_(venta_ids)).all()
    return [_to_out(v) for v in ventas]


@router.get("/mias", response_model=list[VentaOut])
def mis_ventas(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> list[VentaOut]:
    cliente = _get_cliente_o_403(db, usuario)
    ventas = (
        _query_venta_con_detalles(db)
        .filter(Venta.cliente_id == cliente.id)
        .order_by(Venta.fecha.desc())
        .all()
    )
    return [_to_out(v) for v in ventas]


@router.get("/mias/{venta_id}", response_model=VentaOut)
def mi_venta_detalle(
    venta_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU11")),
) -> VentaOut:
    """Detalle de una compra propia -- usado por la pantalla de comprobante
    descargable/imprimible en 'Mis compras'."""
    cliente = _get_cliente_o_403(db, usuario)
    venta = (
        _query_venta_con_detalles(db)
        .filter(Venta.id == venta_id, Venta.cliente_id == cliente.id)
        .first()
    )
    if venta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compra no encontrada.")
    return _to_out(venta)


# ---------- Staff: Administrador, Encargado de Sucursal, Cajero (CU11) ----------
# CU11 "Gestion de Ventas": panel financiero de staff -- reune las ventas
# digitales (PayPal y QR) y las de mostrador en un solo lugar, deja aprobar
# o rechazar los comprobantes QR pendientes, y permite registrar una venta
# presencial en efectivo. Permiso CU11 ("Gestion de Ventas" despues de la
# renumeracion de a1c5f7e93d02 -- antes era CU14, que ahora es "Enviar
# Notificaciones" y por eso ya no se acepta aca). Encargado y Cajero solo
# operan sobre ventas de SU sucursal (ver deps.sucursal_restringida).


def _get_venta_staff_o_404(db: Session, usuario: Usuario, venta_id: int) -> Venta:
    venta = _query_venta_con_detalles(db).filter(Venta.id == venta_id).first()
    if venta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venta no encontrada.")
    verificar_acceso_sucursal(usuario, venta.sucursal_id)
    return venta


def _tiene_devoluciones_vigentes(venta: Venta) -> bool:
    return any(d.estado != "rechazada" for d in venta.devoluciones)


@router.get("", response_model=VentaPage)
def listar_ventas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tipo: str | None = Query(default=None),
    metodo: str | None = Query(default=None),
    estado_pago: str | None = Query(default=None),
    sucursal_id: int | None = Query(default=None),
    # 'online' (con conexion) u 'offline' (sincronizadas, CU12).
    origen: str | None = Query(default=None, pattern=r"^(online|offline)$"),
    db: Session = Depends(get_db),
    empleado: Usuario = Depends(require_permiso("CU11")),
) -> VentaPage:
    query = _query_venta_con_detalles(db)
    if tipo:
        query = query.filter(Venta.tipo == tipo)
    if origen:
        query = query.filter(Venta.origen == origen)
    restringida = sucursal_restringida(empleado)
    if restringida is not None:
        query = query.filter(Venta.sucursal_id == restringida)
    if sucursal_id:
        query = query.filter(Venta.sucursal_id == sucursal_id)
    if metodo or estado_pago:
        query = query.join(Pago, Pago.venta_id == Venta.id)
        if metodo:
            query = query.filter(Pago.metodo == metodo)
        if estado_pago:
            query = query.filter(Pago.estado == estado_pago)

    total = query.count()
    rows = query.order_by(Venta.fecha.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return VentaPage(items=[_to_admin_out(v) for v in rows], total=total, page=page, page_size=page_size)


@router.get("/origenes")
def origenes_habilitados(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU10", "CU11")),
) -> dict:
    """Si la tienda separa sus ventas y reservas en ONLINE / OFFLINE: solo
    con un plan que incluya la operacion sin conexion (Basico y Profesional;
    el de Prueba no). Vale para el personal de la tienda y para el
    SuperAdministrador mirando una tienda (X-Empresa)."""
    empresa_id = usuario.empresa_id if usuario.empresa_id is not None else db.info.get("empresa_scope")
    if empresa_id is None:
        return {"offline": False, "plan": None}
    fila = db.execute(
        text(
            "SELECT p.nombre, p.operacion_offline FROM suscripcion s JOIN plan_suscripcion p ON p.id = s.plan_id "
            "WHERE s.empresa_id = :e AND s.estado = 'activa'"
        ),
        {"e": empresa_id},
    ).first()
    return {"offline": bool(fila and fila.operacion_offline), "plan": fila.nombre if fila else None}


@router.get("/{venta_id}", response_model=VentaAdminOut)
def obtener_venta(
    venta_id: int,
    db: Session = Depends(get_db),
    empleado: Usuario = Depends(require_permiso("CU11")),
) -> VentaAdminOut:
    """Detalle de una venta (no solo las propias) -- usado por la pantalla
    de factura/comprobante que ve el staff desde el panel de Gestion de
    Ventas."""
    venta = _get_venta_staff_o_404(db, empleado, venta_id)
    return _to_admin_out(venta)


@router.post("/{venta_id}/aprobar-pago", response_model=VentaAdminOut)
@router.post("/{venta_id}/aprobar-qr", response_model=VentaAdminOut)
def aprobar_pago_qr(
    venta_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> VentaAdminOut:
    empleado = _get_empleado_o_403(db, usuario)
    venta = _get_venta_staff_o_404(db, usuario, venta_id)
    if venta.pago is None or venta.pago.metodo == "paypal" or venta.pago.estado != "verificando":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta venta no tiene un comprobante pendiente de revisión.")

    for d in venta.detalles:
        inventario = (
            db.query(Inventario)
            .filter(
                Inventario.producto_id == d.producto_id,
                Inventario.talla_id == d.talla_id,
                Inventario.color_id == d.color_id,
                Inventario.sucursal_id == venta.sucursal_id,
            )
            .first()
        )
        if inventario is None or inventario.cantidad < d.cantidad:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f'No hay suficiente stock de "{d.producto.nombre}" ({d.talla.codigo}, {d.color.nombre}) para aprobar esta venta.',
            )

    try:
        db.execute(
            text("SELECT sp_aprobar_pago_comprobante(:venta_id, :empleado_id)"),
            {"venta_id": venta_id, "empleado_id": empleado.id},
        )
        db.commit()
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)

    log_bitacora(db, usuario, "ACTUALIZAR", "venta", venta.id, f"Pago aprobado ({venta.pago.metodo})", request)

    venta = _query_venta_con_detalles(db).filter(Venta.id == venta.id).first()
    return _to_admin_out(venta)


@router.post("/{venta_id}/envio", response_model=VentaAdminOut)
def actualizar_envio(
    venta_id: int,
    payload: EnvioEstadoIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> VentaAdminOut:
    """El personal marca el envio a domicilio: enviado o entregado."""
    venta = _query_venta_con_detalles(db).filter(Venta.id == venta_id).first()
    if venta is None or venta.envio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esta venta no tiene envío a domicilio.")
    verificar_acceso_sucursal(usuario, venta.sucursal_id)
    venta.envio.estado = payload.estado
    venta.envio.actualizado_en = datetime.utcnow()
    db.commit()
    log_bitacora(db, usuario, "ACTUALIZAR", "venta", venta_id, f"Envío a domicilio: {payload.estado}", request)
    venta = _query_venta_con_detalles(db).filter(Venta.id == venta_id).first()
    return _to_admin_out(venta)


@router.post("/{venta_id}/contra-entrega/{accion}", response_model=VentaAdminOut)
def contra_entrega(
    venta_id: int,
    accion: str,
    request: Request,
    motivo: str | None = Body(default=None, embed=True, max_length=500),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> VentaAdminOut:
    """Compra sin conexion pagada contra entrega: el personal marca que cobro
    al entregar (cobrar) o la anula si no se entrego (el stock vuelve)."""
    if accion not in ("cobrar", "anular"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Acción no válida.")
    empleado = _get_empleado_o_403(db, usuario)
    venta = _get_venta_staff_o_404(db, usuario, venta_id)
    if venta.pago is None or venta.pago.metodo != "contra_entrega" or venta.pago.estado != "pendiente":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta venta no tiene un cobro contra entrega pendiente.")
    motivo = (motivo or "").strip() or "No se entregó la compra."
    try:
        if accion == "cobrar":
            db.execute(text("SELECT sp_cobrar_contra_entrega(:v, :e)"), {"v": venta_id, "e": empleado.id})
        else:
            db.execute(text("SELECT sp_anular_contra_entrega(:v, :e, :m)"), {"v": venta_id, "e": empleado.id, "m": motivo})
        db.commit()
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)
    detalle = "Cobro contra entrega registrado" if accion == "cobrar" else f"Compra contra entrega anulada: {motivo}"
    log_bitacora(db, usuario, "ACTUALIZAR", "venta", venta_id, detalle, request)
    venta = _query_venta_con_detalles(db).filter(Venta.id == venta_id).first()
    return _to_admin_out(venta)


@router.post("/{venta_id}/rechazar-pago", response_model=VentaAdminOut)
@router.post("/{venta_id}/rechazar-qr", response_model=VentaAdminOut)
def rechazar_pago_qr(
    venta_id: int,
    request: Request,
    payload: RechazoPagoIn | None = Body(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> VentaAdminOut:
    empleado = _get_empleado_o_403(db, usuario)
    venta = _get_venta_staff_o_404(db, usuario, venta_id)
    if venta.pago is None or venta.pago.metodo == "paypal" or venta.pago.estado != "verificando":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta venta no tiene un comprobante pendiente de revisión.")
    motivo = payload.motivo.strip() if payload else "El comprobante no es válido."

    try:
        db.execute(
            text("SELECT sp_rechazar_pago_comprobante(:venta_id, :empleado_id, :motivo)"),
            {"venta_id": venta_id, "empleado_id": empleado.id, "motivo": motivo},
        )
        db.commit()
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)

    log_bitacora(db, usuario, "ACTUALIZAR", "venta", venta.id, f"Pago rechazado: {motivo}", request)

    venta = _query_venta_con_detalles(db).filter(Venta.id == venta.id).first()
    return _to_admin_out(venta)


@router.get("/clientes/buscar", response_model=list[ClienteBusquedaOut])
def buscar_clientes_para_venta(
    buscar: str = Query(min_length=1),
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU11")),
) -> list[ClienteBusquedaOut]:
    like = f"%{buscar}%"
    clientes = (
        db.query(Cliente)
        .filter(Cliente.nombre.ilike(like) | Cliente.email.ilike(like))
        .filter(Cliente.email != CONSUMIDOR_FINAL_EMAIL)
        .order_by(Cliente.nombre)
        .limit(10)
        .all()
    )
    return [ClienteBusquedaOut(id=c.id, nombre=c.nombre, email=c.email) for c in clientes]


@router.get("/presencial/sucursales", response_model=list[dict[str, int | str]])
def sucursales_mostrador(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> list[dict[str, int | str]]:
    """Sucursales de la tienda donde el personal puede vender (Encargado y
    Cajero, solo la suya). No pide el permiso del catalogo (CU05)."""
    sql = "SELECT id, nombre FROM sucursal WHERE estado = 'activa' AND empresa_id = fn_empresa_actual()"
    params: dict = {}
    restringida = sucursal_restringida(usuario)
    if restringida is not None:
        sql += " AND id = :s"
        params["s"] = restringida
    return [dict(f) for f in db.execute(text(sql + " ORDER BY nombre"), params).mappings()]


@router.get("/presencial/catalogo", response_model=list[ProductoMostradorOut])
def catalogo_mostrador(
    sucursal_id: int = Query(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> list[ProductoMostradorOut]:
    """Prendas con stock en la sucursal (producto, precio, talla, color y
    cuantas quedan) para armar una venta de mostrador. RLS: solo las de la
    tienda del empleado."""
    verificar_acceso_sucursal(usuario, sucursal_id)
    filas = db.execute(
        text(
            """
            SELECT p.id, p.nombre, p.precio,
                   (SELECT url FROM producto_imagen pi WHERE pi.producto_id = p.id ORDER BY pi.orden LIMIT 1) AS imagen_url,
                   i.talla_id, t.codigo AS talla_codigo, i.color_id, c.nombre AS color_nombre, i.cantidad AS stock
            FROM inventario i
            JOIN producto p ON p.id = i.producto_id
            JOIN talla t ON t.id = i.talla_id
            JOIN color c ON c.id = i.color_id
            WHERE i.sucursal_id = :s AND i.cantidad > 0 AND p.estado = 'activo'
            ORDER BY p.nombre, t.id, c.nombre
            """
        ),
        {"s": sucursal_id},
    ).mappings().all()
    productos: dict[int, ProductoMostradorOut] = {}
    for f in filas:
        producto = productos.setdefault(
            f["id"],
            ProductoMostradorOut(producto_id=f["id"], nombre=f["nombre"], precio=f["precio"], imagen_url=f["imagen_url"], variantes=[]),
        )
        producto.variantes.append(
            VarianteMostradorOut(
                talla_id=f["talla_id"], talla_codigo=f["talla_codigo"], color_id=f["color_id"],
                color_nombre=f["color_nombre"], stock=f["stock"],
            )
        )
    return list(productos.values())


@router.get("/presencial/qr")
def qr_de_la_tienda(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> list[dict]:
    """QR de cobro activos de la tienda (Metodos de pago), para mostrarselo
    al cliente en el mostrador. RLS: solo los de la tienda del empleado."""
    empresa_id = usuario.empresa_id if usuario.empresa_id is not None else db.info.get("empresa_scope")
    if empresa_id is None:
        return []
    filas = db.execute(
        text(
            "SELECT id, nombre, qr_url, instrucciones, banco, titular FROM metodo_pago_empresa "
            "WHERE empresa_id = :e AND tipo = 'qr' AND activo AND qr_url IS NOT NULL ORDER BY orden, id"
        ),
        {"e": empresa_id},
    ).mappings().all()
    return [dict(f) for f in filas]


@router.post("/presencial", response_model=VentaAdminOut, status_code=status.HTTP_201_CREATED)
def registrar_venta_presencial(
    payload: VentaPresencialCreate,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> VentaAdminOut:
    """Venta de mostrador -- el staff arma la venta ahi mismo (sin pasar por
    un carrito) y se cobra al instante, en efectivo o con el QR de la tienda
    (con la foto del comprobante si la tomo). Descuenta el stock."""
    empleado = _get_empleado_o_403(db, usuario)
    verificar_acceso_sucursal(usuario, payload.sucursal_id)

    # Sin cuenta: la venta va al cliente generico "Consumidor final" y guarda
    # el nombre y el NIT/CI que dio la persona (para su factura).
    cliente_id = payload.cliente_id or db.execute(text("SELECT fn_consumidor_final()")).scalar()
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first() if cliente_id else None
    if cliente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado.")
    factura_nombre = (payload.factura_nombre or "").strip() or None
    factura_nit = (payload.factura_nit or "").strip() or None
    sucursal = db.query(Sucursal).filter(Sucursal.id == payload.sucursal_id).first()
    if sucursal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sucursal no encontrada.")

    for item in payload.items:
        producto = db.query(Producto).filter(Producto.id == item.producto_id).first()
        talla = db.query(Talla).filter(Talla.id == item.talla_id).first()
        color = db.query(Color).filter(Color.id == item.color_id).first()
        if producto is None or talla is None or color is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto, talla o color no encontrado.")
        inventario = (
            db.query(Inventario)
            .filter(
                Inventario.producto_id == item.producto_id,
                Inventario.talla_id == item.talla_id,
                Inventario.color_id == item.color_id,
                Inventario.sucursal_id == payload.sucursal_id,
            )
            .first()
        )
        if inventario is None or inventario.cantidad < item.cantidad:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f'No hay suficiente stock de "{producto.nombre}" ({talla.codigo}, {color.nombre}) en esa sucursal.',
            )

    try:
        result = db.execute(
            text("SELECT sp_crear_venta_presencial(:cliente_id, :sucursal_id, :empleado_id, CAST(:items AS JSONB))"),
            {
                "cliente_id": cliente.id,
                "sucursal_id": payload.sucursal_id,
                "empleado_id": empleado.id,
                "items": _items_json(payload.items),
            },
        )
        venta_id = result.scalar_one()
        if factura_nombre or factura_nit:
            db.execute(
                text("UPDATE venta SET factura_nombre = :n, factura_nit = :nit WHERE id = :v"),
                {"n": factura_nombre, "nit": factura_nit, "v": venta_id},
            )
        if payload.metodo_pago == "qr":
            # Cobrada con el QR de la tienda: queda pagada (el empleado lo vio
            # en el momento) con la foto del comprobante si la tomo.
            comprobante_url = None
            if payload.comprobante:
                contenido, tipo = _imagen_de_data_url(payload.comprobante)
                comprobante_url = upload_comprobante_pago(cliente.id, contenido, tipo)
            # El QR que se mostro al cliente (si no vino, el primero de la tienda).
            db.execute(
                text(
                    "UPDATE pago SET metodo = 'qr', comprobante_url = :url, revisado_por_id = :emp, "
                    "metodo_pago_id = (SELECT id FROM metodo_pago_empresa WHERE empresa_id = :e AND tipo = 'qr' "
                    "AND activo ORDER BY (id = :mid) DESC, orden, id LIMIT 1) WHERE venta_id = :v"
                ),
                {"url": comprobante_url, "emp": empleado.id, "e": sucursal.empresa_id, "v": venta_id,
                 "mid": payload.metodo_pago_id or 0},
            )
        db.commit()
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)

    forma = "con QR" + (" (con comprobante)" if payload.comprobante else "") if payload.metodo_pago == "qr" else "en efectivo"
    a_quien = factura_nombre if payload.cliente_id is None else cliente.nombre
    log_bitacora(db, usuario, "CREAR", "venta", venta_id, f"Venta presencial {forma} a {a_quien}", request)

    venta = _query_venta_con_detalles(db).filter(Venta.id == venta_id).first()
    return _to_admin_out(venta)


@router.put("/{venta_id}", response_model=VentaAdminOut)
def editar_venta(
    venta_id: int,
    payload: VentaEditIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> VentaAdminOut:
    """Edicion completa (CU11): productos, cantidades, sucursal y estado del
    pago -- por esta misma via se puede "completar" un pago QR o en
    efectivo (poniendo estado_pago='completado'), igual que con los botones
    rapidos de aprobar/rechazar QR. sp_editar_venta libera el stock viejo (si
    la venta ya estaba pagada) y retiene el nuevo dentro de la misma
    transaccion -- si no alcanza, no se confirma nada."""
    empleado = _get_empleado_o_403(db, usuario)
    venta = _get_venta_staff_o_404(db, usuario, venta_id)
    verificar_acceso_sucursal(usuario, payload.sucursal_id)

    # sp_editar_venta solo libera el stock viejo si la venta estaba 'pagada';
    # con una devolucion de por medio (devuelto/devuelto_parcial) volveria a
    # descontar stock sin liberar el anterior, y ademas borraria los
    # item_linea a los que apuntan los detalles de la devolucion.
    if _tiene_devoluciones_vigentes(venta):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Esta venta tiene una devolucion registrada y ya no se puede editar.",
        )

    sucursal = db.query(Sucursal).filter(Sucursal.id == payload.sucursal_id).first()
    if sucursal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sucursal no encontrada.")

    for item in payload.items:
        producto = db.query(Producto).filter(Producto.id == item.producto_id).first()
        talla = db.query(Talla).filter(Talla.id == item.talla_id).first()
        color = db.query(Color).filter(Color.id == item.color_id).first()
        if producto is None or talla is None or color is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto, talla o color no encontrado.")

    try:
        db.execute(
            text(
                "SELECT sp_editar_venta(:venta_id, :sucursal_id, CAST(:items AS JSONB), :metodo_pago, :estado_pago, :empleado_id)"
            ),
            {
                "venta_id": venta_id,
                "sucursal_id": payload.sucursal_id,
                "items": _items_json(payload.items),
                "metodo_pago": payload.metodo_pago,
                "estado_pago": payload.estado_pago,
                "empleado_id": empleado.id,
            },
        )
        db.commit()
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)

    log_bitacora(db, usuario, "ACTUALIZAR", "venta", venta_id, "Venta editada", request)

    venta = _query_venta_con_detalles(db).filter(Venta.id == venta_id).first()
    return _to_admin_out(venta)


@router.delete("/{venta_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_venta(
    venta_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU11")),
) -> None:
    """Borra la venta por completo. sp_eliminar_venta devuelve el stock al
    inventario si estaba retenido (estado 'pagada') antes de borrar. El
    Cajero no puede borrar ventas (solo Administrador o Encargado)."""
    require_encargado_o_admin(usuario)
    empleado = _get_empleado_o_403(db, usuario)
    venta = _get_venta_staff_o_404(db, usuario, venta_id)
    if _tiene_devoluciones_vigentes(venta):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Esta venta tiene una devolucion registrada: elimina primero la devolucion.",
        )

    cliente_nombre = venta.cliente.nombre
    try:
        db.execute(
            text("SELECT sp_eliminar_venta(:venta_id, :empleado_id)"), {"venta_id": venta_id, "empleado_id": empleado.id}
        )
        db.commit()
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)

    log_bitacora(db, usuario, "ELIMINAR", "venta", venta_id, f"Venta de {cliente_nombre} eliminada", request)
