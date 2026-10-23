"""Lo que una tienda (tenant) ve de si misma en la plataforma.

- /mi-empresa/marca: nombre, logo y color de la tienda del usuario (su panel,
  sus reportes y comprobantes se ven con su marca).
- PUT /mi-empresa/marca: el Administrador cambia el logo o el color.
- /mi-empresa/suscripcion: el Administrador de la tienda ve su plan, cuando
  vence, cuanto usa de el y los planes a los que puede cambiarse. La empresa
  sale siempre de la sesion, nunca de un parametro.
- /mi-empresa/suscripcion/{cotizar,orden,confirmar}: compra o renueva su plan
  pagando con PayPal (a la cuenta de Arlani). Con la suscripcion vencida es
  lo unico que la tienda puede hacer.
- /tiendas: las tiendas activas (carrusel de la portada).
- /tiendas/{subdominio}: datos publicos de una tienda para su enlace
  /tienda-<subdominio> (no hace falta dominio propio).
"""

import base64
import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_administrador
from app.api.v1.endpoints.metodos_pago import _empresa_operada
from app.api.v1.endpoints.registro_empresa import _cobrar
from app.core.audit import set_client_ip_for_trigger
from app.core.errores_db import http_desde_pg
from app.core.paypal import crear_orden, reembolsar_captura
from app.core.storage import upload_logo_empresa
from app.db.session import get_db
from app.models import Usuario
from app.schemas.metodos_pago import FacturacionIO
from app.schemas.mi_empresa import (
    ConfirmarRenovacionIn,
    ConfirmarSaldoIn,
    CotizacionRenovacionOut,
    CuentaTiendaOut,
    HistorialSuscripcionOut,
    LiquidacionRecibidaOut,
    MarcaEmpresaIn,
    MarcaEmpresaOut,
    MiSuscripcionOut,
    MovimientoCuentaOut,
    OrdenRenovacionOut,
    OrdenSaldoOut,
    PlanDisponibleOut,
    RenovacionIn,
    SucursalPublicaOut,
    TiendaPublicaOut,
    TiendaResumenOut,
)

logger = logging.getLogger(__name__)
router = APIRouter()
tiendas_router = APIRouter()


def _admin_de_tienda(admin: Usuario = Depends(require_administrador)) -> Usuario:
    # El SuperAdministrador no pertenece a ninguna tienda: ve las
    # suscripciones de todas en /plataforma/empresas.
    if admin.empresa_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Esta pantalla es del Administrador de cada tienda; desde la plataforma se ve en Empresas.",
        )
    return admin


@router.get("/marca", response_model=MarcaEmpresaOut)
def mi_marca(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)) -> MarcaEmpresaOut:
    if usuario.empresa_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tu cuenta no pertenece a una tienda.")
    fila = db.execute(
        text(
            "SELECT nombre, subdominio, ciudad, color_marca, logo_url, email_contacto, "
            "fn_empresa_operativa(id) AS operativa FROM empresa WHERE id = :e"
        ),
        {"e": usuario.empresa_id},
    ).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa no encontrada.")
    return MarcaEmpresaOut(**fila)


@router.put("/marca", response_model=MarcaEmpresaOut)
def actualizar_marca(
    payload: MarcaEmpresaIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(_admin_de_tienda),
) -> MarcaEmpresaOut:
    cambios: dict[str, object] = {}
    if payload.color_marca:
        cambios["color_marca"] = payload.color_marca.lower()
    if payload.quitar_logo:
        cambios["logo_url"] = None
    elif payload.logo:
        try:
            contenido = base64.b64decode(payload.logo.partition(",")[2] or payload.logo)
        except ValueError as err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El logo no es una imagen válida.") from err
        cambios["logo_url"] = upload_logo_empresa(admin.empresa_id, contenido)

    if cambios:
        # trg_auditar_plataforma deja el cambio en la bitacora de la tienda.
        db.execute(text("SELECT set_config('arlani.usuario_id', :id, true)"), {"id": str(admin.id)})
        set_client_ip_for_trigger(db, request)
        asignaciones = ", ".join(f"{columna} = :{columna}" for columna in cambios)
        db.execute(text(f"UPDATE empresa SET {asignaciones} WHERE id = :e"), {**cambios, "e": admin.empresa_id})
        db.commit()
    return mi_marca(db, admin)


@router.get("/facturacion", response_model=FacturacionIO)
def mi_facturacion(db: Session = Depends(get_db), empresa: int = Depends(_empresa_operada)) -> FacturacionIO:
    fila = db.execute(
        text("SELECT razon_social, nit, direccion_fiscal, telefono, email_contacto FROM empresa WHERE id = :e"),
        {"e": empresa},
    ).mappings().first()
    return FacturacionIO(**fila)


@router.put("/facturacion", response_model=FacturacionIO)
def actualizar_facturacion(
    payload: FacturacionIO,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_administrador),
    empresa: int = Depends(_empresa_operada),
) -> FacturacionIO:
    """Datos que salen en las facturas de la tienda (cada tienda factura lo suyo)."""
    datos = {k: ((v or "").strip() or None) for k, v in payload.model_dump().items()}
    db.execute(text("SELECT set_config('arlani.usuario_id', :id, true)"), {"id": str(admin.id)})
    set_client_ip_for_trigger(db, request)
    db.execute(
        text(
            "UPDATE empresa SET razon_social = :razon_social, nit = :nit, direccion_fiscal = :direccion_fiscal, "
            "telefono = :telefono, email_contacto = :email_contacto WHERE id = :e"
        ),
        {**datos, "e": empresa},
    )
    db.commit()
    return mi_facturacion(db, empresa)


@router.get("/suscripcion", response_model=MiSuscripcionOut)
def mi_suscripcion(db: Session = Depends(get_db), admin: Usuario = Depends(_admin_de_tienda)) -> MiSuscripcionOut:
    fila = db.execute(text("SELECT * FROM fn_mi_suscripcion(:e)"), {"e": admin.empresa_id}).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa no encontrada.")

    historial = db.execute(text("SELECT * FROM fn_historial_suscripciones(:e)"), {"e": admin.empresa_id}).mappings().all()
    planes = db.execute(
        text(
            "SELECT codigo, nombre, precio_mensual, max_sucursales, dias_prueba, ia_generativa, operacion_offline, "
            "comision_pct FROM plan_suscripcion WHERE activo ORDER BY orden"
        )
    ).mappings().all()
    return MiSuscripcionOut(
        **fila,
        historial=[HistorialSuscripcionOut(**h) for h in historial],
        planes=[PlanDisponibleOut(**p) for p in planes],
    )


def _cotizar_renovacion(db: Session, empresa_id: int, payload: RenovacionIn) -> CotizacionRenovacionOut:
    """Precio del plan y validaciones antes de cobrar."""
    fila = db.execute(
        text("SELECT * FROM fn_cotizar_suscripcion(:plan, :periodo)"),
        {"plan": payload.plan, "periodo": payload.periodo},
    ).mappings().first()
    plan = db.execute(
        text("SELECT id, dias_prueba, max_sucursales FROM plan_suscripcion WHERE codigo = :c AND activo"),
        {"c": payload.plan},
    ).mappings().first()
    if fila is None or plan is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Plan o periodo de pago no válido.")
    if plan["dias_prueba"] is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "El plan de prueba no se puede volver a contratar: elige el plan Básico o Profesional.",
        )
    usadas = db.execute(
        text("SELECT count(*) FROM sucursal WHERE empresa_id = :e AND estado = 'activa'"), {"e": empresa_id}
    ).scalar()
    if usadas > plan["max_sucursales"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Tienes {usadas} sucursales activas y el plan {fila['plan_nombre']} permite "
            f"{plan['max_sucursales']}. Desactiva sucursales o elige un plan mayor.",
        )
    hoy = db.execute(text("SELECT (now() AT TIME ZONE 'America/La_Paz')::date")).scalar()
    actual = db.execute(
        text("SELECT plan_id, fecha_fin FROM suscripcion WHERE empresa_id = :e AND estado = 'activa'"),
        {"e": empresa_id},
    ).mappings().first()
    # Renovar el mismo plan antes de que venza: el nuevo periodo empieza al
    # terminar el actual. Cambiar de plan (o renovar vencido): desde hoy.
    inicio = hoy
    if actual and actual["plan_id"] == plan["id"] and actual["fecha_fin"] and actual["fecha_fin"] >= hoy:
        inicio = actual["fecha_fin"] + timedelta(days=1)
    # Las comisiones pendientes se cobran junto con el plan.
    comisiones_bob, comisiones_usd, _ = _saldo(db, empresa_id)
    return CotizacionRenovacionOut(
        plan_codigo=fila["plan_codigo"],
        plan_nombre=fila["plan_nombre"],
        periodo=fila["periodo"],
        monto_bob=fila["monto_bob"] + comisiones_bob,
        tipo_cambio=fila["tipo_cambio"],
        monto_usd=fila["monto_usd"] + comisiones_usd,
        plan_bob=fila["monto_bob"],
        plan_usd=fila["monto_usd"],
        comisiones_bob=comisiones_bob,
        comisiones_usd=comisiones_usd,
        fecha_inicio=inicio,
    )


def _saldo(db: Session, empresa_id: int) -> tuple[Decimal, Decimal, Decimal]:
    """Comisiones que la tienda debe hoy, en Bs y en US$ al cambio oficial."""
    fila = db.execute(
        text(
            "SELECT GREATEST(fn_saldo_cuenta_tienda(:e), 0) AS bob, fn_tipo_cambio_oficial() AS tc"
        ),
        {"e": empresa_id},
    ).mappings().first()
    bob = Decimal(fila["bob"]).quantize(Decimal("0.01"))
    tc = Decimal(fila["tc"])
    return bob, (bob / tc).quantize(Decimal("0.01"), ROUND_HALF_UP), tc


@router.post("/suscripcion/cotizar", response_model=CotizacionRenovacionOut)
def cotizar_renovacion(
    payload: RenovacionIn, db: Session = Depends(get_db), admin: Usuario = Depends(_admin_de_tienda)
) -> CotizacionRenovacionOut:
    return _cotizar_renovacion(db, admin.empresa_id, payload)


@router.post("/suscripcion/orden", response_model=OrdenRenovacionOut)
def orden_renovacion(
    payload: RenovacionIn, db: Session = Depends(get_db), admin: Usuario = Depends(_admin_de_tienda)
) -> OrdenRenovacionOut:
    cot = _cotizar_renovacion(db, admin.empresa_id, payload)
    orden = crear_orden(cot.monto_usd, referencia=f"RENOV-{admin.empresa_id}-{cot.plan_codigo}-{cot.periodo}")
    return OrdenRenovacionOut(order_id=orden["id"], monto_usd=cot.monto_usd, monto_bob=cot.monto_bob)


@router.post("/suscripcion/confirmar", response_model=MiSuscripcionOut)
def confirmar_renovacion(
    payload: ConfirmarRenovacionIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(_admin_de_tienda),
) -> MiSuscripcionOut:
    cot = _cotizar_renovacion(db, admin.empresa_id, payload)
    usada = db.execute(
        text("SELECT 1 FROM pago_suscripcion WHERE paypal_order_id = :o"), {"o": payload.order_id}
    ).first()
    if usada:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese pago de PayPal ya se usó para otra suscripción.")
    capture_id = _cobrar(payload.order_id, cot.monto_usd)
    try:
        db.execute(text("SELECT set_config('arlani.usuario_id', :id, true)"), {"id": str(admin.id)})
        set_client_ip_for_trigger(db, request)
        db.execute(
            text("SELECT sp_renovar_suscripcion(:e, :plan, :periodo, :orden, :captura, :usd)"),
            {
                "e": admin.empresa_id,
                "plan": cot.plan_codigo,
                "periodo": payload.periodo,
                "orden": payload.order_id,
                "captura": capture_id,
                "usd": cot.plan_usd,
            },
        )
        if cot.comisiones_bob > 0:
            _registrar_pago_saldo(db, admin.empresa_id, cot.comisiones_bob, cot.comisiones_usd, cot.tipo_cambio,
                                  payload.order_id, capture_id)
        db.commit()
    except Exception as err:
        db.rollback()
        # PayPal ya cobro pero no se pudo registrar: se devuelve el pago.
        devuelto = reembolsar_captura(capture_id)
        logger.exception("Renovacion fallida tras cobrar (orden %s, reembolso=%s)", payload.order_id, devuelto)
        http = http_desde_pg(err) if isinstance(err, DBAPIError) else None
        detalle = (http.detail if http else "No pudimos registrar tu suscripción.") + " Te devolvimos el pago en PayPal."
        raise HTTPException(http.status_code if http else status.HTTP_500_INTERNAL_SERVER_ERROR, detalle) from err
    return mi_suscripcion(db, admin)


# ------------------------------------------------------ estado de cuenta
# Comision de Arlani por cada venta en linea: la tienda la ve aca y paga su
# saldo con PayPal cuando quiera (o junto con la renovacion de su plan).


def _registrar_pago_saldo(
    db: Session, empresa_id: int, bob: Decimal, usd: Decimal, tc: Decimal, order_id: str, capture_id: str
) -> None:
    db.execute(
        text("SELECT sp_pagar_saldo_tienda(:e, :bob, :usd, :tc, :orden, :captura)"),
        {"e": empresa_id, "bob": bob, "usd": usd, "tc": tc, "orden": order_id, "captura": capture_id},
    )


@router.get("/cuenta", response_model=CuentaTiendaOut)
def mi_cuenta(db: Session = Depends(get_db), admin: Usuario = Depends(_admin_de_tienda)) -> CuentaTiendaOut:
    saldo_bob, saldo_usd, tc = _saldo(db, admin.empresa_id)
    mes = db.execute(
        text(
            "SELECT count(*) AS ventas, COALESCE(sum(base_bob), 0) AS base, COALESCE(sum(monto_bob), 0) AS comision "
            "FROM cuenta_tienda_movimiento WHERE empresa_id = :e AND tipo = 'comision' "
            # fecha en UTC; el mes se cuenta en hora de Bolivia.
            "AND fecha AT TIME ZONE 'UTC' AT TIME ZONE 'America/La_Paz' >= date_trunc('month', now() AT TIME ZONE 'America/La_Paz')"
        ),
        {"e": admin.empresa_id},
    ).mappings().first()
    pagado = db.execute(
        text("SELECT COALESCE(-sum(monto_bob), 0) FROM cuenta_tienda_movimiento WHERE empresa_id = :e AND tipo = 'pago'"),
        {"e": admin.empresa_id},
    ).scalar()
    pct = db.execute(
        text(
            "SELECT p.comision_pct FROM suscripcion s JOIN plan_suscripcion p ON p.id = s.plan_id "
            "WHERE s.empresa_id = :e AND s.estado = 'activa'"
        ),
        {"e": admin.empresa_id},
    ).scalar()
    movimientos = db.execute(
        text(
            "SELECT id, fecha, tipo, venta_id, base_bob, porcentaje, monto_bob, descripcion "
            "FROM cuenta_tienda_movimiento WHERE empresa_id = :e ORDER BY fecha DESC, id DESC LIMIT 200"
        ),
        {"e": admin.empresa_id},
    ).mappings().all()
    liquidaciones = db.execute(
        text(
            "SELECT id, fecha, bruto_bob, comision_bob, neto_bob, neto_usd, paypal_email, estado "
            "FROM liquidacion_tienda WHERE empresa_id = :e ORDER BY fecha DESC LIMIT 20"
        ),
        {"e": admin.empresa_id},
    ).mappings().all()
    return CuentaTiendaOut(
        liquidaciones=[LiquidacionRecibidaOut(**l) for l in liquidaciones],
        saldo_bob=saldo_bob,
        saldo_usd=saldo_usd,
        tipo_cambio=tc,
        comision_pct=pct,
        ventas_mes=mes["ventas"],
        ventas_mes_bob=mes["base"],
        comisiones_mes_bob=mes["comision"],
        pagado_total_bob=pagado,
        movimientos=[MovimientoCuentaOut(**m) for m in movimientos],
    )


@router.post("/cuenta/orden", response_model=OrdenSaldoOut)
def orden_saldo(db: Session = Depends(get_db), admin: Usuario = Depends(_admin_de_tienda)) -> OrdenSaldoOut:
    bob, usd, _ = _saldo(db, admin.empresa_id)
    if bob <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "No tienes comisiones pendientes de pago.")
    orden = crear_orden(usd, referencia=f"COMIS-{admin.empresa_id}")
    return OrdenSaldoOut(order_id=orden["id"], monto_usd=usd, monto_bob=bob)


@router.post("/cuenta/confirmar", response_model=CuentaTiendaOut)
def confirmar_saldo(
    payload: ConfirmarSaldoIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(_admin_de_tienda),
) -> CuentaTiendaOut:
    bob, usd, tc = _saldo(db, admin.empresa_id)
    if bob <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "No tienes comisiones pendientes de pago.")
    capture_id = _cobrar(payload.order_id, usd)
    try:
        db.execute(text("SELECT set_config('arlani.usuario_id', :id, true)"), {"id": str(admin.id)})
        set_client_ip_for_trigger(db, request)
        _registrar_pago_saldo(db, admin.empresa_id, bob, usd, tc, payload.order_id, capture_id)
        db.commit()
    except Exception as err:
        db.rollback()
        devuelto = reembolsar_captura(capture_id)
        logger.exception("Pago de comisiones fallido tras cobrar (orden %s, reembolso=%s)", payload.order_id, devuelto)
        http = http_desde_pg(err) if isinstance(err, DBAPIError) else None
        detalle = (http.detail if http else "No pudimos registrar tu pago.") + " Te devolvimos el pago en PayPal."
        raise HTTPException(http.status_code if http else status.HTTP_500_INTERNAL_SERVER_ERROR, detalle) from err
    return mi_cuenta(db, admin)


@tiendas_router.get("", response_model=list[TiendaResumenOut])
def tiendas_publicas(db: Session = Depends(get_db)) -> list[TiendaResumenOut]:
    filas = db.execute(text("SELECT * FROM fn_tiendas_publicas()")).mappings().all()
    return [TiendaResumenOut(**f) for f in filas]


@tiendas_router.get("/{subdominio}", response_model=TiendaPublicaOut)
def tienda_publica(subdominio: str, db: Session = Depends(get_db)) -> TiendaPublicaOut:
    fila = db.execute(text("SELECT * FROM fn_tienda_publica(:s)"), {"s": subdominio}).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esta tienda no existe.")

    sucursales = []
    if fila["estado"] == "activa":
        sucursales = db.execute(
            text(
                "SELECT s.nombre, s.direccion, c.nombre AS ciudad, s.horario_atencion, s.telefono "
                "FROM sucursal s JOIN ciudad c ON c.id = s.ciudad_id "
                "WHERE s.empresa_id = :e AND s.estado = 'activa' ORDER BY c.nombre, s.nombre"
            ),
            {"e": fila["id"]},
        ).mappings().all()
    return TiendaPublicaOut(**fila, sucursales=[SucursalPublicaOut(**s) for s in sucursales])
