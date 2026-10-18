from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.api.deps import require_permiso
from app.core.audit import log_bitacora
from app.db.session import get_db
from app.models import Permiso, Rol, Usuario
from app.schemas.roles import ActualizarPermisosRequest, PermisoOut, RolOut

router = APIRouter()


def _rol_to_out(rol: Rol) -> RolOut:
    return RolOut(id=rol.id, nombre=rol.nombre, descripcion=rol.descripcion, permisos=[p.nombre for p in rol.permisos])


@router.get("/permisos", response_model=list[PermisoOut])
def list_permisos(
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_permiso("CU02")),
) -> list[PermisoOut]:
    return db.query(Permiso).order_by(Permiso.nombre).all()


@router.get("", response_model=list[RolOut])
def list_roles(
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_permiso("CU02")),
) -> list[RolOut]:
    roles = db.query(Rol).options(joinedload(Rol.permisos)).order_by(Rol.nombre).all()
    return [_rol_to_out(r) for r in roles]


@router.put("/{rol_id}/permisos", response_model=RolOut)
def actualizar_permisos_rol(
    rol_id: int,
    payload: ActualizarPermisosRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU02")),
) -> RolOut:
    rol = db.query(Rol).filter(Rol.id == rol_id).first()
    if rol is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rol no encontrado.")

    # Un no-admin con CU02 no puede escalar privilegios: ni editar su propio
    # rol, ni otorgar permisos que el mismo no tiene.
    if admin.tipo != "administrador":
        if admin.rol_id == rol_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes modificar los permisos de tu propio rol.")
        propios = {p.id for p in admin.rol.permisos} if admin.rol else set()
        actuales = {p.id for p in rol.permisos}
        agregados = set(payload.permiso_ids) - actuales
        if not agregados <= propios:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes otorgar permisos que tu rol no tiene.")

    db.execute(
        text("SELECT sp_reemplazar_permisos_rol(:rol_id, :permiso_ids)"),
        {"rol_id": rol_id, "permiso_ids": payload.permiso_ids},
    )
    db.commit()

    rol = db.query(Rol).options(joinedload(Rol.permisos)).filter(Rol.id == rol_id).first()
    log_bitacora(db, admin, "ACTUALIZAR", "rol", rol.id, f"Permisos actualizados para rol: {rol.nombre}", request)
    return _rol_to_out(rol)
