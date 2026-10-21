from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, joinedload

from app.api.deps import ADMIN_TIPOS, require_permiso
from app.core.audit import log_bitacora
from app.core.errores_db import http_desde_pg
from app.db.session import get_db
from app.models import Empresa, Permiso, Rol, Usuario
from app.schemas.roles import ActualizarPermisosRequest, PermisoOut, RolOut
from app.services.usuarios import codigos_permiso

router = APIRouter()

# Roles del personal de una tienda: tienen matriz de permisos por empresa.
# Cliente (de toda la plataforma) y SuperAdministrador usan la matriz global.
ROLES_TIENDA = {"Administrador", "Encargado de Sucursal", "Cajero"}


def _empresa_objetivo(usuario: Usuario, empresa_id: int | None) -> int | None:
    """Empresa sobre la que se leen/editan permisos. El personal de una tienda
    solo puede tocar la suya; el SuperAdministrador elige cualquiera."""
    if usuario.empresa_id is not None:
        return usuario.empresa_id
    return empresa_id


def _rol_to_out(db: Session, rol: Rol, empresa_id: int | None) -> RolOut:
    if empresa_id is not None and rol.nombre in ROLES_TIENDA:
        permisos = db.execute(
            text("SELECT fn_permisos_empresa_rol(:e, :r)"), {"e": empresa_id, "r": rol.id}
        ).scalars().all()
    else:
        permisos = [p.nombre for p in rol.permisos]
    return RolOut(id=rol.id, nombre=rol.nombre, descripcion=rol.descripcion, permisos=list(permisos))


@router.get("/permisos", response_model=list[PermisoOut])
def list_permisos(
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_permiso("CU02")),
) -> list[PermisoOut]:
    return db.query(Permiso).order_by(Permiso.nombre).all()


@router.get("", response_model=list[RolOut])
def list_roles(
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU02")),
) -> list[RolOut]:
    empresa = _empresa_objetivo(usuario, empresa_id)
    roles = db.query(Rol).options(joinedload(Rol.permisos)).order_by(Rol.nombre).all()
    # El rol SuperAdministrador no se administra desde ninguna tienda.
    roles = [r for r in roles if r.nombre != "SuperAdministrador"]
    return [_rol_to_out(db, r, empresa) for r in roles]


@router.put("/{rol_id}/permisos", response_model=RolOut)
def actualizar_permisos_rol(
    rol_id: int,
    payload: ActualizarPermisosRequest,
    request: Request,
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU02")),
) -> RolOut:
    rol = db.query(Rol).options(joinedload(Rol.permisos)).filter(Rol.id == rol_id).first()
    if rol is None or rol.nombre == "SuperAdministrador":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rol no encontrado.")

    empresa = _empresa_objetivo(admin, empresa_id)
    por_empresa = rol.nombre in ROLES_TIENDA

    if por_empresa and empresa is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elige la empresa cuyos permisos quieres cambiar.")
    if not por_empresa and admin.tipo != "superadministrador":
        # La matriz global (rol Cliente) es de toda la plataforma.
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Los permisos de este rol son de toda la plataforma: los gestiona el SuperAdministrador."
        )

    # Un no-admin con CU02 no puede escalar privilegios: ni editar su propio
    # rol, ni otorgar permisos que el mismo no tiene.
    if admin.tipo not in ADMIN_TIPOS:
        if admin.rol_id == rol_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes modificar los permisos de tu propio rol.")
        propios = codigos_permiso(admin)
        actuales = set(_rol_to_out(db, rol, empresa).permisos)
        pedidos = {p.nombre for p in db.query(Permiso).filter(Permiso.id.in_(payload.permiso_ids)).all()}
        if not (pedidos - actuales) <= propios:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes otorgar permisos que tu rol no tiene.")

    try:
        if por_empresa:
            db.execute(
                text("SELECT sp_reemplazar_permisos_empresa_rol(:e, :r, :ids)"),
                {"e": empresa, "r": rol_id, "ids": payload.permiso_ids},
            )
        else:
            db.execute(
                text("SELECT sp_reemplazar_permisos_rol(:rol_id, :permiso_ids)"),
                {"rol_id": rol_id, "permiso_ids": payload.permiso_ids},
            )
        db.commit()
    except DBAPIError as err:
        db.rollback()
        http = http_desde_pg(err)
        if http is None:
            raise
        raise http from err

    db.expire_all()
    rol = db.query(Rol).options(joinedload(Rol.permisos)).filter(Rol.id == rol_id).first()
    donde = ""
    if por_empresa:
        nombre_empresa = db.query(Empresa.nombre).filter(Empresa.id == empresa).scalar()
        donde = f" en {nombre_empresa}"
    log_bitacora(db, admin, "ACTUALIZAR", "rol", rol.id, f"Permisos actualizados para rol: {rol.nombre}{donde}", request)
    return _rol_to_out(db, rol, empresa)
