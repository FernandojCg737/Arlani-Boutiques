import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import require_permiso_cliente
from app.core.audit import log_bitacora
from app.core.config import settings
from app.core.email import send_email
from app.core.security import create_access_token, vigencia_sesion, hash_password, verify_password
from app.db.session import get_db
from app.models import Cliente, Usuario
from app.schemas.auth import TokenResponse, UsuarioOut
from app.schemas.perfil import CambiarPasswordRequest, PerfilUpdate
from app.services.usuarios import to_usuario_out

router = APIRouter()
logger = logging.getLogger(__name__)


@router.put("", response_model=UsuarioOut)
def actualizar_perfil(
    payload: PerfilUpdate,
    request: Request,
    usuario: Usuario = Depends(require_permiso_cliente("CU15")),
    db: Session = Depends(get_db),
) -> UsuarioOut:
    if isinstance(usuario, Cliente):
        db.execute(
            text("SELECT sp_actualizar_cliente_perfil(:id, :nombre, :telefono, :direccion)"),
            {"id": usuario.id, "nombre": payload.nombre, "telefono": payload.telefono, "direccion": payload.direccion},
        )
    else:
        db.execute(
            text("SELECT sp_actualizar_usuario_nombre(:id, :nombre)"),
            {"id": usuario.id, "nombre": payload.nombre},
        )
    db.commit()

    usuario = db.query(Usuario).filter(Usuario.id == usuario.id).first()
    log_bitacora(db, usuario, "ACTUALIZAR", "usuario", usuario.id, f"Edicion de perfil: {usuario.email}", request)
    return to_usuario_out(usuario)


@router.post("/cambiar-password", response_model=TokenResponse)
def cambiar_password(
    payload: CambiarPasswordRequest,
    request: Request,
    usuario: Usuario = Depends(require_permiso_cliente("CU15")),
    db: Session = Depends(get_db),
) -> TokenResponse:
    if not verify_password(payload.password_actual, usuario.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "La contrasena actual no es correcta.")

    # Nueva sesion: si la contrasena vieja quedo comprometida, cualquier otra
    # sesion abierta con el token anterior deja de servir.
    nuevo_session_id = uuid.uuid4().hex
    db.execute(
        text("SELECT sp_cambiar_password(:id, :password_hash, :session_id)"),
        {
            "id": usuario.id,
            "password_hash": hash_password(payload.password_nueva),
            "session_id": nuevo_session_id,
        },
    )
    db.commit()

    usuario = db.query(Usuario).filter(Usuario.id == usuario.id).first()
    usuario.sesion_expira_en = datetime.utcnow() + timedelta(minutes=vigencia_sesion(usuario.tipo))
    db.commit()
    db.refresh(usuario)
    log_bitacora(db, usuario, "ACTUALIZAR", "usuario", usuario.id, f"Cambio de contrasena: {usuario.email}", request)

    try:
        send_email(
            to=usuario.email,
            subject="Tu contrasena fue actualizada - Arlani Boutiques",
            html_body=(
                f"<p>Hola {usuario.nombre},</p>"
                "<p>Tu contrasena se actualizo correctamente.</p>"
                "<p>Si no fuiste tu, contactanos de inmediato para proteger tu cuenta.</p>"
            ),
        )
    except Exception:
        logger.exception("No se pudo enviar el aviso de cambio de contrasena a %s", usuario.email)

    token = create_access_token(
        subject=str(usuario.id), session_id=usuario.session_id, minutes=vigencia_sesion(usuario.tipo)
    )
    return TokenResponse(access_token=token, usuario=to_usuario_out(usuario))
