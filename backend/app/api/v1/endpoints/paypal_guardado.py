"""PayPal guardado del cliente (compras sin conexion que se cobran solas).

El cliente vincula su PayPal una vez, con conexion: PayPal le muestra la
autorizacion y Arlani recibe un token de cobro (PayPal Vault). Desde entonces,
lo que compre sin conexion con "Pagar con mi PayPal guardado" se cobra solo al
sincronizar (ver offline.py: _cobrar_pendientes). Solo se guarda el token
cifrado; nunca datos de la cuenta del cliente.
"""

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

router = APIRouter()


class VincularIn(BaseModel):
    # A donde vuelve PayPal: la web (perfil) o la pagina del backend que
    # cierra el WebView de la app movil.
    retorno: str = Field(max_length=500)
    cancelado: str = Field(max_length=500)


class PaypalGuardadoOut(BaseModel):
    vinculado: bool
    correo: str | None = None
    desde: str | None = None


class VincularOut(BaseModel):
    approve_url: str


def _cliente(usuario: Usuario) -> int:
    if usuario.tipo != "cliente":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo los clientes guardan su PayPal para comprar sin conexión.")
    return usuario.id


def _url_permitida(url: str, request: Request) -> bool:
    """Solo se vuelve a la web de Arlani o al propio backend (no a otro sitio)."""
    destino = urlparse(url)
    if destino.scheme not in ("http", "https") or not destino.netloc:
        return False
    propios = {urlparse(o).netloc for o in settings.cors_origins_list} | {urlparse(str(request.base_url)).netloc}
    return destino.netloc in propios


def _estado(db: Session, cliente_id: int) -> PaypalGuardadoOut:
    fila = db.execute(
        text("SELECT correo, actualizado_en FROM cliente_paypal_guardado WHERE cliente_id = :c AND estado = 'activo'"),
        {"c": cliente_id},
    ).first()
    if fila is None:
        return PaypalGuardadoOut(vinculado=False)
    return PaypalGuardadoOut(vinculado=True, correo=fila.correo, desde=fila.actualizado_en.isoformat() + "Z")


@router.get("/paypal", response_model=PaypalGuardadoOut)
def ver_paypal_guardado(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)) -> PaypalGuardadoOut:
    return _estado(db, _cliente(usuario))


@router.post("/paypal/vincular", response_model=VincularOut)
def vincular_paypal(
    payload: VincularIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> VincularOut:
    """Abre la autorizacion de PayPal; al aprobar, el cliente vuelve a `retorno`
    y la app llama a /paypal/confirmar."""
    cliente_id = _cliente(usuario)
    if not (_url_permitida(payload.retorno, request) and _url_permitida(payload.cancelado, request)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dirección de retorno no permitida.")
    setup = crear_setup_token(payload.retorno, payload.cancelado)
    approve = next((l["href"] for l in setup.get("links", []) if l.get("rel") == "approve"), None)
    if not approve:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "PayPal no devolvió el enlace para vincular la cuenta.")
    db.execute(
        text(
            """INSERT INTO cliente_paypal_guardado (cliente_id, estado, setup_token)
               VALUES (:c, 'pendiente', :s)
               ON CONFLICT (cliente_id) DO UPDATE SET setup_token = :s, actualizado_en = now(),
                   estado = CASE WHEN cliente_paypal_guardado.estado = 'activo' THEN 'activo' ELSE 'pendiente' END"""
        ),
        {"c": cliente_id, "s": setup["id"]},
    )
    db.commit()
    return VincularOut(approve_url=approve)


@router.post("/paypal/confirmar", response_model=PaypalGuardadoOut)
def confirmar_paypal(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> PaypalGuardadoOut:
    """Despues de aprobar en PayPal: se crea y guarda (cifrado) el token de cobro."""
    cliente_id = _cliente(usuario)
    fila = db.execute(
        text("SELECT setup_token, token_cifrado FROM cliente_paypal_guardado WHERE cliente_id = :c"), {"c": cliente_id}
    ).first()
    if fila is None or not fila.setup_token:
        raise HTTPException(status.HTTP_409_CONFLICT, "Primero inicia la vinculación con PayPal.")
    token = crear_payment_token(fila.setup_token)
    correo = ((token.get("payment_source") or {}).get("paypal") or {}).get("email_address")
    # Si ya tenia otro PayPal vinculado, el anterior se desvincula.
    anterior = descifrar(fila.token_cifrado) if fila.token_cifrado else None
    db.execute(
        text(
            """UPDATE cliente_paypal_guardado
               SET estado = 'activo', token_cifrado = :t, correo = :m, setup_token = NULL, actualizado_en = now()
               WHERE cliente_id = :c"""
        ),
        {"t": cifrar(token["id"]), "m": correo, "c": cliente_id},
    )
    db.commit()
    if anterior and anterior != token["id"]:
        borrar_payment_token(anterior)
    log_bitacora(db, usuario, "ACTUALIZAR", "cliente", cliente_id, "Vinculó su PayPal para compras sin conexión", request)
    return _estado(db, cliente_id)


@router.delete("/paypal", response_model=PaypalGuardadoOut)
def desvincular_paypal(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> PaypalGuardadoOut:
    cliente_id = _cliente(usuario)
    fila = db.execute(
        text("SELECT token_cifrado FROM cliente_paypal_guardado WHERE cliente_id = :c"), {"c": cliente_id}
    ).first()
    db.execute(text("DELETE FROM cliente_paypal_guardado WHERE cliente_id = :c"), {"c": cliente_id})
    db.commit()
    if fila and fila.token_cifrado and (token := descifrar(fila.token_cifrado)):
        borrar_payment_token(token)
    log_bitacora(db, usuario, "ACTUALIZAR", "cliente", cliente_id, "Desvinculó su PayPal de compras sin conexión", request)
    return PaypalGuardadoOut(vinculado=False)


def token_activo(db: Session, cliente_id: int) -> str | None:
    """Token de cobro del cliente (descifrado) o None si no vinculo su PayPal."""
    cifrado = db.execute(
        text("SELECT token_cifrado FROM cliente_paypal_guardado WHERE cliente_id = :c AND estado = 'activo'"),
        {"c": cliente_id},
    ).scalar()
    return descifrar(cifrado) if cifrado else None
