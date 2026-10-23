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

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
from app.api.v1.endpoints.reservas import _mover_stock_reserva
from app.core.audit import client_ip, client_platform, log_bitacora
from app.core.errores_db import http_desde_pg
from app.db.session import get_db
from app.models import Bitacora, DetalleReserva, Notificacion, Reserva, Usuario
from app.services.usuarios import codigos_permiso
from app.schemas.offline import (
    CatalogoClienteOfflineOut,
    ClienteOfflineOut,
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
            )
        )
    db.commit()
    return CatalogoClienteOfflineOut(descargado_en=_ahora(), tiendas=salida)


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
    elif not personal and op.tipo != "reserva":
        estado, mensaje = "rechazada", "Sin conexión el cliente solo puede reservar."
    elif op.tipo == "reserva" and (
        cliente_reserva is None
        or db.execute(text("SELECT 1 FROM cliente WHERE id = :c"), {"c": cliente_reserva}).scalar() is None
    ):
        estado, mensaje = "rechazada", "La reserva necesita un cliente registrado."
    else:
        faltan = _faltantes(db, op.sucursal_id, op.items)
        if faltan:
            estado, conflicto = "conflicto", faltan
            mensaje = "Al sincronizar ya no había stock suficiente: " + "; ".join(
                f"{f['producto']} ({f['talla']}, {f['color']}) pidió {f['pedido']}, hay {f['disponible']}" for f in faltan
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
    return resultados


@router.post("/estado", response_model=list[ResultadoOperacionOut])
def estado_operaciones(
    payload: EstadoOperacionesIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> list[ResultadoOperacionOut]:
    """Estado actual de operaciones ya enviadas (p. ej. un conflicto que el
    encargado resolvio despues)."""
    filas = db.execute(
        text("SELECT * FROM operacion_offline WHERE uuid = ANY(CAST(:u AS UUID[])) AND usuario_id = :usr"),
        {"u": [str(u) for u in payload.uuids], "usr": usuario.id},
    ).mappings().all()
    return [_resultado(f) for f in filas]


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
