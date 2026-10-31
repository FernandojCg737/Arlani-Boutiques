"""Metodos de pago del cliente: sus cuentas PayPal (compras sin conexion que
se cobran solas).

- Automatico: cada vez que el cliente paga con PayPal en Arlani, esa cuenta
  (su correo de PayPal) queda registrada en sus Metodos de pago
  (`registrar_paypal_usado`), con cuantas veces y cuando la uso.
- Manual: "Agregar cuenta PayPal" abre la autorizacion de PayPal (Vault).
- Para cobrar una compra sin conexion PayPal exige que el cliente autorice
  esa cuenta una vez: Arlani recibe un token de cobro y lo guarda cifrado
  (nunca datos de la cuenta). Lo que compre sin conexion con "Mi PayPal
  guardado" se cobra solo al sincronizar (ver offline.py: _cobrar_pendientes).
"""

import logging
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import log_bitacora
from app.core.cifrado import cifrar, descifrar
from app.core.config import settings
from app.core.paypal import borrar_payment_token, crear_payment_token, crear_setup_token
from app.db.session import get_db
from app.models import Usuario

logger = logging.getLogger(__name__)

router = APIRouter()


class VincularIn(BaseModel):
    # A donde vuelve PayPal: la web (perfil) o la pagina del backend que
    # cierra el WebView de la app movil.
    retorno: str = Field(max_length=500)
    cancelado: str = Field(max_length=500)


class VincularOut(BaseModel):
    approve_url: str


class MetodoPagoClienteOut(BaseModel):
    id: int
    tipo: str
    cuenta: str | None
    origen: str
    autorizada: bool
    veces_usado: int
    ultimo_uso: datetime | None
    creado_en: datetime


def _cliente(usuario: Usuario) -> int:
    if usuario.tipo != "cliente":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo los clientes guardan sus métodos de pago.")
    return usuario.id


def _url_permitida(url: str, request: Request) -> bool:
    """Solo se vuelve a la web de Arlani o al propio backend (no a otro sitio)."""
    destino = urlparse(url)
    if destino.scheme not in ("http", "https") or not destino.netloc:
        return False
    propios = {urlparse(o).netloc for o in settings.cors_origins_list} | {urlparse(str(request.base_url)).netloc}
    return destino.netloc in propios


def _metodos(db: Session, cliente_id: int) -> list[MetodoPagoClienteOut]:
    filas = db.execute(
        text(
            """SELECT id, tipo, cuenta, origen, estado = 'autorizada' AS autorizada, veces_usado, ultimo_uso, creado_en
               FROM cliente_metodo_pago
               WHERE cliente_id = :c AND NOT (estado = 'pendiente' AND cuenta IS NULL)
               ORDER BY (estado = 'autorizada') DESC, ultimo_uso DESC NULLS LAST, creado_en DESC"""
        ),
        {"c": cliente_id},
    ).mappings().all()
    return [MetodoPagoClienteOut(**f) for f in filas]


@router.get("/metodos", response_model=list[MetodoPagoClienteOut])
def mis_metodos(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)) -> list[MetodoPagoClienteOut]:
    return _metodos(db, _cliente(usuario))


@router.post("/paypal/vincular", response_model=VincularOut)
def vincular_paypal(
    payload: VincularIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> VincularOut:
    """Agregar o autorizar una cuenta PayPal: abre la autorizacion de PayPal;
    al aprobar, el cliente vuelve a `retorno` y la app llama a /paypal/confirmar.
    La cuenta queda segun el correo con el que inicie sesion en PayPal."""
    cliente_id = _cliente(usuario)
    if not (_url_permitida(payload.retorno, request) and _url_permitida(payload.cancelado, request)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dirección de retorno no permitida.")
    setup = crear_setup_token(payload.retorno, payload.cancelado)
    approve = next((l["href"] for l in setup.get("links", []) if l.get("rel") == "approve"), None)
    if not approve:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "PayPal no devolvió el enlace para autorizar la cuenta.")
    # Una sola autorizacion en curso por cliente.
    db.execute(
        text("DELETE FROM cliente_metodo_pago WHERE cliente_id = :c AND estado = 'pendiente' AND cuenta IS NULL"),
        {"c": cliente_id},
    )
    db.execute(
        text(
            """INSERT INTO cliente_metodo_pago (cliente_id, tipo, origen, estado, setup_token)
               VALUES (:c, 'paypal', 'manual', 'pendiente', :s)"""
        ),
        {"c": cliente_id, "s": setup["id"]},
    )
    db.commit()
    return VincularOut(approve_url=approve)


@router.post("/paypal/confirmar", response_model=list[MetodoPagoClienteOut])
def confirmar_paypal(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> list[MetodoPagoClienteOut]:
    """Despues de aprobar en PayPal: se crea y guarda (cifrado) el token de
    cobro. Si esa cuenta ya estaba registrada (se pago con ella), se autoriza
    esa misma; si no, se agrega."""
    cliente_id = _cliente(usuario)
    pendiente = db.execute(
        text(
            """SELECT id, setup_token FROM cliente_metodo_pago
               WHERE cliente_id = :c AND estado = 'pendiente' AND cuenta IS NULL ORDER BY id DESC LIMIT 1"""
        ),
        {"c": cliente_id},
    ).first()
    if pendiente is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Primero inicia la autorización con PayPal.")
    token = crear_payment_token(pendiente.setup_token)
    paypal = (token.get("payment_source") or {}).get("paypal") or {}
    correo = paypal.get("email_address")
    payer_id = paypal.get("payer_id")
    existente = None
    if correo:
        existente = db.execute(
            text(
                """SELECT id, token_cifrado FROM cliente_metodo_pago
                   WHERE cliente_id = :c AND tipo = 'paypal' AND lower(cuenta) = lower(:m)"""
            ),
            {"c": cliente_id, "m": correo},
        ).first()
    anterior = None
    if existente is not None:
        anterior = descifrar(existente.token_cifrado) if existente.token_cifrado else None
        db.execute(
            text(
                """UPDATE cliente_metodo_pago SET estado = 'autorizada', token_cifrado = :t,
                          paypal_payer_id = coalesce(:p, paypal_payer_id), actualizado_en = now()
                   WHERE id = :i"""
            ),
            {"t": cifrar(token["id"]), "p": payer_id, "i": existente.id},
        )
        db.execute(text("DELETE FROM cliente_metodo_pago WHERE id = :i"), {"i": pendiente.id})
    else:
        db.execute(
            text(
                """UPDATE cliente_metodo_pago SET estado = 'autorizada', token_cifrado = :t, cuenta = :m,
                          paypal_payer_id = :p, setup_token = NULL, actualizado_en = now()
                   WHERE id = :i"""
            ),
            {"t": cifrar(token["id"]), "m": correo, "p": payer_id, "i": pendiente.id},
        )
    db.commit()
    if anterior and anterior != token["id"]:
        borrar_payment_token(anterior)
    log_bitacora(
        db, usuario, "ACTUALIZAR", "cliente", cliente_id,
        f"Autorizó su PayPal {correo or ''} para compras sin conexión".replace("  ", " "), request,
    )
    return _metodos(db, cliente_id)


@router.delete("/metodos/{metodo_id}", response_model=list[MetodoPagoClienteOut])
def quitar_metodo(
    metodo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> list[MetodoPagoClienteOut]:
    cliente_id = _cliente(usuario)
    fila = db.execute(
        text("SELECT cuenta, token_cifrado FROM cliente_metodo_pago WHERE id = :i AND cliente_id = :c"),
        {"i": metodo_id, "c": cliente_id},
    ).first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Método de pago no encontrado.")
    db.execute(text("DELETE FROM cliente_metodo_pago WHERE id = :i"), {"i": metodo_id})
    db.commit()
    if fila.token_cifrado and (token := descifrar(fila.token_cifrado)):
        borrar_payment_token(token)
    log_bitacora(db, usuario, "ACTUALIZAR", "cliente", cliente_id, f"Quitó su PayPal {fila.cuenta or ''} de sus métodos de pago", request)
    return _metodos(db, cliente_id)


# ------------------------------------------------- para otros modulos


def registrar_paypal_usado(db: Session, cliente_id: int, resultado: dict | None) -> None:
    """Despues de un pago con PayPal ya confirmado: la cuenta con la que pago
    queda en sus Metodos de pago (o suma un uso). Nunca hace fallar la venta."""
    try:
        resultado = resultado or {}
        fuente = resultado.get("payment_source") or {"paypal": {}}
        # Pago con tarjeta (por el boton de PayPal): no es una cuenta PayPal.
        if "paypal" not in fuente:
            return
        payer = resultado.get("payer") or {}
        paypal = fuente.get("paypal") or {}
        correo = payer.get("email_address") or paypal.get("email_address")
        if not correo:
            return
        db.execute(
            text(
                """INSERT INTO cliente_metodo_pago (cliente_id, tipo, cuenta, paypal_payer_id, origen, estado,
                                                   veces_usado, ultimo_uso)
                   VALUES (:c, 'paypal', :m, :p, 'automatico', 'registrada', 1, now())
                   ON CONFLICT (cliente_id, tipo, lower(cuenta)) WHERE cuenta IS NOT NULL DO UPDATE
                   SET veces_usado = cliente_metodo_pago.veces_usado + 1, ultimo_uso = now(),
                       paypal_payer_id = coalesce(EXCLUDED.paypal_payer_id, cliente_metodo_pago.paypal_payer_id),
                       actualizado_en = now()"""
            ),
            {"c": cliente_id, "m": correo, "p": payer.get("payer_id") or paypal.get("account_id")},
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("No se pudo registrar el PayPal usado por el cliente %s", cliente_id)


def token_de(db: Session, cliente_id: int, metodo_id: int | None = None) -> tuple[int, str] | None:
    """(id, token de cobro descifrado) de una cuenta PayPal autorizada del
    cliente: la elegida o, sin elegir, la ultima autorizada."""
    sql = "SELECT id, token_cifrado FROM cliente_metodo_pago WHERE cliente_id = :c AND estado = 'autorizada'"
    params: dict = {"c": cliente_id}
    if metodo_id is not None:
        sql += " AND id = :i"
        params["i"] = metodo_id
    fila = db.execute(text(sql + " ORDER BY actualizado_en DESC LIMIT 1"), params).first()
    token = descifrar(fila.token_cifrado) if fila and fila.token_cifrado else None
    return (fila.id, token) if token else None


def marcar_uso(db: Session, metodo_id: int) -> None:
    db.execute(
        text("UPDATE cliente_metodo_pago SET veces_usado = veces_usado + 1, ultimo_uso = now() WHERE id = :i"),
        {"i": metodo_id},
    )


def paypals_de(db: Session, cliente_id: int) -> list[dict]:
    """Sus cuentas PayPal para el catalogo sin conexion (autorizadas primero)."""
    return [
        dict(f)
        for f in db.execute(
            text(
                """SELECT id, cuenta, estado = 'autorizada' AS autorizada FROM cliente_metodo_pago
                   WHERE cliente_id = :c AND tipo = 'paypal' AND NOT (estado = 'pendiente' AND cuenta IS NULL)
                   ORDER BY (estado = 'autorizada') DESC, ultimo_uso DESC NULLS LAST, id"""
            ),
            {"c": cliente_id},
        ).mappings()
    ]
