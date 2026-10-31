"""Compra de la suscripcion de una boutique desde la portada (/empezar).

1. cotizar:   valida todo ANTES de cobrar (correo del administrador libre,
              sucursales dentro del plan) y devuelve el precio en Bs y en USD.
2. orden:     crea la orden de PayPal por el monto en USD (tipo de cambio
              oficial). Todavia no cobra nada.
3. confirmar: verifica que la orden este aprobada y por el monto exacto, la
              cobra y registra empresa + suscripcion + Administrador + pago
              (sp_registrar_empresa_suscrita). Si la base falla despues de
              cobrar, se devuelve el dinero. Envia las credenciales del
              Administrador al correo del cliente que compro.
El plan Prueba no pasa por PayPal: confirmar lo activa directo.
"""

import base64
import html
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import set_client_ip_for_trigger
from app.core.email import send_email
from app.core.errores_db import http_desde_pg
from app.core.paypal import (
    PAYPAL_CURRENCY,
    captura_de,
    capturar_orden,
    crear_orden,
    obtener_orden,
    reembolsar_captura,
)
from app.core.security import generate_temp_password, hash_password
from app.core.storage import upload_logo_empresa
from app.db.session import get_db
from app.models import Usuario
from app.schemas.registro_empresa import (
    ConfirmarSuscripcionIn,
    CotizacionOut,
    OrdenSuscripcionOut,
    SolicitudSuscripcionIn,
    SuscripcionCreadaOut,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/enlace-disponible")
def enlace_disponible(
    texto: str, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)
) -> dict:
    # Enlace que quedaria para la tienda: si ya lo usa otra, con un numero al
    # final (el mismo criterio que aplica sp_crear_empresa al guardar).
    subdominio = db.execute(text("SELECT fn_subdominio_disponible(:t)"), {"t": texto[:80]}).scalar()
    return {"subdominio": subdominio}


def _cotizar(db: Session, payload: SolicitudSuscripcionIn) -> CotizacionOut:
    """Precio del plan y validaciones que se hacen antes de cobrar."""
    fila = db.execute(
        text("SELECT * FROM fn_cotizar_suscripcion(:plan, :periodo)"),
        {"plan": payload.plan, "periodo": payload.periodo},
    ).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Plan o periodo de pago no válido.")

    if payload.boutique.sucursales > fila["max_sucursales"]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"El plan {fila['plan_nombre']} permite hasta {fila['max_sucursales']} "
            f"{'sucursal' if fila['max_sucursales'] == 1 else 'sucursales'}.",
        )

    correo = payload.administrador.email.strip().lower()
    if db.execute(text("SELECT 1 FROM usuario WHERE lower(email) = :c"), {"c": correo}).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ese correo ya tiene una cuenta en Arlani. Usa otro correo para el administrador de tu boutique.",
        )

    subdominio = db.execute(
        text("SELECT fn_subdominio_disponible(:t)"), {"t": payload.boutique.subdominio}
    ).scalar()
    return CotizacionOut(**fila, requiere_pago=fila["monto_bob"] > 0, subdominio=subdominio)


@router.post("/registro/cotizar", response_model=CotizacionOut)
def cotizar(
    payload: SolicitudSuscripcionIn, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)
) -> CotizacionOut:
    return _cotizar(db, payload)


@router.post("/registro/orden", response_model=OrdenSuscripcionOut)
def crear_orden_suscripcion(
    payload: SolicitudSuscripcionIn,
    request: Request,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
) -> OrdenSuscripcionOut:
    cot = _cotizar(db, payload)
    if not cot.requiere_pago:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El plan de prueba no requiere pago.")
    base = str(request.base_url).rstrip("/")
    orden = crear_orden(
        cot.monto_usd,
        referencia=f"SUSC-{cot.plan_codigo}-{cot.periodo}",
        return_url=f"{base}/paypal-embed/retorno",
        cancel_url=f"{base}/paypal-embed/cancelado",
    )
    approve = next((l["href"] for l in orden.get("links", []) if l.get("rel") in ("approve", "payer-action")), None)
    return OrdenSuscripcionOut(
        order_id=orden["id"], monto_usd=cot.monto_usd, monto_bob=cot.monto_bob, approve_url=approve
    )


def _monto_de(unidad: dict) -> tuple[Decimal, str]:
    monto = unidad.get("amount") or {}
    return Decimal(str(monto.get("value", "0"))), monto.get("currency_code", "")


def _cobrar(order_id: str, esperado: Decimal) -> str:
    """Verifica la orden (aprobada, en USD, por el monto cotizado) y la cobra.
    Devuelve el id de la captura."""
    orden = obtener_orden(order_id)
    if orden.get("status") != "APPROVED":
        raise HTTPException(status.HTTP_409_CONFLICT, "El pago todavía no fue aprobado en PayPal.")
    monto, moneda = _monto_de((orden.get("purchase_units") or [{}])[0])
    if moneda != PAYPAL_CURRENCY or monto != esperado:
        raise HTTPException(status.HTTP_409_CONFLICT, "El monto de la orden de PayPal no coincide con el plan.")

    captura = captura_de(capturar_orden(order_id))
    if not captura or captura.get("status") != "COMPLETED":
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "PayPal no completó el cobro. No se te cobró nada.")
    cobrado, _ = _monto_de(captura)
    if cobrado != esperado:
        reembolsar_captura(captura["id"])
        raise HTTPException(status.HTTP_409_CONFLICT, "El cobro no coincidió con el plan y se devolvió el pago.")
    return captura["id"]


def _decodificar_logo(data_url: str) -> bytes | None:
    try:
        _, _, b64 = data_url.partition(",")
        return base64.b64decode(b64 or data_url, validate=False)
    except (ValueError, TypeError):
        return None


def _correo_credenciales(
    origen: str, empresa: str, subdominio: str, plan: str, cliente_nombre: str, admin_email: str, clave: str
) -> str:
    e = html.escape
    return (
        f"<p>Hola {e(cliente_nombre)},</p>"
        f"<p><strong>{e(empresa)}</strong> ya es parte de <strong>Arlani Boutiques</strong> "
        f"con el plan {e(plan)}.</p>"
        "<p>Estas son las credenciales del <strong>Administrador</strong> de tu boutique:</p>"
        f"<p>Correo: {e(admin_email)}<br>Contraseña temporal: <strong>{e(clave)}</strong></p>"
        "<p><strong>Por seguridad, cambia esta contraseña</strong> desde tu perfil apenas inicies sesión.</p>"
        f'<p>Inicia sesión en <a href="{e(origen)}/login">{e(origen)}/login</a>.</p>'
        f'<p>El enlace de tu tienda es <a href="{e(origen)}/tienda-{e(subdominio)}">'
        f"{e(origen)}/tienda-{e(subdominio)}</a>.</p>"
    )


@router.post("/registro/confirmar", response_model=SuscripcionCreadaOut, status_code=status.HTTP_201_CREATED)
def confirmar_suscripcion(
    payload: ConfirmarSuscripcionIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> SuscripcionCreadaOut:
    cot = _cotizar(db, payload)

    order_id: str | None = None
    capture_id: str | None = None
    if cot.requiere_pago:
        if not payload.order_id:
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Este plan requiere el pago de la suscripción.")
        ya_usada = db.execute(
            text("SELECT 1 FROM pago_suscripcion WHERE paypal_order_id = :o"), {"o": payload.order_id}
        ).first()
        if ya_usada:
            raise HTTPException(status.HTTP_409_CONFLICT, "Esa orden de PayPal ya se usó para otra suscripción.")
        order_id = payload.order_id
        capture_id = _cobrar(order_id, cot.monto_usd)

    clave = generate_temp_password()
    admin_email = payload.administrador.email.strip().lower()
    try:
        # El cliente que compra queda como propietario y es quien aparece en
        # la bitacora (triggers de auditoria).
        db.execute(text("SELECT set_config('arlani.usuario_id', :id, true)"), {"id": str(usuario.id)})
        set_client_ip_for_trigger(db, request)
        creada = db.execute(
            text(
                "SELECT * FROM sp_registrar_empresa_suscrita(:nombre, :subdominio, :ciudad, :color, :plan, "
                ":periodo, :propietario, :admin_nombre, :admin_email, :admin_hash, :order_id, :capture_id, :usd)"
            ),
            {
                "nombre": payload.boutique.nombre.strip(),
                "subdominio": payload.boutique.subdominio,
                "ciudad": payload.boutique.ciudad,
                "color": payload.boutique.color,
                "plan": cot.plan_codigo,
                "periodo": payload.periodo,
                "propietario": usuario.id,
                "admin_nombre": payload.administrador.nombre.strip(),
                "admin_email": admin_email,
                "admin_hash": hash_password(clave),
                "order_id": order_id,
                "capture_id": capture_id,
                "usd": cot.monto_usd if order_id else Decimal(0),
            },
        ).mappings().one()
        publicos = sorted({x for x in payload.boutique.publicos if x in ("mujer", "hombre", "unisex", "nina", "nino", "bebe")})
        db.execute(text("UPDATE empresa SET publicos = :p WHERE subdominio = :s"),
                   {"p": publicos, "s": payload.boutique.subdominio})
        db.commit()
    except Exception as err:
        db.rollback()
        # PayPal ya cobro pero la boutique no se pudo registrar: se devuelve.
        if capture_id:
            devuelto = reembolsar_captura(capture_id)
            logger.exception("Alta de boutique fallida tras cobrar (orden %s, reembolso=%s)", order_id, devuelto)
        http = http_desde_pg(err) if isinstance(err, DBAPIError) else None
        detalle = http.detail if http else "No pudimos registrar tu boutique."
        if capture_id:
            detalle = f"{detalle} Te devolvimos el pago en PayPal."
        raise HTTPException(http.status_code if http else status.HTTP_500_INTERNAL_SERVER_ERROR, detalle) from err

    # Logo: si falla, la boutique queda creada igual (se puede subir despues).
    logo_guardado = False
    contenido = _decodificar_logo(payload.logo) if payload.logo else None
    if contenido:
        try:
            url = upload_logo_empresa(creada["empresa_id"], contenido)
            db.execute(
                text("UPDATE empresa SET logo_url = :u WHERE id = :id"), {"u": url, "id": creada["empresa_id"]}
            )
            db.commit()
            logo_guardado = True
        except Exception:
            db.rollback()
            logger.exception("No se pudo guardar el logo de la empresa %s", creada["empresa_id"])

    # Las credenciales van al correo del cliente que compro (su cuenta de
    # Arlani): el correo del Administrador es el usuario con el que se entra.
    origen = (request.headers.get("origin") or str(request.base_url)).rstrip("/")
    destino = usuario.email
    correo_enviado = False
    try:
        send_email(
            to=destino,
            subject=f"Tu boutique {payload.boutique.nombre.strip()} ya está en Arlani Boutiques",
            html_body=_correo_credenciales(
                origen,
                payload.boutique.nombre.strip(),
                creada["subdominio"],
                cot.plan_nombre,
                usuario.nombre,
                admin_email,
                clave,
            ),
        )
        correo_enviado = True
    except Exception:
        logger.exception("No se pudo enviar las credenciales a %s", destino)

    return SuscripcionCreadaOut(
        empresa_id=creada["empresa_id"],
        empresa_nombre=payload.boutique.nombre.strip(),
        subdominio=creada["subdominio"],
        plan_nombre=cot.plan_nombre,
        admin_email=admin_email,
        correo_destino=destino,
        metodo="paypal" if order_id else "prueba",
        monto_bob=cot.monto_bob,
        monto_usd=cot.monto_usd if order_id else Decimal(0),
        logo_guardado=logo_guardado,
        correo_enviado=correo_enviado,
    )
