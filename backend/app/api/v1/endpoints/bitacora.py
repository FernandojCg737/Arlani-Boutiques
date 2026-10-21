from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permiso
from app.db.session import get_db
from app.models import Bitacora, Empresa, Usuario
from app.schemas.bitacora import BitacoraItem, BitacoraPage

router = APIRouter()


@router.get("", response_model=BitacoraPage)
def list_bitacora(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    buscar: str | None = Query(default=None),
    empresa_id: int | None = Query(default=None),
    plataforma: bool = Query(default=False),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU17")),
) -> BitacoraPage:
    query = db.query(Bitacora).join(Usuario, Usuario.id == Bitacora.usuario_id)

    # Cada tienda ve solo lo que se refiere a ella (su personal, ventas y
    # reservas en sus sucursales, uso del probador...). El SuperAdministrador
    # ve todo y puede filtrar por empresa o por lo que es de la plataforma.
    if usuario.tipo == "superadministrador":
        if empresa_id is not None:
            query = query.filter(Bitacora.empresa_id == empresa_id)
        elif plataforma:
            query = query.filter(Bitacora.empresa_id.is_(None))
    else:
        query = query.filter(Bitacora.empresa_id == usuario.empresa_id)

    if buscar:
        like = f"%{buscar}%"
        query = query.filter(
            Usuario.email.ilike(like) | Usuario.nombre.ilike(like) | Bitacora.entidad_afectada.ilike(like)
        )

    total = query.count()
    empresas = {e.id: e.nombre for e in db.query(Empresa.id, Empresa.nombre).all()}
    rows = (
        query.order_by(Bitacora.fecha.desc(), Bitacora.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [
        BitacoraItem(
            id=b.id,
            usuario_id=b.usuario_id,
            usuario_nombre=b.usuario.nombre,
            usuario_email=b.usuario.email,
            accion=b.accion,
            entidad_afectada=b.entidad_afectada,
            entidad_id=b.entidad_id,
            fecha=b.fecha,
            detalle=b.detalle,
            ip_address=b.ip_address,
            plataforma=b.plataforma,
            empresa_id=b.empresa_id,
            empresa_nombre=empresas.get(b.empresa_id) if b.empresa_id else None,
        )
        for b in rows
    ]
    return BitacoraPage(items=items, total=total, page=page, page_size=page_size)
