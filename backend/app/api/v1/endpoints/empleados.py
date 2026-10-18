import html
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.api.deps import require_permiso
from app.core.audit import log_bitacora, set_client_ip_for_trigger
from app.core.email import send_email
from app.core.security import generate_temp_password, hash_password
from app.db.session import get_db
from app.models import Empleado, Usuario
from app.schemas.empleados import EmpleadoCreate, EmpleadoOut, EmpleadoUpdate

router = APIRouter()
logger = logging.getLogger(__name__)

TIPOS_VALIDOS = {"administrador", "encargado_sucursal", "cajero"}
TIPOS_CON_SUCURSAL = {"encargado_sucursal", "cajero"}


def _to_out(empleado: Empleado) -> EmpleadoOut:
    return EmpleadoOut(
        id=empleado.id,
        nombre=empleado.nombre,
        email=empleado.email,
        tipo=empleado.tipo,
        estado=empleado.estado,
        fecha_registro=empleado.fecha_registro,
        metodo_registro=empleado.metodo_registro,
        sucursal_id=empleado.sucursal_id,
        sucursal_nombre=empleado.sucursal.nombre if empleado.sucursal else None,
        rol_id=empleado.rol_id,
        rol_nombre=empleado.rol.nombre if empleado.rol else None,
    )


def _get_empleado_or_404(db: Session, empleado_id: int) -> Empleado:
    empleado = (
        db.query(Empleado)
        .options(joinedload(Empleado.sucursal), joinedload(Empleado.rol))
        .filter(Empleado.id == empleado_id)
        .first()
    )
    if empleado is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empleado no encontrado.")
    return empleado


@router.get("", response_model=list[EmpleadoOut])
def list_empleados(
    tipo: str = Query(...),
    buscar: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_permiso("CU02")),
) -> list[EmpleadoOut]:
    if tipo not in TIPOS_VALIDOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo de empleado invalido.")

    query = (
        db.query(Empleado)
        .options(joinedload(Empleado.sucursal), joinedload(Empleado.rol))
        .filter(Empleado.tipo == tipo)
    )
    if buscar:
        like = f"%{buscar}%"
        query = query.filter(Empleado.nombre.ilike(like) | Empleado.email.ilike(like))

    return [_to_out(e) for e in query.order_by(Empleado.nombre).all()]


@router.post("", response_model=EmpleadoOut, status_code=status.HTTP_201_CREATED)
def create_empleado(
    payload: EmpleadoCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU02")),
) -> EmpleadoOut:
    # El Administrador es superusuario por tipo (ver deps.require_permiso):
    # si un no-admin con CU02 pudiera crear administradores, CU02 equivaldria
    # a poder convertirse en Administrador.
    if payload.tipo == "administrador" and admin.tipo != "administrador":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el Administrador puede crear otros administradores.")

    existing = db.query(Usuario).filter(Usuario.email == payload.email).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese correo.")

    if payload.tipo in TIPOS_CON_SUCURSAL and payload.sucursal_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selecciona una sucursal para este cargo.")

    password_temporal = generate_temp_password()

    set_client_ip_for_trigger(db, request)
    result = db.execute(
        text(
            "SELECT sp_crear_empleado(:nombre, :email, :password_hash, :tipo, :sucursal_id, "
            ":rol_id, :metodo_registro)"
        ),
        {
            "nombre": payload.nombre,
            "email": payload.email,
            "password_hash": hash_password(password_temporal),
            "tipo": payload.tipo,
            "sucursal_id": payload.sucursal_id,
            "rol_id": payload.rol_id,
            "metodo_registro": "admin",
        },
    )
    empleado_id = result.scalar_one()
    db.commit()

    empleado = _get_empleado_or_404(db, empleado_id)

    try:
        send_email(
            to=empleado.email,
            subject="Bienvenido al equipo - Atelier Aranier",
            html_body=(
                f"<p>Hola {html.escape(empleado.nombre)},</p>"
                f"<p>Se creo tu cuenta de <strong>{empleado.tipo.replace('_', ' ')}</strong> en el panel de "
                "administracion de Atelier Aranier.</p>"
                "<p>Estos son tus datos de acceso:</p>"
                f"<p>Correo: {html.escape(empleado.email)}<br>Contrasena temporal: {password_temporal}</p>"
                "<p>Te recomendamos cambiar la contrasena desde tu perfil apenas inicies sesion.</p>"
            ),
        )
    except Exception:
        logger.exception("No se pudo enviar el correo de bienvenida a %s", empleado.email)

    log_bitacora(db, admin, "CREAR", "usuario", empleado.id, f"Alta de {empleado.tipo}: {empleado.email}", request)
    return _to_out(empleado)


@router.put("/{empleado_id}", response_model=EmpleadoOut)
def update_empleado(
    empleado_id: int,
    payload: EmpleadoUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU02")),
) -> EmpleadoOut:
    empleado = _get_empleado_or_404(db, empleado_id)

    if admin.tipo != "administrador":
        if empleado.tipo == "administrador":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el Administrador puede editar a otro administrador.")
        if empleado.id == admin.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes cambiar tu propio rol ni tu estado.")

    if empleado.tipo in TIPOS_CON_SUCURSAL and payload.sucursal_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selecciona una sucursal para este cargo.")

    db.execute(
        text("SELECT sp_actualizar_empleado(:id, :nombre, :sucursal_id, :rol_id, :estado)"),
        {
            "id": empleado_id,
            "nombre": payload.nombre,
            "sucursal_id": payload.sucursal_id,
            "rol_id": payload.rol_id,
            "estado": payload.estado,
        },
    )
    db.commit()

    empleado = _get_empleado_or_404(db, empleado_id)
    log_bitacora(
        db, admin, "ACTUALIZAR", "usuario", empleado.id, f"Edicion de {empleado.tipo}: {empleado.email}", request
    )
    return _to_out(empleado)
