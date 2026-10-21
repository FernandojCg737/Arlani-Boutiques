from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permiso
from app.db.session import get_db
from app.models import Empresa, Usuario
from app.schemas.sesiones import SesionActivaOut

router = APIRouter()

# Personal de tienda cuyas sesiones se ven dentro de la empresa: su(s)
# Administrador(es), Encargados de Sucursal y Cajeros.
PERSONAL_VISIBLE = ("administrador", "encargado_sucursal", "cajero")


@router.get("/activas", response_model=list[SesionActivaOut])
def sesiones_activas(
    empresa_id: int | None = Query(default=None),
    plataforma: bool = Query(default=False),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU01")),
) -> list[SesionActivaOut]:
    """Quien tiene una sesion abierta ahora mismo.

    - SuperAdministrador: todo el sistema. Puede filtrar por empresa
      (empresa_id) o ver solo las cuentas de la plataforma (plataforma=true:
      clientes y el propio SuperAdministrador).
    - Personal de una tienda: el personal de SU empresa (Administrador,
      Encargados de Sucursal y Cajeros); nunca clientes ni gente de otras
      empresas.
    """
    # "Activa" = tiene session_id Y todavia no paso su expiracion (60 min
    # desde el login). Antes solo se filtraba por session_id no nulo, que
    # nunca se limpiaba si el usuario cerraba la pestana sin desloguearse.
    query = db.query(Usuario).filter(
        Usuario.session_id.isnot(None),
        Usuario.sesion_expira_en.isnot(None),
        Usuario.sesion_expira_en > datetime.utcnow(),
    )

    if usuario.tipo == "superadministrador":
        if empresa_id is not None:
            query = query.filter(Usuario.empresa_id == empresa_id)
        elif plataforma:
            query = query.filter(Usuario.empresa_id.is_(None))
    else:
        query = query.filter(Usuario.empresa_id == usuario.empresa_id, Usuario.tipo.in_(PERSONAL_VISIBLE))

    usuarios = query.order_by(Usuario.nombre).all()
    empresas = {e.id: e.nombre for e in db.query(Empresa.id, Empresa.nombre).all()}
    return [
        SesionActivaOut(
            id=u.id,
            nombre=u.nombre,
            email=u.email,
            tipo=u.tipo,
            rol=u.rol.nombre if u.rol else None,
            empresa_id=u.empresa_id,
            empresa_nombre=empresas.get(u.empresa_id) if u.empresa_id else None,
            sucursal_nombre=u.sucursal.nombre if getattr(u, "sucursal", None) else None,
            expira_en=u.sesion_expira_en.replace(tzinfo=timezone.utc),
        )
        for u in usuarios
    ]
