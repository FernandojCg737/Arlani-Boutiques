import html
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import require_permiso
from app.core.audit import log_bitacora, set_client_ip_for_trigger
from app.core.email import nombre_marca, send_email
from app.core.security import generate_temp_password, hash_password
from app.db.session import get_db
from app.models import Proveedor, Usuario
from app.schemas.proveedores import ProveedorCreate, ProveedorOut, ProveedorUpdate

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_proveedor_or_404(db: Session, proveedor_id: int) -> Proveedor:
    proveedor = db.query(Proveedor).filter(Proveedor.id == proveedor_id).first()
    if proveedor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proveedor no encontrado.")
    return proveedor


@router.get("", response_model=list[ProveedorOut])
def list_proveedores(
    buscar: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_permiso("CU06")),
) -> list[ProveedorOut]:
    query = db.query(Proveedor)
    if buscar:
        like = f"%{buscar}%"
        query = query.filter(Proveedor.nombre.ilike(like) | Proveedor.email.ilike(like) | Proveedor.nit.ilike(like))
    return query.order_by(Proveedor.nombre).all()


@router.post("", response_model=ProveedorOut, status_code=status.HTTP_201_CREATED)
def create_proveedor(
    payload: ProveedorCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU06")),
) -> ProveedorOut:
    existing = db.query(Usuario).filter(Usuario.email == payload.email).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese correo.")

    existing_nit = db.query(Proveedor).filter(Proveedor.nit == payload.nit).first()
    if existing_nit:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un proveedor con ese NIT.")

    password_temporal = generate_temp_password()

    set_client_ip_for_trigger(db, request)
    result = db.execute(
        text(
            "SELECT sp_crear_proveedor(:nombre, :email, :password_hash, :nit, :contacto_nombre, "
            ":telefono, :direccion, :metodo_registro)"
        ),
        {
            "nombre": payload.nombre,
            "email": payload.email,
            "password_hash": hash_password(password_temporal),
            "nit": payload.nit,
            "contacto_nombre": payload.contacto_nombre,
            "telefono": payload.telefono,
            "direccion": payload.direccion,
            "metodo_registro": "admin",
        },
    )
    proveedor_id = result.scalar_one()
    db.commit()

    proveedor = _get_proveedor_or_404(db, proveedor_id)
    # El proveedor trabaja con la tienda de quien lo registra.
    marca = nombre_marca(db, admin.empresa_id)

    try:
        send_email(
            to=proveedor.email,
            subject=f"Alta de proveedor - {marca}",
            html_body=(
                f"<p>Hola {proveedor.nombre},</p>"
                "<p>Se registro tu cuenta de <strong>proveedor</strong> en el panel de administracion de "
                f"{html.escape(marca)}.</p>"
                "<p>Estos son tus datos de acceso:</p>"
                f"<p>Correo: {proveedor.email}<br>Contrasena temporal: {password_temporal}</p>"
            ),
        )
    except Exception:
        logger.exception("No se pudo enviar el correo de bienvenida a %s", proveedor.email)

    log_bitacora(db, admin, "CREAR", "usuario", proveedor.id, f"Alta de proveedor: {proveedor.email}", request)
    return proveedor


@router.put("/{proveedor_id}", response_model=ProveedorOut)
def update_proveedor(
    proveedor_id: int,
    payload: ProveedorUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU06")),
) -> ProveedorOut:
    _get_proveedor_or_404(db, proveedor_id)

    existing_nit = (
        db.query(Proveedor).filter(Proveedor.nit == payload.nit, Proveedor.id != proveedor_id).first()
    )
    if existing_nit:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un proveedor con ese NIT.")

    db.execute(
        text(
            "SELECT sp_actualizar_proveedor(:id, :nombre, :nit, :contacto_nombre, :telefono, :direccion, :estado)"
        ),
        {
            "id": proveedor_id,
            "nombre": payload.nombre,
            "nit": payload.nit,
            "contacto_nombre": payload.contacto_nombre,
            "telefono": payload.telefono,
            "direccion": payload.direccion,
            "estado": payload.estado,
        },
    )
    db.commit()

    proveedor = _get_proveedor_or_404(db, proveedor_id)
    log_bitacora(db, admin, "ACTUALIZAR", "usuario", proveedor.id, f"Edicion de proveedor: {proveedor.email}", request)
    return proveedor
