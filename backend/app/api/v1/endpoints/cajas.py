"""CU16 Arqueo y cierre de caja (2do parcial).

- Caja fisica: el personal la abre en su sucursal con un fondo inicial y la
  cierra contando el efectivo; queda el arqueo (esperado, contado y
  diferencia). Sin caja abierta no se cobra en mostrador (trg_venta_caja).
- Caja online: una por tienda y por dia, se abre y se cierra sola. Junta las
  ventas en linea (PayPal o QR), tambien las que entran con la tienda
  cerrada.
- Administrador: todas las sucursales y la caja online. Encargado y Cajero:
  solo su sucursal. SuperAdministrador: elige la tienda (X-Empresa) y ve lo
  mismo que el Administrador, sin operar.
Las reglas viven en la migracion a4c6e8f0b123.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.deps import require_permiso, sucursal_restringida, verificar_acceso_sucursal
from app.core.audit import log_bitacora
from app.core.errores_db import http_desde_pg
from app.db.session import get_db
from app.models import Usuario
from app.schemas.cajas import (
    AbrirCajaIn,
    CajaDetalleOut,
    CajaOut,
    CerrarCajaIn,
    EstadoTiendaOut,
    MovimientoCajaIn,
    MovimientoCajaOut,
    PanelCajaOut,
    ResumenCajaOut,
    SucursalCajaOut,
    VentaCajaOut,
)

router = APIRouter()

PERMISO = "2P-CU16"

_HOY = "fn_dia_bolivia(now()::timestamp)"

_SQL_CAJA = f"""
    SELECT c.id, c.tipo, c.sucursal_id, c.fecha, c.abierta_en, c.monto_inicial, c.efectivo_esperado,
           c.efectivo_contado, c.diferencia, c.observacion,
           s.nombre AS sucursal_nombre, ua.nombre AS abierta_por_nombre, ua.tipo AS abierta_por_rol,
           uc.nombre AS cerrada_por_nombre,
           CASE WHEN c.tipo = 'online' THEN CASE WHEN c.fecha < {_HOY} THEN 'cerrada' ELSE 'abierta' END
                WHEN c.cerrada_en IS NULL THEN 'abierta' ELSE 'cerrada' END AS estado,
           CASE WHEN c.tipo = 'online' AND c.fecha < {_HOY} THEN c.abierta_en + interval '1 day'
                ELSE c.cerrada_en END AS cerrada_en,
           r.ventas AS r_ventas, r.total_ventas AS r_total_ventas, r.efectivo AS r_efectivo, r.qr AS r_qr,
           r.paypal AS r_paypal, r.otros AS r_otros, r.ingresos AS r_ingresos, r.retiros AS r_retiros,
           r.devoluciones_efectivo AS r_devoluciones_efectivo, r.efectivo_esperado AS r_efectivo_esperado
    FROM caja c
    LEFT JOIN sucursal s ON s.id = c.sucursal_id
    LEFT JOIN usuario ua ON ua.id = c.abierta_por_id
    LEFT JOIN usuario uc ON uc.id = c.cerrada_por_id
    CROSS JOIN LATERAL fn_resumen_caja(c.id) r
"""


def _to_out(f) -> dict:
    return dict(
        id=f["id"],
        tipo=f["tipo"],
        estado=f["estado"],
        sucursal_id=f["sucursal_id"],
        sucursal_nombre=f["sucursal_nombre"],
        fecha=f["fecha"],
        abierta_en=f["abierta_en"],
        abierta_por_nombre=f["abierta_por_nombre"],
        abierta_por_rol=f["abierta_por_rol"],
        cerrada_en=f["cerrada_en"],
        cerrada_por_nombre=f["cerrada_por_nombre"],
        monto_inicial=f["monto_inicial"],
        efectivo_esperado=f["efectivo_esperado"],
        efectivo_contado=f["efectivo_contado"],
        diferencia=f["diferencia"],
        observacion=f["observacion"],
        resumen=ResumenCajaOut(**{k[2:]: f[k] for k in f.keys() if k.startswith("r_")}),
    )


def _empresa_actual(db: Session, usuario: Usuario) -> int:
    """La tienda del personal, o la que eligio el SuperAdministrador."""
    empresa = db.execute(text("SELECT fn_empresa_actual()")).scalar()
    if empresa is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Elige primero la tienda de la que quieres ver las cajas.")
    return empresa


def _puede_operar(usuario: Usuario) -> bool:
    # El SuperAdministrador mira; abren y cierran las cajas los empleados.
    return usuario.empresa_id is not None


def _caja(db: Session, usuario: Usuario, caja_id: int):
    fila = db.execute(text(_SQL_CAJA + " WHERE c.id = :id"), {"id": caja_id}).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caja no encontrada.")
    restringida = sucursal_restringida(usuario)
    if restringida is not None and fila["sucursal_id"] != restringida:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puedes ver las cajas de tu sucursal.")
    return fila


def _ejecutar(db: Session, sql: str, params: dict):
    try:
        resultado = db.execute(text(sql), params).scalar()
    except DBAPIError as exc:
        db.rollback()
        traducido = http_desde_pg(exc)
        if traducido is not None:
            raise traducido
        raise
    return resultado


@router.get("/panel", response_model=PanelCajaOut)
def panel(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> PanelCajaOut:
    """Estado actual: cada sucursal con su caja abierta y la caja online de hoy."""
    empresa = _empresa_actual(db, usuario)
    restringida = sucursal_restringida(usuario)
    sql = "SELECT id, nombre, horario_atencion FROM sucursal WHERE empresa_id = :e AND estado = 'activa'"
    params: dict = {"e": empresa}
    if restringida is not None:
        sql += " AND id = :s"
        params["s"] = restringida
    sucursales = db.execute(text(sql + " ORDER BY nombre"), params).mappings().all()
    abiertas = {
        f["sucursal_id"]: f
        for f in db.execute(
            text(_SQL_CAJA + " WHERE c.empresa_id = :e AND c.tipo = 'fisica' AND c.cerrada_en IS NULL"), {"e": empresa}
        ).mappings()
    }
    online = None
    if restringida is None:
        fila = (
            db.execute(text(_SQL_CAJA + f" WHERE c.empresa_id = :e AND c.tipo = 'online' AND c.fecha = {_HOY}"), {"e": empresa})
            .mappings()
            .first()
        )
        online = CajaOut(**_to_out(fila)) if fila else None
    return PanelCajaOut(
        sucursales=[
            SucursalCajaOut(
                id=s["id"],
                nombre=s["nombre"],
                horario_atencion=s["horario_atencion"],
                caja=CajaOut(**_to_out(abiertas[s["id"]])) if s["id"] in abiertas else None,
            )
            for s in sucursales
        ],
        online=online,
        puede_operar=_puede_operar(usuario),
    )


@router.get("", response_model=list[CajaOut])
def historial(
    sucursal_id: int | None = Query(default=None),
    tipo: str | None = Query(default=None, pattern="^(fisica|online)$"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> list[CajaOut]:
    """Historial de cajas, de la mas reciente a la mas antigua."""
    empresa = _empresa_actual(db, usuario)
    sql = _SQL_CAJA + " WHERE c.empresa_id = :e"
    params: dict = {"e": empresa}
    restringida = sucursal_restringida(usuario)
    if restringida is not None:
        # Encargado y Cajero: solo las cajas fisicas de su sucursal.
        sql += " AND c.sucursal_id = :s"
        params["s"] = restringida
    elif sucursal_id is not None:
        sql += " AND c.sucursal_id = :s"
        params["s"] = sucursal_id
    if tipo:
        sql += " AND c.tipo = :t"
        params["t"] = tipo
    filas = db.execute(text(sql + " ORDER BY c.abierta_en DESC, c.id DESC LIMIT 200"), params).mappings().all()
    return [CajaOut(**_to_out(f)) for f in filas]


@router.get("/{caja_id}", response_model=CajaDetalleOut)
def detalle(
    caja_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> CajaDetalleOut:
    """Una caja con sus movimientos de efectivo y todas sus ventas."""
    fila = _caja(db, usuario, caja_id)
    movimientos = db.execute(
        text(
            """SELECT m.id, m.tipo, m.monto, m.motivo, u.nombre AS usuario_nombre, m.fecha
               FROM movimiento_caja m LEFT JOIN usuario u ON u.id = m.usuario_id
               WHERE m.caja_id = :id ORDER BY m.fecha"""
        ),
        {"id": caja_id},
    ).mappings().all()
    ventas = db.execute(
        text(
            """SELECT v.id, v.fecha, v.tipo, v.origen, v.estado, v.total, v.fuera_de_arqueo,
                      coalesce(v.factura_nombre, u.nombre, 'Cliente') AS cliente,
                      p.metodo AS metodo_pago, p.estado AS estado_pago, ue.nombre AS atendido_por
               FROM venta v
               LEFT JOIN usuario u ON u.id = v.cliente_id
               LEFT JOIN pago p ON p.venta_id = v.id
               LEFT JOIN venta_presencial vp ON vp.id = v.id
               LEFT JOIN usuario ue ON ue.id = vp.empleado_id
               WHERE v.caja_id = :id
               ORDER BY v.fecha"""
        ),
        {"id": caja_id},
    ).mappings().all()
    return CajaDetalleOut(
        **_to_out(fila),
        movimientos=[MovimientoCajaOut(**m) for m in movimientos],
        ventas_detalle=[VentaCajaOut(**v) for v in ventas],
    )


@router.post("/abrir", response_model=CajaOut, status_code=status.HTTP_201_CREATED)
def abrir(
    payload: AbrirCajaIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> CajaOut:
    if not _puede_operar(usuario):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Las cajas las abre el personal de la tienda.")
    verificar_acceso_sucursal(usuario, payload.sucursal_id)
    caja_id = _ejecutar(
        db,
        "SELECT sp_abrir_caja(:s, :u, :m)",
        {"s": payload.sucursal_id, "u": usuario.id, "m": payload.monto_inicial},
    )
    log_bitacora(db, usuario, "CREAR", "caja", caja_id, f"Abrió la caja con un fondo de Bs {payload.monto_inicial}", request)
    db.commit()
    return CajaOut(**_to_out(_caja(db, usuario, caja_id)))


def _caja_fisica_abierta(db: Session, usuario: Usuario, caja_id: int):
    if not _puede_operar(usuario):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Las cajas las opera el personal de la tienda.")
    fila = _caja(db, usuario, caja_id)
    if fila["tipo"] != "fisica" or fila["estado"] != "abierta":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa caja ya está cerrada.")
    return fila


@router.post("/{caja_id}/movimientos", response_model=CajaDetalleOut, status_code=status.HTTP_201_CREATED)
def registrar_movimiento(
    caja_id: int,
    payload: MovimientoCajaIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> CajaDetalleOut:
    """Ingreso o retiro de efectivo durante el turno (ej. llevar plata al banco)."""
    _caja_fisica_abierta(db, usuario, caja_id)
    db.execute(
        text("INSERT INTO movimiento_caja (caja_id, tipo, monto, motivo, usuario_id) VALUES (:c, :t, :m, :mo, :u)"),
        {"c": caja_id, "t": payload.tipo, "m": payload.monto, "mo": payload.motivo.strip(), "u": usuario.id},
    )
    log_bitacora(
        db, usuario, "CREAR", "caja", caja_id, f"{payload.tipo.capitalize()} de Bs {payload.monto}: {payload.motivo.strip()}", request
    )
    db.commit()
    return detalle(caja_id, db, usuario)


@router.post("/{caja_id}/cerrar", response_model=CajaDetalleOut)
def cerrar(
    caja_id: int,
    payload: CerrarCajaIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> CajaDetalleOut:
    """Arqueo: el efectivo contado contra el esperado; queda la diferencia."""
    _caja_fisica_abierta(db, usuario, caja_id)
    _ejecutar(
        db,
        "SELECT sp_cerrar_caja(:c, :u, :m, :o)",
        {"c": caja_id, "u": usuario.id, "m": payload.efectivo_contado, "o": payload.observacion},
    )
    log_bitacora(db, usuario, "ACTUALIZAR", "caja", caja_id, f"Cerró la caja: contó Bs {payload.efectivo_contado}", request)
    db.commit()
    return detalle(caja_id, db, usuario)


# Publico (checkout): si la sucursal esta atendiendo ahora mismo.
publico_router = APIRouter()


@publico_router.get("/sucursal/{sucursal_id}/estado", response_model=EstadoTiendaOut)
def estado_sucursal(sucursal_id: int, db: Session = Depends(get_db)) -> EstadoTiendaOut:
    fila = db.execute(
        text(
            """SELECT s.horario_atencion,
                      EXISTS (SELECT 1 FROM caja c WHERE c.tipo = 'fisica' AND c.sucursal_id = s.id
                              AND c.cerrada_en IS NULL) AS abierta
               FROM sucursal s WHERE s.id = :s"""
        ),
        {"s": sucursal_id},
    ).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sucursal no encontrada.")
    return EstadoTiendaOut(abierta=fila["abierta"], horario_atencion=fila["horario_atencion"])
