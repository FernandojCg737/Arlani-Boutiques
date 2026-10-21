import html
import logging
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import client_ip, log_bitacora, set_client_ip_for_trigger
from app.core.config import settings
from app.core.email import send_email
from app.core.rate_limit import verificar_limite
from app.core.security import create_access_token, create_reset_token, hash_password, verify_password
from app.db.session import get_db
from app.models import Cliente, Usuario
from app.schemas.auth import (
    ClienteLogin,
    ClienteRegister,
    ForgotPasswordRequest,
    GoogleAuthPayload,
    LoginWithResetTokenRequest,
    MessageResponse,
    ResetPasswordRequest,
    ResetTokenResponse,
    TokenResponse,
    UsuarioOut,
    VerifyResetCodeRequest,
)
from app.services.usuarios import to_usuario_out

router = APIRouter()
logger = logging.getLogger(__name__)

# Codigo de recuperacion de 6 digitos: tras MAX_INTENTOS_CODIGO fallos se
# invalida y hay que pedir uno nuevo.
MAX_INTENTOS_CODIGO = 5

# Respuesta identica exista o no la cuenta: si "no existe" devolviera otra
# cosa, cualquiera podria averiguar que correos estan registrados.
_MENSAJE_CODIGO_ENVIADO = "Si el correo esta registrado, te enviamos un codigo de verificacion."


def _limitar_por_ip(request: Request, alcance: str, maximo: int, segundos: int) -> None:
    verificar_limite(alcance, client_ip(request) or "desconocida", maximo, segundos)


def _log_sesion_bitacora(db: Session, usuario: Usuario, accion: str, request: Request) -> None:
    detalle_por_accion = {
        "LOGIN": f"Inicio de sesion ({usuario.tipo}): {usuario.email}",
        "LOGOUT": f"Cierre de sesion ({usuario.tipo}): {usuario.email}",
    }
    log_bitacora(db, usuario, accion, "usuario", usuario.id, detalle_por_accion.get(accion), request)


def _issue_token(usuario: Usuario, db: Session, request: Request) -> TokenResponse:
    # Cada login/registro reemplaza el session_id guardado en la BD: si el
    # usuario tenia una sesion abierta en otro dispositivo, su token anterior
    # deja de matchear "sid" y get_current_user lo rechaza en su proximo request.
    usuario.session_id = uuid.uuid4().hex
    usuario.sesion_expira_en = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    db.commit()
    db.refresh(usuario)

    _log_sesion_bitacora(db, usuario, "LOGIN", request)

    token = create_access_token(subject=str(usuario.id), session_id=usuario.session_id)
    return TokenResponse(access_token=token, usuario=to_usuario_out(usuario))


def _usuario_from_reset_token(reset_token: str, db: Session) -> Usuario:
    """Valida el reset_token y lo CONSUME (un solo uso): despues de esto el
    mismo token ya no sirve ni para reset-password ni para
    login-with-reset-code."""
    invalido = HTTPException(status.HTTP_400_BAD_REQUEST, "Token de recuperacion invalido o expirado.")
    try:
        payload = jwt.decode(reset_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise invalido

    if payload.get("scope") != "password_reset" or not payload.get("jti"):
        raise invalido

    usuario = db.query(Usuario).filter(Usuario.id == int(payload.get("sub", 0))).first()
    if usuario is None or not usuario.reset_token_jti or usuario.reset_token_jti != payload["jti"]:
        raise invalido
    if usuario.estado != "activo":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta cuenta esta desactivada.")

    usuario.reset_token_jti = None
    return usuario


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: ClienteRegister, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    _limitar_por_ip(request, "register", maximo=10, segundos=3600)

    existing = db.query(Usuario).filter(Usuario.email == payload.email).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese correo.")

    set_client_ip_for_trigger(db, request)
    result = db.execute(
        text(
            "SELECT sp_crear_cliente(:nombre, :email, :password_hash, :telefono, :direccion, :metodo_registro)"
        ),
        {
            "nombre": payload.nombre,
            "email": payload.email,
            "password_hash": hash_password(payload.password),
            "telefono": payload.telefono,
            "direccion": None,
            "metodo_registro": "email",
        },
    )
    cliente_id = result.scalar_one()
    db.commit()

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()

    # Nunca se manda la contrasena por correo: el cliente la acaba de elegir
    # y el correo viaja/queda guardado en texto plano.
    try:
        send_email(
            to=cliente.email,
            subject="Bienvenido a Arlani Boutiques",
            html_body=(
                f"<p>Hola {html.escape(cliente.nombre)},</p>"
                "<p>Gracias por registrarte en <strong>Arlani Boutiques</strong>. "
                "Con tu cuenta puedes comprar y reservar en todas nuestras boutiques.</p>"
                f"<p>Tu cuenta quedo registrada con el correo {html.escape(cliente.email)}.</p>"
                "<p>Ya puedes iniciar sesion cuando quieras.</p>"
            ),
        )
    except Exception:
        logger.exception("No se pudo enviar el correo de bienvenida a %s", cliente.email)

    return _issue_token(cliente, db, request)


@router.post("/google", response_model=TokenResponse)
def google_auth(payload: GoogleAuthPayload, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    _limitar_por_ip(request, "google", maximo=30, segundos=300)

    try:
        # 10 s de tolerancia: si el reloj del servidor (Docker, Render) va un
        # poco atrasado, Google rechaza el token como "usado antes de tiempo".
        idinfo = google_id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=10,
        )
    except ValueError as err:
        # El motivo real (audiencia equivocada, expirado, ...) queda en el log
        # del backend; al usuario le basta el mensaje general.
        logger.warning("Google rechazo el id_token: %s", err)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de Google invalido.")

    email = idinfo.get("email")
    if not email or not idinfo.get("email_verified"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No se pudo verificar el correo de Google.")

    cliente = db.query(Cliente).filter(Cliente.email == email).first()
    if cliente is None:
        existing_usuario = db.query(Usuario).filter(Usuario.email == email).first()
        if existing_usuario is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese correo.")

        set_client_ip_for_trigger(db, request)
        result = db.execute(
            text(
                "SELECT sp_crear_cliente(:nombre, :email, :password_hash, :telefono, :direccion, :metodo_registro)"
            ),
            {
                "nombre": idinfo.get("name") or email.split("@")[0],
                "email": email,
                "password_hash": hash_password(secrets.token_urlsafe(32)),
                "telefono": None,
                "direccion": None,
                "metodo_registro": "google",
            },
        )
        cliente_id = result.scalar_one()
        db.commit()

        cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()

        try:
            send_email(
                to=cliente.email,
                subject="Bienvenido a Arlani Boutiques",
                html_body=(
                    f"<p>Hola {html.escape(cliente.nombre)},</p>"
                    "<p>Gracias por registrarte en <strong>Arlani Boutiques</strong> con tu cuenta de Google. "
                    "Con tu cuenta puedes comprar y reservar en todas nuestras boutiques.</p>"
                    f"<p>Iniciaste sesion con tu cuenta de Google ({html.escape(cliente.email)}), "
                    "asi que puedes volver a entrar en cualquier momento con el boton "
                    "\"Continuar con Google\".</p>"
                ),
            )
        except Exception:
            logger.exception("No se pudo enviar el correo de bienvenida a %s", cliente.email)

    if cliente.estado != "activo":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta cuenta esta desactivada.")

    return _issue_token(cliente, db, request)


@router.post("/login", response_model=TokenResponse)
def login(payload: ClienteLogin, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    # Por cuenta (frena fuerza bruta contra un correo concreto aunque el
    # atacante rote IPs) y por IP (frena barridos de muchos correos).
    verificar_limite("login-email", payload.email, maximo=10, segundos=900)
    _limitar_por_ip(request, "login-ip", maximo=30, segundos=300)

    usuario = db.query(Usuario).filter(Usuario.email == payload.email).first()
    if not usuario or not verify_password(payload.password, usuario.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contrasena incorrectos.")

    if usuario.estado != "activo":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta cuenta esta desactivada.")

    return _issue_token(usuario, db, request)


@router.get("/me", response_model=UsuarioOut)
def me(usuario: Usuario = Depends(get_current_user)) -> UsuarioOut:
    return to_usuario_out(usuario)


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    usuario: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    usuario.session_id = None
    usuario.sesion_expira_en = None
    db.commit()
    _log_sesion_bitacora(db, usuario, "LOGOUT", request)
    return MessageResponse(message="Sesion cerrada.")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    verificar_limite("forgot-email", payload.email, maximo=3, segundos=900)
    _limitar_por_ip(request, "forgot-ip", maximo=10, segundos=900)

    usuario = db.query(Usuario).filter(Usuario.email == payload.email).first()
    if usuario is None or usuario.estado != "activo":
        return MessageResponse(message=_MENSAJE_CODIGO_ENVIADO)

    code = f"{secrets.randbelow(1_000_000):06d}"
    usuario.reset_code_hash = hash_password(code)
    usuario.reset_code_expires_at = datetime.utcnow() + timedelta(minutes=10)
    usuario.reset_code_intentos = 0
    usuario.reset_token_jti = None
    db.commit()

    try:
        send_email(
            to=usuario.email,
            subject="Codigo de verificacion - Arlani Boutiques",
            html_body=(
                f"<p>Hola {html.escape(usuario.nombre)},</p>"
                "<p>Tu codigo de verificacion para recuperar tu contrasena es:</p>"
                f"<h2>{code}</h2>"
                "<p>Vence en 10 minutos. Si no lo pediste tu, ignora este correo.</p>"
            ),
        )
    except Exception:
        logger.exception("No se pudo enviar el codigo de recuperacion a %s", usuario.email)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "No pudimos enviar el correo en este momento. Intenta de nuevo."
        )
    return MessageResponse(message=_MENSAJE_CODIGO_ENVIADO)


@router.post("/verify-reset-code", response_model=ResetTokenResponse)
def verify_reset_code(
    payload: VerifyResetCodeRequest, request: Request, db: Session = Depends(get_db)
) -> ResetTokenResponse:
    _limitar_por_ip(request, "verify-code-ip", maximo=20, segundos=900)

    invalido = HTTPException(status.HTTP_400_BAD_REQUEST, "Codigo invalido o expirado.")
    usuario = db.query(Usuario).filter(Usuario.email == payload.email).first()
    if (
        usuario is None
        or usuario.reset_code_hash is None
        or usuario.reset_code_expires_at is None
        or usuario.reset_code_expires_at < datetime.utcnow()
    ):
        raise invalido

    if not verify_password(payload.code, usuario.reset_code_hash):
        usuario.reset_code_intentos = (usuario.reset_code_intentos or 0) + 1
        if usuario.reset_code_intentos >= MAX_INTENTOS_CODIGO:
            usuario.reset_code_hash = None
            usuario.reset_code_expires_at = None
            db.commit()
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Demasiados intentos fallidos. Solicita un codigo nuevo."
            )
        db.commit()
        raise invalido

    # codigo de un solo uso; el reset_token que se emite tambien (via jti)
    jti = uuid.uuid4().hex
    usuario.reset_code_hash = None
    usuario.reset_code_expires_at = None
    usuario.reset_code_intentos = 0
    usuario.reset_token_jti = jti
    db.commit()

    return ResetTokenResponse(reset_token=create_reset_token(subject=str(usuario.id), jti=jti))


@router.post("/reset-password", response_model=TokenResponse)
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    usuario = _usuario_from_reset_token(payload.reset_token, db)
    usuario.password_hash = hash_password(payload.new_password)
    db.commit()
    return _issue_token(usuario, db, request)


@router.post("/login-with-reset-code", response_model=TokenResponse)
def login_with_reset_code(
    payload: LoginWithResetTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    usuario = _usuario_from_reset_token(payload.reset_token, db)
    db.commit()
    return _issue_token(usuario, db, request)
