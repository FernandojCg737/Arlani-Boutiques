"""P4 Offline y sincronizacion (CU11 a CU14 del 2do parcial).

Solo para tiendas cuyo plan incluye la operacion sin conexion (Basico y
Profesional): fn_empresa_con_offline.

- CU11: el personal descarga el paquete de su sucursal (productos,
  variantes, precios, stock y clientes); el cliente con sesion, el catalogo
  de las tiendas que trabajan sin conexion.
- CU12: el dispositivo manda las operaciones que guardo sin conexion (venta
  de contado del personal o reserva). Cada una trae su uuid: si llega dos
  veces se devuelve el mismo resultado y no se duplica.
- CU13: operaciones recibidas y su estado.
- CU14: si al llegar ya no hay stock, la operacion queda en conflicto (no se
  pierde) y el Administrador o el Encargado la ajusta o la anula.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import (
    STAFF_TIPOS,
    cliente_sin_permiso,
    get_current_user,
    require_permiso,
    sucursal_restringida,
    verificar_acceso_sucursal,
)
from app.api.v1.endpoints.metodos_pago import _publico
from app.api.v1.endpoints.paypal_guardado import token_activo
from app.api.v1.endpoints.reservas import _mover_stock_reserva
from app.api.v1.endpoints.ventas import (
    _a_usd,
    _error_sp,
    _guardar_captura,
    _guardar_envio,
    _monto_coincide,
    _paypal_de_tienda,
)
from app.core.audit import client_ip, client_platform, log_bitacora
from app.core.errores_db import http_desde_pg
from app.core.aviso_cliente import programar_correo
from app.core.liquidaciones import enviar_liquidaciones
from app.core.paypal import (
    CobroRechazado,
    captura_de,
    capturar_orden,
    cobrar_con_token,
    crear_orden,
    obtener_orden,
    reembolsar_captura,
)
from app.core.storage import upload_comprobante_pago
from app.db.session import get_db
from app.models import Bitacora, DetalleReserva, MetodoPagoEmpresa, Notificacion, Reserva, Usuario
from app.services.usuarios import codigos_permiso
from app.schemas.offline import (
    CatalogoClienteOfflineOut,
    ClienteOfflineOut,
    DireccionOfflineOut,
    ItemPedidoOut,
    PedidoOfflineOut,
    DescargaOfflineOut,
    EstadoOperacionesIn,
    ItemConflictoOut,
    ItemOfflineIn,
    OpcionesConflictoOut,
    OperacionOfflineIn,
    OperacionOfflineOut,
    PaqueteOfflineOut,
    ProductoOfflineOut,
    ResolverConflictoIn,
    ResultadoOperacionOut,
    ResumenSeguimientoOut,
    SeguimientoOfflineOut,
    SincronizarIn,
    SucursalOfflineOut,
    TiendaOfflineOut,
    UsuarioOfflineOut,
    VarianteDisponibleOut,
    VarianteOfflineOut,
)

logger = logging.getLogger(__name__)

router = APIRouter()

SIN_PLAN = "El plan de esta tienda no incluye la operación sin conexión (solo Básico y Profesional)."
# Una reserva cuya hora de recojo ya paso al sincronizar se corre a mañana.
PLAZO_RESERVA = timedelta(days=1)


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc(valor: datetime) -> datetime:
    """Fecha del dispositivo a UTC sin zona (como se guarda todo)."""
    if valor.tzinfo is not None:
        valor = valor.astimezone(timezone.utc).replace(tzinfo=None)
    # Un reloj adelantado no puede dejar operaciones "en el futuro".
    return min(valor, _ahora())


def _es_personal(usuario: Usuario) -> bool:
    return usuario.tipo in STAFF_TIPOS and usuario.tipo != "superadministrador"


def _con_offline(db: Session, empresa_id: int) -> bool:
    return bool(db.execute(text("SELECT fn_empresa_con_offline(:e)"), {"e": empresa_id}).scalar())


def _productos_de(filas) -> list[ProductoOfflineOut]:
    productos: dict[int, ProductoOfflineOut] = {}
    for f in filas:
        p = productos.setdefault(
            f["id"],
            ProductoOfflineOut(
                producto_id=f["id"], nombre=f["nombre"], precio=f["precio"], imagen_url=f["imagen_url"],
                categoria=f["categoria"], variantes=[],
            ),
        )
        p.variantes.append(
            VarianteOfflineOut(
                talla_id=f["talla_id"], talla_codigo=f["talla_codigo"], color_id=f["color_id"],
                color_nombre=f["color_nombre"], stock=f["stock"], sucursal_id=f.get("sucursal_id"),
            )
        )
    return list(productos.values())


_SQL_VARIANTES = """
    SELECT p.id, p.nombre, p.precio, cat.nombre AS categoria,
           (SELECT url FROM producto_imagen pi WHERE pi.producto_id = p.id ORDER BY pi.orden LIMIT 1) AS imagen_url,
           i.sucursal_id, i.talla_id, t.codigo AS talla_codigo, i.color_id, c.nombre AS color_nombre, i.cantidad AS stock
    FROM inventario i
    JOIN producto p ON p.id = i.producto_id
    LEFT JOIN categoria cat ON cat.id = p.categoria_id
    JOIN talla t ON t.id = i.talla_id
    JOIN color c ON c.id = i.color_id
    WHERE p.estado = 'activo'
"""


# ================================================================== CU11


def _registrar_descarga(
    db: Session, empresa_id: int, sucursal_id: int | None, usuario_id: int, tipo: str, productos: int, clientes: int
) -> None:
    """Queda quien descargo datos para trabajar sin conexion (seguimiento CU11)."""
    db.execute(
        text(
            "INSERT INTO descarga_offline (empresa_id, sucursal_id, usuario_id, tipo, productos, clientes) "
            "VALUES (:e, :s, :u, :t, :p, :c)"
        ),
        {"e": empresa_id, "s": sucursal_id, "u": usuario_id, "t": tipo, "p": productos, "c": clientes},
    )


@router.get("/paquete", response_model=PaqueteOfflineOut)
def paquete_sucursal(
    sucursal_id: int = Query(...),
    # La app lo descarga sola cada pocos minutos: esas no llenan el seguimiento.
    automatica: bool = Query(default=False),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("2P-CU11")),
) -> PaqueteOfflineOut:
    """Datos para vender y reservar sin conexion en una sucursal."""
    if not _es_personal(usuario):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El paquete sin conexión es para el personal de la tienda.")
    verificar_acceso_sucursal(usuario, sucursal_id)
    sucursal = db.execute(
        text(
            "SELECT s.id, s.nombre, e.id AS empresa_id, e.nombre AS empresa_nombre FROM sucursal s "
            "JOIN empresa e ON e.id = s.empresa_id WHERE s.id = :s AND s.estado = 'activa'"
        ),
        {"s": sucursal_id},
    ).mappings().first()
    if sucursal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sucursal no encontrada.")
    if not _con_offline(db, sucursal["empresa_id"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, SIN_PLAN)
    filas = db.execute(
        text(_SQL_VARIANTES + " AND i.sucursal_id = :s ORDER BY p.nombre, t.id, c.nombre"), {"s": sucursal_id}
    ).mappings().all()
    # Datos minimos de los clientes que ya compraron o reservaron en la tienda.
    clientes = db.execute(
        text(
            """SELECT DISTINCT u.id, u.nombre, u.email FROM usuario u
               WHERE u.tipo = 'cliente' AND u.estado = 'activo' AND u.id IN (
                   SELECT cliente_id FROM venta UNION SELECT cliente_id FROM reserva)
                 AND u.email <> 'consumidor.final@arlaniboutiques.com'
               ORDER BY u.nombre LIMIT 1000"""
        )
    ).mappings().all()
    reciente = automatica and db.execute(
        text(
            "SELECT 1 FROM descarga_offline WHERE usuario_id = :u AND sucursal_id = :s "
            "AND fecha > now() - interval '30 minutes'"
        ),
        {"u": usuario.id, "s": sucursal_id},
    ).first()
    if not reciente:
        _registrar_descarga(
            db, sucursal["empresa_id"], sucursal_id, usuario.id, "personal", len({f["id"] for f in filas}), len(clientes)
        )
        db.commit()
    return PaqueteOfflineOut(
        empresa_id=sucursal["empresa_id"],
        empresa_nombre=sucursal["empresa_nombre"],
        sucursal=SucursalOfflineOut(id=sucursal["id"], nombre=sucursal["nombre"]),
        descargado_en=_ahora(),
        productos=_productos_de(filas),
        clientes=[ClienteOfflineOut(**c) for c in clientes],
    )


@router.get("/catalogo-cliente", response_model=CatalogoClienteOfflineOut)
def catalogo_cliente(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> CatalogoClienteOfflineOut:
    """Catalogo de las tiendas que trabajan sin conexion (con stock por
    sucursal), para que el cliente lo consulte y reserve sin internet."""
    if usuario.tipo != "cliente" or cliente_sin_permiso(usuario, "CU10"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El catálogo sin conexión es para clientes con sesión.")
    tiendas = db.execute(
        text(
            "SELECT id, nombre, logo_url FROM empresa WHERE estado = 'activa' AND fn_empresa_con_offline(id) ORDER BY nombre"
        )
    ).mappings().all()
    salida = []
    for t in tiendas:
        sucursales = db.execute(
            text("SELECT id, nombre FROM sucursal WHERE empresa_id = :e AND estado = 'activa' ORDER BY nombre"),
            {"e": t["id"]},
        ).mappings().all()
        filas = db.execute(
            text(
                _SQL_VARIANTES
                + " AND i.cantidad > 0 AND i.sucursal_id IN (SELECT id FROM sucursal WHERE empresa_id = :e AND estado = 'activa')"
                " ORDER BY p.nombre, t.id, c.nombre"
            ),
            {"e": t["id"]},
        ).mappings().all()
        _registrar_descarga(db, t["id"], None, usuario.id, "cliente", len({f["id"] for f in filas}), 0)
        salida.append(
            TiendaOfflineOut(
                empresa_id=t["id"], nombre=t["nombre"], logo_url=t["logo_url"],
                sucursales=[SucursalOfflineOut(**s) for s in sucursales], productos=_productos_de(filas),
                acepta_contra_entrega=_metodo_contra_entrega(db, t["id"]) is not None,
                acepta_paypal=_metodo_paypal(db, t["id"]) is not None,
            )
        )
    direcciones = db.execute(
        text("SELECT id, alias, direccion FROM direccion_cliente WHERE cliente_id = :c ORDER BY predeterminada DESC, id"),
        {"c": usuario.id},
    ).mappings().all()
    paypal = db.execute(
        text("SELECT coalesce(correo, '') FROM cliente_paypal_guardado WHERE cliente_id = :c AND estado = 'activo'"),
        {"c": usuario.id},
    ).scalar()
    db.commit()
    return CatalogoClienteOfflineOut(
        descargado_en=_ahora(), tiendas=salida, direcciones=[DireccionOfflineOut(**d) for d in direcciones],
        paypal_guardado=paypal,
    )


# ================================================================== CU12


def _faltantes(db: Session, sucursal_id: int, items: list[ItemOfflineIn]) -> list[dict]:
    """Lineas sin stock suficiente HOY en la sucursal (bloquea las filas)."""
    faltan = []
    for it in items:
        fila = db.execute(
            text(
                """SELECT p.nombre AS producto, t.codigo AS talla, c.nombre AS color,
                          (SELECT i.cantidad FROM inventario i WHERE i.producto_id = p.id AND i.talla_id = t.id
                             AND i.color_id = c.id AND i.sucursal_id = :s FOR UPDATE) AS disponible
                   FROM producto p, talla t, color c WHERE p.id = :p AND t.id = :t AND c.id = :c"""
            ),
            {"s": sucursal_id, "p": it.producto_id, "t": it.talla_id, "c": it.color_id},
        ).mappings().first()
        if fila is None:
            faltan.append(
                dict(producto_id=it.producto_id, producto="Prenda que ya no existe", talla_id=it.talla_id, talla="-",
                     color_id=it.color_id, color="-", pedido=it.cantidad, disponible=0)
            )
            continue
        disponible = fila["disponible"] or 0
        if disponible < it.cantidad:
            faltan.append(
                dict(producto_id=it.producto_id, producto=fila["producto"], talla_id=it.talla_id, talla=fila["talla"],
                     color_id=it.color_id, color=fila["color"], pedido=it.cantidad, disponible=disponible)
            )
    return faltan


def _aviso_precios(db: Session, items: list[ItemOfflineIn]) -> str | None:
    distintos = 0
    for it in items:
        if it.precio is None:
            continue
        actual = db.execute(text("SELECT precio FROM producto WHERE id = :p"), {"p": it.producto_id}).scalar()
        if actual is not None and Decimal(actual) != it.precio:
            distintos += 1
    if distintos:
        return f"{distintos} prenda(s) cambiaron de precio mientras no había conexión: se respetó el precio cobrado."
    return None


def _metodo_contra_entrega(db: Session, empresa_id: int) -> MetodoPagoEmpresa | None:
    return (
        db.query(MetodoPagoEmpresa)
        .filter(
            MetodoPagoEmpresa.empresa_id == empresa_id,
            MetodoPagoEmpresa.tipo == "contra_entrega",
            MetodoPagoEmpresa.activo.is_(True),
        )
        .first()
    )


def _metodo_paypal(db: Session, empresa_id: int) -> MetodoPagoEmpresa | None:
    # PayPal con correo: a la tienda se le paga su parte por la liquidacion.
    return (
        db.query(MetodoPagoEmpresa)
        .filter(
            MetodoPagoEmpresa.empresa_id == empresa_id,
            MetodoPagoEmpresa.tipo == "paypal",
            MetodoPagoEmpresa.activo.is_(True),
            MetodoPagoEmpresa.paypal_email.isnot(None),
        )
        .first()
    )


def _pedido_invalido(db: Session, op: OperacionOfflineIn, cliente_id: int, empresa_id: int) -> str | None:
    if op.forma_pago is None:
        return "Elige cómo vas a pagar la compra."
    if op.entrega == "envio" and (
        op.direccion_id is None
        or not db.execute(
            text("SELECT 1 FROM direccion_cliente WHERE id = :d AND cliente_id = :c"), {"d": op.direccion_id, "c": cliente_id}
        ).first()
    ):
        return "Elige una de tus direcciones para el envío."
    if op.forma_pago == "contra_entrega" and _metodo_contra_entrega(db, empresa_id) is None:
        return "Esta tienda no acepta pago contra entrega."
    if op.forma_pago == "paypal_guardado" and not token_activo(db, cliente_id):
        return "No tienes un PayPal guardado: vincúlalo en tu perfil y vuelve a comprar."
    if op.forma_pago == "paypal_guardado" and _metodo_paypal(db, empresa_id) is None:
        return "Esta tienda no recibe pagos con PayPal."
    return None


def _registrar_venta(db: Session, op: OperacionOfflineIn, usuario: Usuario, fecha: datetime) -> int:
    cliente_id = None
    if op.cliente_id is not None:
        cliente_id = db.execute(text("SELECT id FROM cliente WHERE id = :c"), {"c": op.cliente_id}).scalar()
    if cliente_id is None:
        cliente_id = db.execute(text("SELECT fn_consumidor_final()")).scalar()
    items = [it.model_dump(mode="json") for it in op.items]
    venta_id = db.execute(
        text("SELECT sp_crear_venta_offline(:c, :s, :e, CAST(:items AS JSONB), :f)"),
        {"c": cliente_id, "s": op.sucursal_id, "e": usuario.id, "items": json.dumps(items), "f": fecha},
    ).scalar()
    nombre = (op.factura_nombre or "").strip() or None
    if op.cliente_id is None and nombre is None:
        nombre = "Cliente"
    db.execute(
        text("UPDATE venta SET factura_nombre = :n, factura_nit = :nit WHERE id = :v"),
        {"n": nombre, "nit": (op.factura_nit or "").strip() or None, "v": venta_id},
    )
    return venta_id


def _registrar_reserva(db: Session, op: OperacionOfflineIn, cliente_id: int, fecha: datetime) -> tuple[int, str | None]:
    aviso = None
    horario = op.horario_atencion
    if horario is not None and horario.tzinfo is not None:
        horario = horario.astimezone(timezone.utc).replace(tzinfo=None)
    if horario is None or horario < _ahora():
        horario = _ahora() + PLAZO_RESERVA
        aviso = "La hora de recojo ya había pasado: la reserva quedó para recoger hasta mañana a esta hora."
    reserva = Reserva(
        cliente_id=cliente_id, sucursal_id=op.sucursal_id, horario_atencion=horario,
        fecha_creacion=fecha, origen="offline", sincronizado_en=_ahora(),
    )
    for it in op.items:
        reserva.detalles.append(
            DetalleReserva(producto_id=it.producto_id, talla_id=it.talla_id, color_id=it.color_id, cantidad=it.cantidad)
        )
    db.add(reserva)
    db.flush()
    _mover_stock_reserva(db, reserva, "salida", None, "retenido al sincronizar reserva sin conexión")
    db.flush()
    return reserva.id, aviso


def _resultado(fila) -> ResultadoOperacionOut:
    return ResultadoOperacionOut(
        uuid=fila["uuid"], estado=fila["estado"], mensaje=fila["mensaje"],
        venta_id=fila["venta_id"], reserva_id=fila["reserva_id"],
        # Compra con PayPal guardado: lo que no se cobro y por que.
        no_pagados=fila["conflicto"] if fila["estado"] in ("pago_parcial", "no_pagada") and fila["conflicto"] else None,
    )


def _procesar(db: Session, op: OperacionOfflineIn, usuario: Usuario, request: Request) -> ResultadoOperacionOut:
    previa = db.execute(
        text("SELECT * FROM operacion_offline WHERE uuid = :u"), {"u": str(op.uuid)}
    ).mappings().first()
    if previa is not None:
        # Reenvio (idempotencia): el mismo resultado, sin registrar de nuevo.
        if previa["usuario_id"] != usuario.id:
            return ResultadoOperacionOut(uuid=op.uuid, estado="rechazada", mensaje="Operación de otro usuario.")
        db.execute(
            text("UPDATE operacion_offline SET intentos = intentos + 1 WHERE id = :i"), {"i": previa["id"]}
        )
        return _resultado(previa)

    personal = _es_personal(usuario)
    sucursal = db.execute(
        text("SELECT id, empresa_id, nombre FROM sucursal WHERE id = :s"), {"s": op.sucursal_id}
    ).mappings().first()
    if sucursal is None:
        return ResultadoOperacionOut(uuid=op.uuid, estado="rechazada", mensaje="La sucursal no existe o no es de tu tienda.")

    estado, mensaje, conflicto, venta_id, reserva_id = "confirmada", None, None, None, None
    fecha = _utc(op.registrada_en)
    cliente_reserva = usuario.id if not personal else op.cliente_id

    if not _con_offline(db, sucursal["empresa_id"]):
        estado, mensaje = "rechazada", SIN_PLAN
    elif personal and sucursal_restringida(usuario) not in (None, op.sucursal_id):
        estado, mensaje = "rechazada", "Solo puedes registrar operaciones de tu propia sucursal."
    elif not personal and op.tipo == "venta":
        estado, mensaje = "rechazada", "Sin conexión el cliente puede reservar o comprar, no registrar ventas."
    elif personal and op.tipo == "pedido":
        estado, mensaje = "rechazada", "Las compras sin conexión son de los clientes; registra una venta de contado."
    elif op.tipo == "pedido" and (motivo := _pedido_invalido(db, op, usuario.id, sucursal["empresa_id"])):
        estado, mensaje = "rechazada", motivo
    elif op.tipo == "reserva" and (
        cliente_reserva is None
        or db.execute(text("SELECT 1 FROM cliente WHERE id = :c"), {"c": cliente_reserva}).scalar() is None
    ):
        estado, mensaje = "rechazada", "La reserva necesita un cliente registrado."
    elif op.tipo == "pedido" and op.forma_pago == "paypal_guardado":
        # "Pago enviado": se cobra con el PayPal guardado apenas termina la
        # sincronizacion (_cobrar_pendientes), prenda por prenda.
        estado, mensaje = "por_cobrar", "Pago enviado: se cobra con tu PayPal guardado."
    else:
        faltan = _faltantes(db, op.sucursal_id, op.items)
        if faltan:
            estado, conflicto = ("sin_stock" if op.tipo == "pedido" else "conflicto"), faltan
            mensaje = "Al sincronizar ya no había stock suficiente: " + "; ".join(
                f"{f['producto']} ({f['talla']}, {f['color']}) pidió {f['pedido']}, hay {f['disponible']}" for f in faltan
            )
            if op.tipo == "pedido":
                mensaje += ". No se puede comprar."
        elif op.tipo == "pedido":
            # No se cobra nada todavia: la app le pide pagarla con prioridad.
            estado = "por_pagar"
            mensaje = (
                "Cambió el precio de alguna prenda: verás el precio nuevo al pagar."
                if _aviso_precios(db, op.items) else "Lista para pagar."
            )
        elif op.tipo == "venta":
            venta_id = _registrar_venta(db, op, usuario, fecha)
            mensaje = _aviso_precios(db, op.items) or "Venta registrada."
        else:
            reserva_id, aviso = _registrar_reserva(db, op, cliente_reserva, fecha)
            mensaje = aviso or "Reserva registrada."

    fila = db.execute(
        text(
            """INSERT INTO operacion_offline (uuid, empresa_id, sucursal_id, usuario_id, tipo, datos, registrada_en,
                                              estado, mensaje, conflicto, venta_id, reserva_id)
               VALUES (:u, :e, :s, :usr, :t, CAST(:d AS JSONB), :f, :est, :m, CAST(:c AS JSONB), :v, :r)
               RETURNING *"""
        ),
        {
            "u": str(op.uuid), "e": sucursal["empresa_id"], "s": op.sucursal_id, "usr": usuario.id, "t": op.tipo,
            "d": op.model_dump_json(), "f": fecha, "est": estado, "m": mensaje,
            "c": json.dumps(conflicto) if conflicto else None, "v": venta_id, "r": reserva_id,
        },
    ).mappings().first()
    # Sin commit: cada operacion va en su propio savepoint (log_bitacora
    # confirmaria la transaccion entera).
    db.add(
        Bitacora(
            usuario_id=usuario.id, accion="SINCRONIZAR", entidad_afectada="operacion_offline", entidad_id=fila["id"],
            detalle=f"{op.tipo.capitalize()} sin conexión en {sucursal['nombre']}: {estado}",
            ip_address=client_ip(request), plataforma=client_platform(request),
        )
    )
    db.flush()
    return _resultado(fila)


def _puede_sincronizar(usuario: Usuario) -> None:
    if _es_personal(usuario):
        if usuario.tipo != "administrador" and "2P-CU12" not in codigos_permiso(usuario):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tu rol no tiene permiso para sincronizar (CU12).")
    elif usuario.tipo != "cliente" or cliente_sin_permiso(usuario, "CU10"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el personal de la tienda y los clientes sincronizan.")


@router.post("/sincronizar", response_model=list[ResultadoOperacionOut])
def sincronizar(
    payload: SincronizarIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> list[ResultadoOperacionOut]:
    """Recibe las operaciones guardadas sin conexion. Cada una se procesa por
    separado: si una falla, las demas siguen; las que dan "error" no se
    guardan y el dispositivo las reintenta."""
    _puede_sincronizar(usuario)
    resultados = []
    for op in payload.operaciones:
        punto = db.begin_nested()
        try:
            resultados.append(_procesar(db, op, usuario, request))
            punto.commit()
        except IntegrityError:
            # Llego la misma operacion por dos caminos a la vez: gana la primera.
            punto.rollback()
            fila = db.execute(
                text("SELECT * FROM operacion_offline WHERE uuid = :u"), {"u": str(op.uuid)}
            ).mappings().first()
            resultados.append(
                _resultado(fila) if fila else ResultadoOperacionOut(uuid=op.uuid, estado="error", mensaje="Reintentar.")
            )
        except (DBAPIError, HTTPException) as exc:
            punto.rollback()
            traducido = http_desde_pg(exc) if isinstance(exc, DBAPIError) else exc
            logger.warning("Sincronizacion offline %s fallo: %s", op.uuid, exc)
            resultados.append(
                ResultadoOperacionOut(
                    uuid=op.uuid, estado="error",
                    mensaje=traducido.detail if traducido else "El servidor no pudo registrarla: se reintentará.",
                )
            )
    db.commit()
    if usuario.tipo == "cliente":
        cobradas = _cobrar_pendientes(db, usuario, request)
        resultados = [cobradas.get(str(r.uuid), r) for r in resultados]
    return resultados


@router.post("/estado", response_model=list[ResultadoOperacionOut])
def estado_operaciones(
    payload: EstadoOperacionesIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> list[ResultadoOperacionOut]:
    """Estado actual de operaciones ya enviadas (p. ej. un conflicto que el
    encargado resolvio despues)."""
    if usuario.tipo == "cliente":
        # Compras con PayPal guardado que quedaron sin cobrar (p. ej. se corto
        # la conexion justo al sincronizar): se cobran ahora.
        _cobrar_pendientes(db, usuario, request)
    filas = db.execute(
        text("SELECT * FROM operacion_offline WHERE uuid = ANY(CAST(:u AS UUID[])) AND usuario_id = :usr"),
        {"u": [str(u) for u in payload.uuids], "usr": usuario.id},
    ).mappings().all()
    return [_con_total(db, f) for f in filas]


# ============================================================= CU13 / CU14

_SQL_OPERACION = """
    SELECT o.*, s.nombre AS sucursal_nombre, u.nombre AS usuario_nombre, u.tipo AS usuario_tipo,
           coalesce(nullif(o.datos->>'factura_nombre', ''), uc.nombre,
                    CASE WHEN o.tipo = 'reserva' AND u.tipo = 'cliente' THEN u.nombre END) AS cliente_nombre,
           ur.nombre AS resuelta_por_nombre
    FROM operacion_offline o
    LEFT JOIN sucursal s ON s.id = o.sucursal_id
    LEFT JOIN usuario u ON u.id = o.usuario_id
    LEFT JOIN usuario uc ON uc.id = (o.datos->>'cliente_id')::int
    LEFT JOIN usuario ur ON ur.id = o.resuelta_por_id
"""


def _to_out(db: Session, f) -> OperacionOfflineOut:
    items = f["datos"].get("items", [])
    nombres = {}
    if items:
        filas = db.execute(
            text(
                """SELECT p.id AS p, t.id AS t, c.id AS c, p.nombre, p.precio, t.codigo, c.nombre AS color
                   FROM producto p, talla t, color c
                   WHERE p.id = ANY(:ps) AND t.id = ANY(:ts) AND c.id = ANY(:cs)"""
            ),
            {
                "ps": [i["producto_id"] for i in items], "ts": [i["talla_id"] for i in items],
                "cs": [i["color_id"] for i in items],
            },
        ).mappings().all()
        nombres = {(n["p"], n["t"], n["c"]): n for n in filas}
    detalle, total = [], Decimal(0)
    for i in items:
        n = nombres.get((i["producto_id"], i["talla_id"], i["color_id"]))
        precio = Decimal(str(i["precio"])) if i.get("precio") is not None else Decimal(n["precio"] if n else 0)
        total += precio * i["cantidad"]
        detalle.append(
            {
                **i, "precio": str(precio),
                "producto": n["nombre"] if n else f"Producto {i['producto_id']}",
                "talla": n["codigo"] if n else "-", "color": n["color"] if n else "-",
            }
        )
    return OperacionOfflineOut(
        id=f["id"], uuid=f["uuid"], tipo=f["tipo"], estado=f["estado"], mensaje=f["mensaje"],
        sucursal_id=f["sucursal_id"], sucursal_nombre=f["sucursal_nombre"], usuario_nombre=f["usuario_nombre"],
        usuario_tipo=f["usuario_tipo"], cliente_nombre=f["cliente_nombre"], registrada_en=f["registrada_en"],
        recibida_en=f["recibida_en"], intentos=f["intentos"], total=total, items=detalle,
        conflicto=[ItemConflictoOut(**c) for c in f["conflicto"]] if f["conflicto"] else None,
        venta_id=f["venta_id"], reserva_id=f["reserva_id"], resuelta_por_nombre=f["resuelta_por_nombre"],
        resuelta_en=f["resuelta_en"], resolucion=f["resolucion"],
    )


@router.get("/operaciones", response_model=list[OperacionOfflineOut])
def listar_operaciones(
    estado: str | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> list[OperacionOfflineOut]:
    """CU13: operaciones sin conexion recibidas. El cliente ve las suyas; el
    personal, las de su tienda (Encargado y Cajero, su sucursal); el
    SuperAdministrador, las de la tienda elegida."""
    sql = _SQL_OPERACION + " WHERE TRUE"
    params: dict = {}
    if usuario.tipo == "cliente":
        sql += " AND o.usuario_id = :u"
        params["u"] = usuario.id
    elif usuario.tipo == "superadministrador":
        empresa = db.execute(text("SELECT fn_empresa_actual()")).scalar()
        if empresa is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Elige primero la tienda.")
        sql += " AND o.empresa_id = :e"
        params["e"] = empresa
    else:
        if usuario.tipo != "administrador" and not codigos_permiso(usuario) & {"2P-CU13", "2P-CU14"}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tu rol no tiene permiso para ver las operaciones sin conexión.")
        restringida = sucursal_restringida(usuario)
        if restringida is not None:
            sql += " AND o.sucursal_id = :s"
            params["s"] = restringida
    if estado:
        sql += " AND o.estado = :est"
        params["est"] = estado
    filas = db.execute(text(sql + " ORDER BY o.recibida_en DESC LIMIT 300"), params).mappings().all()
    return [_to_out(db, f) for f in filas]


def _conflicto(db: Session, usuario: Usuario, operacion_id: int):
    fila = db.execute(text(_SQL_OPERACION + " WHERE o.id = :i"), {"i": operacion_id}).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Operación no encontrada.")
    verificar_acceso_sucursal(usuario, fila["sucursal_id"])
    return fila


@router.get("/operaciones/{operacion_id}/opciones", response_model=OpcionesConflictoOut)
def opciones_conflicto(
    operacion_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("2P-CU14")),
) -> OpcionesConflictoOut:
    """CU14: el conflicto y lo que hay hoy en la sucursal de esas prendas."""
    fila = _conflicto(db, usuario, operacion_id)
    productos = list({i["producto_id"] for i in fila["datos"].get("items", [])})
    disponibles = db.execute(
        text(
            """SELECT i.producto_id, i.talla_id, t.codigo AS talla, i.color_id, c.nombre AS color, i.cantidad AS stock
               FROM inventario i JOIN talla t ON t.id = i.talla_id JOIN color c ON c.id = i.color_id
               WHERE i.sucursal_id = :s AND i.producto_id = ANY(:p) AND i.cantidad > 0
               ORDER BY i.producto_id, t.id, c.nombre"""
        ),
        {"s": fila["sucursal_id"], "p": productos},
    ).mappings().all()
    return OpcionesConflictoOut(
        operacion=_to_out(db, fila), disponibles=[VarianteDisponibleOut(**d) for d in disponibles]
    )


@router.post("/operaciones/{operacion_id}/resolver", response_model=OperacionOfflineOut)
def resolver_conflicto(
    operacion_id: int,
    payload: ResolverConflictoIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("2P-CU14")),
) -> OperacionOfflineOut:
    """CU14: ajustar (registrar con lo que hay: otra cantidad, talla o color)
    o anular. Si cambia el total de una venta, queda dicho cuanto devolverle
    al cliente en efectivo."""
    if not _es_personal(usuario):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Los conflictos los resuelve el personal de la tienda.")
    fila = _conflicto(db, usuario, operacion_id)
    if fila["estado"] != "conflicto":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta operación ya no está en conflicto.")
    original = OperacionOfflineIn.model_validate(fila["datos"])
    total_original = _to_out(db, fila).total
    venta_id = reserva_id = None

    if payload.accion == "anular":
        motivo = (payload.motivo or "").strip()
        if len(motivo) < 3:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Escribe el motivo de la anulación.")
        estado = "anulada"
        resolucion = motivo
        if original.tipo == "venta":
            resolucion += f" · Devolver Bs {total_original:.2f} en efectivo al cliente."
    else:
        if not payload.items:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indica con qué prendas queda la operación.")
        ajustada = original.model_copy(update={"items": payload.items})
        if _faltantes(db, original.sucursal_id, ajustada.items):
            raise HTTPException(status.HTTP_409_CONFLICT, "Tampoco hay stock suficiente para ese ajuste.")
        fecha = fila["registrada_en"]
        try:
            if original.tipo == "venta":
                venta_id = _registrar_venta(db, ajustada, usuario, fecha)
                nuevo = db.execute(text("SELECT total FROM venta WHERE id = :v"), {"v": venta_id}).scalar()
                diferencia = Decimal(total_original) - Decimal(nuevo)
                resolucion = f"Venta ajustada (#{venta_id}) por Bs {Decimal(nuevo):.2f}."
                if diferencia > 0:
                    resolucion += f" Devolver Bs {diferencia:.2f} en efectivo al cliente."
                elif diferencia < 0:
                    resolucion += f" Cobrar Bs {-diferencia:.2f} más al cliente."
            else:
                cliente = ajustada.cliente_id if _es_personal_de_fila(fila) else fila["usuario_id"]
                reserva_id, _ = _registrar_reserva(db, ajustada, cliente, fecha)
                resolucion = f"Reserva ajustada (#{reserva_id})."
        except DBAPIError as exc:
            db.rollback()
            raise http_desde_pg(exc) or HTTPException(status.HTTP_409_CONFLICT, "No se pudo registrar el ajuste.")
        estado = "resuelta"
        if payload.motivo:
            resolucion += f" {payload.motivo.strip()}"

    db.execute(
        text(
            """UPDATE operacion_offline SET estado = :e, resolucion = :r, resuelta_por_id = :u, resuelta_en = now(),
                      actualizada_en = now(), venta_id = coalesce(:v, venta_id), reserva_id = coalesce(:rs, reserva_id),
                      mensaje = :m
               WHERE id = :i"""
        ),
        {
            "e": estado, "r": resolucion, "u": usuario.id, "v": venta_id, "rs": reserva_id, "i": operacion_id,
            "m": "Resuelta por la tienda: " + resolucion if estado == "resuelta" else "Anulada por la tienda: " + resolucion,
        },
    )
    # Si la reserva era de un cliente, se le avisa.
    if fila["usuario_tipo"] == "cliente":
        db.add(
            Notificacion(
                cliente_id=fila["usuario_id"], canal="app", tipo_evento="reserva_offline",
                mensaje=f"Tu reserva sin conexión en {fila['sucursal_nombre']}: {resolucion}",
                estado="enviada", entidad_tipo="reserva", entidad_id=reserva_id,
            )
        )
    log_bitacora(db, usuario, "ACTUALIZAR", "operacion_offline", operacion_id, f"Conflicto {estado}: {resolucion}", request)
    db.commit()
    return _to_out(db, db.execute(text(_SQL_OPERACION + " WHERE o.id = :i"), {"i": operacion_id}).mappings().first())


def _es_personal_de_fila(fila) -> bool:
    return fila["usuario_tipo"] in STAFF_TIPOS


# ===================================================== seguimiento (CU11/12)


@router.get("/seguimiento", response_model=SeguimientoOfflineOut)
def seguimiento(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> SeguimientoOfflineOut:
    """Seguimiento de una tienda sin conexion: quien descargo datos (CU11) y
    como sincroniza cada usuario (CU12). Para el SuperAdministrador (la
    tienda elegida) y el Administrador de la tienda."""
    if usuario.tipo not in ("superadministrador", "administrador"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el Administrador o el SuperAdministrador.")
    empresa = db.execute(text("SELECT fn_empresa_actual()")).scalar()
    if empresa is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Elige primero la tienda.")
    plan = db.execute(
        text(
            """SELECT p.nombre, fn_empresa_con_offline(:e) AS offline FROM suscripcion s
               JOIN plan_suscripcion p ON p.id = s.plan_id WHERE s.empresa_id = :e AND s.estado = 'activa'"""
        ),
        {"e": empresa},
    ).mappings().first()
    resumen = db.execute(
        text(
            """SELECT
                 (SELECT count(*) FROM descarga_offline
                  WHERE empresa_id = :e AND fecha >= now() - interval '30 days') AS descargas_30d,
                 (SELECT count(DISTINCT usuario_id) FROM descarga_offline
                  WHERE empresa_id = :e AND fecha >= now() - interval '30 days') AS usuarios_con_datos,
                 (SELECT max(fecha) FROM descarga_offline WHERE empresa_id = :e) AS ultima_descarga,
                 count(o.id) AS operaciones,
                 count(o.id) FILTER (WHERE o.estado = 'confirmada') AS confirmadas,
                 count(o.id) FILTER (WHERE o.estado = 'conflicto') AS conflictos,
                 count(o.id) FILTER (WHERE o.estado = 'resuelta') AS resueltas,
                 count(o.id) FILTER (WHERE o.estado = 'anulada') AS anuladas,
                 count(o.id) FILTER (WHERE o.estado = 'rechazada') AS rechazadas,
                 coalesce(sum(o.intentos - 1), 0) AS reenvios,
                 max(o.recibida_en) AS ultima_sincronizacion
               FROM operacion_offline o WHERE o.empresa_id = :e"""
        ),
        {"e": empresa},
    ).mappings().first()
    descargas = db.execute(
        text(
            """SELECT d.fecha, d.tipo, d.productos, d.clientes, u.nombre AS usuario_nombre, u.tipo AS usuario_tipo,
                      s.nombre AS sucursal_nombre
               FROM descarga_offline d
               LEFT JOIN usuario u ON u.id = d.usuario_id
               LEFT JOIN sucursal s ON s.id = d.sucursal_id
               WHERE d.empresa_id = :e ORDER BY d.fecha DESC LIMIT 100"""
        ),
        {"e": empresa},
    ).mappings().all()
    usuarios = db.execute(
        text(
            """WITH ops AS (
                 SELECT o.usuario_id, count(*) AS operaciones,
                        count(*) FILTER (WHERE o.estado = 'confirmada') AS confirmadas,
                        count(*) FILTER (WHERE o.estado = 'conflicto') AS conflictos,
                        count(*) FILTER (WHERE o.estado = 'resuelta') AS resueltas,
                        count(*) FILTER (WHERE o.estado IN ('anulada', 'rechazada')) AS no_registradas,
                        sum(o.intentos - 1) AS reenvios, max(o.recibida_en) AS ultima_sincronizacion,
                        (array_agg(s.nombre ORDER BY o.recibida_en DESC))[1] AS sucursal_nombre
                 FROM operacion_offline o LEFT JOIN sucursal s ON s.id = o.sucursal_id
                 WHERE o.empresa_id = :e GROUP BY o.usuario_id
               ), des AS (
                 SELECT d.usuario_id, max(d.fecha) AS ultima_descarga, count(*) AS descargas,
                        (array_agg(s.nombre ORDER BY d.fecha DESC))[1] AS sucursal_nombre
                 FROM descarga_offline d LEFT JOIN sucursal s ON s.id = d.sucursal_id
                 WHERE d.empresa_id = :e GROUP BY d.usuario_id
               )
               SELECT u.nombre AS usuario_nombre, u.tipo AS usuario_tipo,
                      coalesce(ops.sucursal_nombre, des.sucursal_nombre) AS sucursal_nombre,
                      coalesce(ops.operaciones, 0) AS operaciones, coalesce(ops.confirmadas, 0) AS confirmadas,
                      coalesce(ops.conflictos, 0) AS conflictos, coalesce(ops.resueltas, 0) AS resueltas,
                      coalesce(ops.no_registradas, 0) AS no_registradas, coalesce(ops.reenvios, 0) AS reenvios,
                      ops.ultima_sincronizacion, des.ultima_descarga, coalesce(des.descargas, 0) AS descargas
               FROM ops FULL JOIN des ON des.usuario_id = ops.usuario_id
               JOIN usuario u ON u.id = coalesce(ops.usuario_id, des.usuario_id)
               ORDER BY greatest(ops.ultima_sincronizacion, des.ultima_descarga) DESC NULLS LAST"""
        ),
        {"e": empresa},
    ).mappings().all()
    return SeguimientoOfflineOut(
        plan=plan["nombre"] if plan else None,
        plan_offline=bool(plan and plan["offline"]),
        resumen=ResumenSeguimientoOut(**resumen),
        descargas=[DescargaOfflineOut(**d) for d in descargas],
        usuarios=[UsuarioOfflineOut(**u) for u in usuarios],
    )


# ================================================= compras sin conexion
# El cliente armo su compra sin internet. Al volver la conexion la app se la
# muestra con prioridad, revisada contra el precio y el stock de AHORA: si
# falta stock no se puede comprar; si cambio el precio, se le muestra y paga
# el actual. Al pagar se registra la venta (origen 'offline').

PEDIDO_ABIERTO = ("por_pagar", "sin_stock")


def _cliente_pedido(db: Session, usuario: Usuario, uuid: str):
    if usuario.tipo != "cliente":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el cliente paga sus compras sin conexión.")
    fila = db.execute(
        text(
            """SELECT o.*, s.nombre AS sucursal_nombre, e.id AS e_id, e.nombre AS e_nombre, e.logo_url, e.color_marca
               FROM operacion_offline o JOIN sucursal s ON s.id = o.sucursal_id JOIN empresa e ON e.id = o.empresa_id
               WHERE o.uuid = CAST(:u AS UUID) AND o.usuario_id = :c AND o.tipo = 'pedido'"""
        ),
        {"u": uuid, "c": usuario.id},
    ).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compra no encontrada.")
    return fila


def _revisar(db: Session, fila) -> PedidoOfflineOut:
    """Precio y stock de AHORA para cada prenda de la compra."""
    datos = OperacionOfflineIn.model_validate(fila["datos"])
    items, total_guardado, total_actual = [], Decimal(0), Decimal(0)
    for it in datos.items:
        f = db.execute(
            text(
                """SELECT p.nombre, p.precio, t.codigo, c.nombre AS color,
                          coalesce((SELECT i.cantidad FROM inventario i WHERE i.producto_id = p.id AND i.talla_id = t.id
                                      AND i.color_id = c.id AND i.sucursal_id = :s), 0) AS stock
                   FROM producto p, talla t, color c WHERE p.id = :p AND t.id = :t AND c.id = :c"""
            ),
            {"s": datos.sucursal_id, "p": it.producto_id, "t": it.talla_id, "c": it.color_id},
        ).mappings().first()
        actual = Decimal(f["precio"]) if f else Decimal(0)
        guardado = it.precio if it.precio is not None else actual
        total_guardado += guardado * it.cantidad
        total_actual += actual * it.cantidad
        items.append(
            ItemPedidoOut(
                producto_id=it.producto_id, talla_id=it.talla_id, color_id=it.color_id,
                producto=f["nombre"] if f else "Prenda que ya no existe", talla=f["codigo"] if f else "-",
                color=f["color"] if f else "-", cantidad=it.cantidad, precio_guardado=guardado,
                precio_actual=actual, stock=f["stock"] if f else 0,
            )
        )
    sin_stock = any(i.stock < i.cantidad for i in items)
    estado = fila["estado"]
    if estado in PEDIDO_ABIERTO:
        nuevo = "sin_stock" if sin_stock else "por_pagar"
        if nuevo != estado:
            mensaje = (
                "Ya no hay stock suficiente: no se puede comprar." if sin_stock else "Volvió a haber stock: lista para pagar."
            )
            db.execute(
                text("UPDATE operacion_offline SET estado = :e, mensaje = :m, actualizada_en = now() WHERE id = :i"),
                {"e": nuevo, "m": mensaje, "i": fila["id"]},
            )
            db.commit()
            estado = nuevo
    if datos.forma_pago == "contra_entrega":
        metodo = _metodo_contra_entrega(db, fila["empresa_id"])
        metodos = [_publico(metodo)] if metodo else []
    else:
        metodos = [
            _publico(m)
            for m in db.query(MetodoPagoEmpresa)
            .filter(
                MetodoPagoEmpresa.empresa_id == fila["empresa_id"],
                MetodoPagoEmpresa.activo.is_(True),
                MetodoPagoEmpresa.tipo != "contra_entrega",
            )
            .order_by(MetodoPagoEmpresa.orden, MetodoPagoEmpresa.id)
        ]
    direccion = None
    if datos.entrega == "envio" and datos.direccion_id:
        direccion = db.execute(
            text("SELECT alias || ': ' || direccion FROM direccion_cliente WHERE id = :d"), {"d": datos.direccion_id}
        ).scalar()
    total_usd, _ = _a_usd(db, total_actual.quantize(Decimal("0.01")))
    return PedidoOfflineOut(
        id=fila["id"], uuid=fila["uuid"], estado=estado, mensaje=fila["mensaje"], empresa_id=fila["e_id"],
        tienda=fila["e_nombre"], logo_url=fila["logo_url"], color_marca=fila["color_marca"],
        sucursal_id=datos.sucursal_id, sucursal=fila["sucursal_nombre"], registrada_en=fila["registrada_en"],
        entrega=datos.entrega, direccion=direccion, forma_pago=datos.forma_pago or "en_linea", items=items,
        total_guardado=total_guardado.quantize(Decimal("0.01")), total_actual=total_actual.quantize(Decimal("0.01")),
        total_usd=total_usd, precio_cambio=any(i.precio_guardado != i.precio_actual for i in items),
        sin_stock=sin_stock, puede_pagar=estado == "por_pagar" and not sin_stock and bool(metodos), metodos=metodos,
        venta_id=fila["venta_id"],
    )


@router.get("/pedidos", response_model=list[PedidoOfflineOut])
def pedidos_por_pagar(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> list[PedidoOfflineOut]:
    """Compras sin conexion del cliente que esperan su pago (las que hizo en
    la web o en la app movil), revisadas contra el precio y stock de ahora."""
    if usuario.tipo != "cliente":
        return []
    filas = db.execute(
        text(
            """SELECT o.*, s.nombre AS sucursal_nombre, e.id AS e_id, e.nombre AS e_nombre, e.logo_url, e.color_marca
               FROM operacion_offline o JOIN sucursal s ON s.id = o.sucursal_id JOIN empresa e ON e.id = o.empresa_id
               WHERE o.usuario_id = :c AND o.tipo = 'pedido' AND o.estado IN ('por_pagar', 'sin_stock')
               ORDER BY o.registrada_en"""
        ),
        {"c": usuario.id},
    ).mappings().all()
    return [_revisar(db, f) for f in filas]


def _pagable(db: Session, usuario: Usuario, uuid: str) -> tuple[dict, PedidoOfflineOut, OperacionOfflineIn]:
    fila = _cliente_pedido(db, usuario, uuid)
    revisado = _revisar(db, fila)
    if revisado.estado not in PEDIDO_ABIERTO:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta compra ya fue pagada o cancelada.")
    if revisado.sin_stock:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya no hay stock suficiente de alguna prenda: no se puede comprar.")
    return fila, revisado, OperacionOfflineIn.model_validate(fila["datos"])


def _items_actuales(datos: OperacionOfflineIn) -> str:
    # El precio lo pone el procedimiento con el de ahora (el que ve el cliente).
    return json.dumps(
        [{"producto_id": i.producto_id, "talla_id": i.talla_id, "color_id": i.color_id, "cantidad": i.cantidad} for i in datos.items]
    )


def _marcar_pagada(db: Session, fila, venta_id: int, datos: OperacionOfflineIn, mensaje: str) -> None:
    db.execute(
        text("UPDATE venta SET origen = 'offline', sincronizado_en = now() WHERE id = :v"), {"v": venta_id}
    )
    if datos.entrega == "envio" and datos.direccion_id:
        _guardar_envio(db, [venta_id], fila["usuario_id"], datos.direccion_id)
    db.execute(
        text(
            """UPDATE operacion_offline SET estado = 'pagada', venta_id = :v, mensaje = :m, actualizada_en = now()
               WHERE id = :i"""
        ),
        {"v": venta_id, "m": mensaje, "i": fila["id"]},
    )


@router.post("/pedidos/{uuid}/paypal/orden")
def pedido_paypal_orden(
    uuid: str,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict:
    fila, revisado, _ = _pagable(db, usuario, uuid)
    _, cuenta = _paypal_de_tienda(db, fila["empresa_id"])
    base = str(request.base_url).rstrip("/")
    orden = crear_orden(
        revisado.total_usd, referencia=f"pedido-offline-{fila['id']}",
        return_url=f"{base}/paypal-embed/retorno", cancel_url=f"{base}/paypal-embed/cancelado", cuenta=cuenta,
    )
    return {"order_id": orden["id"], "total": revisado.total_usd}


@router.post("/pedidos/{uuid}/paypal/capturar/{order_id}", response_model=PedidoOfflineOut)
def pedido_paypal_capturar(
    uuid: str,
    order_id: str,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> PedidoOfflineOut:
    fila, revisado, datos = _pagable(db, usuario, uuid)
    metodo, cuenta = _paypal_de_tienda(db, fila["empresa_id"])
    unidad = (obtener_orden(order_id, cuenta).get("purchase_units") or [{}])[0]
    if unidad.get("reference_id") != f"pedido-offline-{fila['id']}" or not _monto_coincide(unidad.get("amount"), revisado.total_usd):
        raise HTTPException(status.HTTP_409_CONFLICT, "El precio cambió desde que iniciaste el pago. Vuelve a intentarlo.")
    try:
        venta_id = db.execute(
            text("SELECT sp_crear_venta_tienda(:c, :s, NULL, CAST(:items AS JSONB), CAST(:d AS INTEGER[]), :m, :r, NULL)"),
            {"c": usuario.id, "s": datos.sucursal_id, "items": _items_actuales(datos), "d": [], "m": metodo.id, "r": order_id},
        ).scalar_one()
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)
    resultado = capturar_orden(order_id, cuenta)
    captura = captura_de(resultado)
    if resultado.get("status") != "COMPLETED" or captura is None:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "PayPal no confirmó el pago.")
    try:
        _guardar_captura(db, [venta_id], captura["id"])
        _marcar_pagada(db, fila, venta_id, datos, f"Pagada con PayPal · Venta #{venta_id}")
        log_bitacora(db, usuario, "CREAR", "venta", venta_id, f"Compra sin conexión pagada con PayPal (orden {order_id})", request)
    except Exception:
        db.rollback()
        reembolsar_captura(captura["id"], cuenta)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No se pudo registrar tu compra. El cobro fue revertido.")
    return _revisar(db, _cliente_pedido(db, usuario, uuid))


@router.post("/pedidos/{uuid}/comprobante", response_model=PedidoOfflineOut)
async def pedido_comprobante(
    uuid: str,
    request: Request,
    metodo_pago_id: int = Form(...),
    file: UploadFile = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> PedidoOfflineOut:
    """QR, transferencia u otro: sube el comprobante; la tienda lo aprueba."""
    fila, _, datos = _pagable(db, usuario, uuid)
    metodo = db.query(MetodoPagoEmpresa).filter(
        MetodoPagoEmpresa.id == metodo_pago_id, MetodoPagoEmpresa.empresa_id == fila["empresa_id"],
        MetodoPagoEmpresa.activo.is_(True),
    ).first()
    if metodo is None or metodo.tipo in ("paypal", "contra_entrega") or datos.forma_pago == "contra_entrega":
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese método de pago no está disponible para esta compra.")
    if file is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sube la foto de tu comprobante de pago.")
    comprobante_url = upload_comprobante_pago(usuario.id, await file.read(), file.content_type or "")
    try:
        venta_id = db.execute(
            text("SELECT sp_crear_venta_tienda(:c, :s, NULL, CAST(:items AS JSONB), CAST(:d AS INTEGER[]), :m, NULL, :u)"),
            {"c": usuario.id, "s": datos.sucursal_id, "items": _items_actuales(datos), "d": [], "m": metodo.id, "u": comprobante_url},
        ).scalar_one()
        _marcar_pagada(db, fila, venta_id, datos, f"Comprobante enviado ({metodo.nombre}): la tienda lo revisa · Venta #{venta_id}")
        log_bitacora(db, usuario, "CREAR", "venta", venta_id, f"Compra sin conexión con comprobante ({metodo.nombre})", request)
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)
    return _revisar(db, _cliente_pedido(db, usuario, uuid))


@router.post("/pedidos/{uuid}/contra-entrega", response_model=PedidoOfflineOut)
def pedido_contra_entrega(
    uuid: str,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> PedidoOfflineOut:
    """Confirma la compra: se registra la venta, se aparta el stock y paga al
    recibirla o recogerla."""
    fila, _, datos = _pagable(db, usuario, uuid)
    if datos.forma_pago != "contra_entrega":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta compra se paga en línea: elige un método de pago.")
    metodo = _metodo_contra_entrega(db, fila["empresa_id"])
    if metodo is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta tienda ya no acepta pago contra entrega: cancélala y vuelve a comprar.")
    try:
        venta_id = db.execute(
            text("SELECT sp_crear_venta_contra_entrega(:c, :s, CAST(:items AS JSONB), :m)"),
            {"c": usuario.id, "s": datos.sucursal_id, "items": _items_actuales(datos), "m": metodo.id},
        ).scalar_one()
        momento = "al recibirla" if datos.entrega == "envio" else "al recogerla"
        _marcar_pagada(db, fila, venta_id, datos, f"Confirmada: pagas {momento} · Venta #{venta_id}")
        log_bitacora(db, usuario, "CREAR", "venta", venta_id, "Compra sin conexión confirmada contra entrega", request)
    except DBAPIError as exc:
        db.rollback()
        raise _error_sp(exc)
    return _revisar(db, _cliente_pedido(db, usuario, uuid))


@router.post("/pedidos/{uuid}/cancelar", response_model=PedidoOfflineOut)
def pedido_cancelar(
    uuid: str,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> PedidoOfflineOut:
    fila = _cliente_pedido(db, usuario, uuid)
    if fila["estado"] not in PEDIDO_ABIERTO:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta compra ya fue pagada o cancelada.")
    db.execute(
        text("UPDATE operacion_offline SET estado = 'cancelada', mensaje = :m, actualizada_en = now() WHERE id = :i"),
        {"m": "La cancelaste.", "i": fila["id"]},
    )
    log_bitacora(db, usuario, "ACTUALIZAR", "operacion_offline", fila["id"], "Compra sin conexión cancelada por el cliente", request)
    return _revisar(db, _cliente_pedido(db, usuario, uuid))


# ================================== compras sin conexion con PayPal guardado
# El cliente compro sin internet con "Pagar con mi PayPal guardado" (vio "Pago
# enviado"). Al sincronizar se revisa cada prenda contra el stock y el precio de
# AHORA y se cobra solo lo que se puede comprar: lo demas no se cobra nunca (no
# hay nada que devolver) y queda dicho por que.


def _con_total(db: Session, fila) -> ResultadoOperacionOut:
    r = _resultado(fila)
    if fila["venta_id"] and fila["estado"] in ("pagada", "pago_parcial") and fila["tipo"] == "pedido":
        r.total_cobrado = db.execute(text("SELECT total FROM venta WHERE id = :v"), {"v": fila["venta_id"]}).scalar()
    return r


def _cerrar_cobro(db: Session, fila, estado: str, mensaje: str, no_pagados: list[dict], venta_id: int | None) -> None:
    db.execute(
        text(
            """UPDATE operacion_offline SET estado = :e, mensaje = :m, conflicto = CAST(:c AS JSONB), venta_id = :v,
                      actualizada_en = now()
               WHERE id = :i AND estado = 'por_cobrar'"""
        ),
        {"e": estado, "m": mensaje, "c": json.dumps(no_pagados, default=str) if no_pagados else None, "v": venta_id,
         "i": fila["id"]},
    )


def _avisar_cobro(db: Session, fila, titulo: str, mensaje: str) -> None:
    """Notificacion al cliente y copia por correo de parte de la tienda."""
    db.add(
        Notificacion(
            cliente_id=fila["usuario_id"], canal="app", tipo_evento="compra_offline", mensaje=mensaje,
            estado="enviada", entidad_tipo="operacion_offline", entidad_id=fila["id"],
        )
    )
    programar_correo(db, fila["usuario_id"], fila["empresa_id"], titulo, mensaje)


def _revisar_items(db: Session, datos: OperacionOfflineIn) -> tuple[list[tuple[ItemOfflineIn, dict]], list[dict]]:
    """Separa las prendas que se pueden cobrar (stock y precio vigentes) de las
    que no, con su motivo. Bloquea el stock de las que se cobran."""
    validos, no_pagados = [], []
    sucursal = db.execute(text("SELECT nombre FROM sucursal WHERE id = :s"), {"s": datos.sucursal_id}).scalar()
    for it in datos.items:
        f = db.execute(
            text(
                """SELECT p.nombre, p.precio, p.estado, t.codigo AS talla, c.nombre AS color,
                          (SELECT i.cantidad FROM inventario i WHERE i.producto_id = p.id AND i.talla_id = t.id
                             AND i.color_id = c.id AND i.sucursal_id = :s FOR UPDATE) AS stock
                   FROM producto p, talla t, color c WHERE p.id = :p AND t.id = :t AND c.id = :c"""
            ),
            {"s": datos.sucursal_id, "p": it.producto_id, "t": it.talla_id, "c": it.color_id},
        ).mappings().first()
        stock = (f["stock"] or 0) if f else 0
        base = dict(
            producto_id=it.producto_id, talla_id=it.talla_id, color_id=it.color_id, pedido=it.cantidad,
            disponible=stock, producto=f["nombre"] if f else "Prenda que ya no existe",
            talla=f["talla"] if f else "-", color=f["color"] if f else "-",
        )
        actual = Decimal(f["precio"]) if f else Decimal(0)
        guardado = it.precio if it.precio is not None else actual
        if f is None or f["estado"] != "activo":
            no_pagados.append({**base, "motivo": "La prenda ya no está a la venta."})
        elif stock < it.cantidad:
            no_pagados.append(
                {**base, "motivo": f"Sin stock suficiente en {sucursal}: pediste {it.cantidad} y hay {stock}."}
            )
        elif actual > guardado:
            # No se cobra mas de lo que el cliente acepto al comprar.
            no_pagados.append(
                {**base, "motivo": f"Subió de precio (de Bs {guardado:.2f} a Bs {actual:.2f}): no se cobró sin tu permiso."}
            )
        else:
            validos.append((it, base))
    return validos, no_pagados


def _cobrar(db: Session, usuario: Usuario, operacion_id: int, request: Request) -> None:
    """Cobra una compra sin conexion con el PayPal guardado del cliente (cuenta
    de Arlani, como "Pagar todo") y la deja en 'pagada', 'pago_parcial' o
    'no_pagada'. A la tienda le llega lo suyo por la liquidacion."""
    fila = db.execute(
        text("SELECT * FROM operacion_offline WHERE id = :i AND estado = 'por_cobrar' FOR UPDATE SKIP LOCKED"),
        {"i": operacion_id},
    ).mappings().first()
    if fila is None:
        db.rollback()
        return
    datos = OperacionOfflineIn.model_validate(fila["datos"])
    tienda = db.execute(text("SELECT nombre FROM empresa WHERE id = :e"), {"e": fila["empresa_id"]}).scalar()

    def no_pagada(motivo: str, detalle: list[dict]) -> None:
        _cerrar_cobro(db, fila, "no_pagada", f"Pago no finalizado: {motivo} No se te cobró nada.", detalle, None)
        _avisar_cobro(
            db, fila, "Pago no finalizado", f"Tu compra sin conexión en {tienda} no se cobró: {motivo} No se te cobró nada."
        )
        db.commit()

    validos, no_pagados = _revisar_items(db, datos)
    todos = no_pagados + [b for _, b in validos]
    token = token_activo(db, fila["usuario_id"])
    metodo = _metodo_paypal(db, fila["empresa_id"])
    if not token:
        motivo = "Ya no tienes un PayPal guardado: vincúlalo en tu perfil y vuelve a comprar."
        return no_pagada(motivo, [{**b, "motivo": motivo} for b in todos])
    if metodo is None:
        motivo = "La tienda ya no recibe pagos con PayPal."
        return no_pagada(motivo, [{**b, "motivo": motivo} for b in todos])
    if not validos:
        return no_pagada("ninguna prenda se pudo comprar.", no_pagados)

    # 1) La venta con lo que si se puede comprar (aparta el stock, sin confirmar).
    referencia = f"pedido-offline-{fila['id']}"
    items = json.dumps(
        [{"producto_id": i.producto_id, "talla_id": i.talla_id, "color_id": i.color_id, "cantidad": i.cantidad}
         for i, _ in validos]
    )
    try:
        venta_id = db.execute(
            text("SELECT sp_crear_venta_tienda(:c, :s, NULL, CAST(:items AS JSONB), CAST(:d AS INTEGER[]), :m, :r, NULL)"),
            {"c": fila["usuario_id"], "s": datos.sucursal_id, "items": items, "d": [], "m": metodo.id, "r": referencia},
        ).scalar_one()
    except DBAPIError as exc:
        db.rollback()
        logger.warning("Compra sin conexion %s: no se pudo registrar la venta: %s", fila["uuid"], exc)
        motivo = "La tienda no pudo registrar la compra."
        return no_pagada(motivo, [{**b, "motivo": motivo} for b in todos])
    total = Decimal(db.execute(text("SELECT total FROM venta WHERE id = :v"), {"v": venta_id}).scalar())
    total_usd, tc = _a_usd(db, total)

    # 2) El cobro con el PayPal guardado. El uuid evita cobrar dos veces.
    try:
        orden = cobrar_con_token(token, total_usd, referencia, f"arlani-offline-{fila['uuid']}")
    except (CobroRechazado, HTTPException) as exc:
        db.rollback()
        motivo = f"PayPal rechazó el cobro ({exc.detail if isinstance(exc, HTTPException) else exc})."
        return no_pagada(motivo, [{**b, "motivo": motivo} for b in todos])
    captura = captura_de(orden)

    # 3) Se confirma todo; si algo falla aca, se devuelve el cobro.
    try:
        if not _monto_coincide(captura.get("amount"), total_usd):
            raise ValueError("monto cobrado distinto")
        db.execute(
            text("UPDATE transaccion SET referencia_externa = :o WHERE pago_id IN (SELECT id FROM pago WHERE venta_id = :v)"),
            {"o": orden["id"], "v": venta_id},
        )
        _guardar_captura(db, [venta_id], captura["id"])
        db.execute(text("UPDATE venta SET origen = 'offline', sincronizado_en = now() WHERE id = :v"), {"v": venta_id})
        if datos.entrega == "envio":
            _guardar_envio(db, [venta_id], fila["usuario_id"], datos.direccion_id)
        liquidacion = db.execute(
            text("SELECT sp_registrar_liquidacion(:e, :o, :c, :v, :tc)"),
            {"e": fila["empresa_id"], "o": orden["id"], "c": captura["id"], "v": [venta_id], "tc": tc},
        ).scalar_one()
        if no_pagados:
            _cerrar_cobro(
                db, fila, "pago_parcial",
                f"Pago no finalizado: se cobraron Bs {total:.2f} por lo que sí había; "
                f"{len(no_pagados)} prenda(s) no se cobraron · Venta #{venta_id}",
                no_pagados, venta_id,
            )
            _avisar_cobro(
                db, fila, "Pago no finalizado",
                f"De tu compra sin conexión en {tienda} se cobraron Bs {total:.2f} con tu PayPal. No se pudo pagar: "
                + "; ".join(f"{n['producto']} ({n['talla']}, {n['color']}): {n['motivo']}" for n in no_pagados)
                + " Eso no se te cobró.",
            )
        else:
            _cerrar_cobro(
                db, fila, "pagada", f"Pago finalizado con éxito: Bs {total:.2f} con tu PayPal · Venta #{venta_id}",
                [], venta_id,
            )
            _avisar_cobro(
                db, fila, "Pago finalizado con éxito",
                f"Tu compra sin conexión en {tienda} se pagó con tu PayPal guardado: Bs {total:.2f} (venta #{venta_id}).",
            )
        db.add(
            Bitacora(
                usuario_id=usuario.id, accion="CREAR", entidad_afectada="venta", entidad_id=venta_id,
                detalle=f"Compra sin conexión cobrada con PayPal guardado (orden {orden['id']})",
                ip_address=client_ip(request), plataforma=client_platform(request),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Compra sin conexion %s cobrada pero no registrada: se devuelve el cobro", fila["uuid"])
        if not reembolsar_captura(captura["id"]):
            logger.error("No se pudo devolver la captura %s (orden %s): revisar a mano", captura["id"], orden["id"])
        motivo = "No se pudo registrar la compra; el cobro fue devuelto a tu PayPal."
        return no_pagada(motivo, [{**b, "motivo": motivo} for b in todos])

    # 4) Lo de la tienda (menos la comision) se le envia al instante; si PayPal
    # falla queda para reintentar: la compra del cliente ya esta confirmada.
    try:
        enviar_liquidaciones(db, [liquidacion])
    except Exception:
        db.rollback()
        logger.exception("No se pudo enviar la liquidacion %s (orden %s)", liquidacion, orden["id"])


def _cobrar_pendientes(db: Session, usuario: Usuario, request: Request) -> dict[str, ResultadoOperacionOut]:
    """Cobra las compras con PayPal guardado del cliente que esperan su cobro y
    devuelve el resultado de cada una por uuid."""
    ids = db.execute(
        text("SELECT id FROM operacion_offline WHERE usuario_id = :u AND estado = 'por_cobrar' ORDER BY registrada_en"),
        {"u": usuario.id},
    ).scalars().all()
    resultados: dict[str, ResultadoOperacionOut] = {}
    for operacion_id in ids:
        try:
            _cobrar(db, usuario, operacion_id, request)
        except Exception:
            # Queda 'por_cobrar' y se reintenta en la proxima sincronizacion.
            db.rollback()
            logger.exception("Fallo el cobro de la compra sin conexion %s", operacion_id)
        fila = db.execute(text("SELECT * FROM operacion_offline WHERE id = :i"), {"i": operacion_id}).mappings().first()
        resultados[str(fila["uuid"])] = _con_total(db, fila)
    return resultados
