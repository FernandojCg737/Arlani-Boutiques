from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.deps import require_permiso
from app.core.audit import log_bitacora
from app.db.session import get_db
from app.models import Empresa, Temporada, Usuario
from app.schemas.temporadas import TemporadaCreate, TemporadaOut, TemporadaUpdate

router = APIRouter()


def _get_temporada_or_404(db: Session, temporada_id: int) -> Temporada:
    temporada = db.query(Temporada).filter(Temporada.id == temporada_id).first()
    if temporada is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Temporada no encontrada.")
    return temporada


@router.get("", response_model=list[TemporadaOut])
def list_temporadas(
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_permiso("CU07")),
) -> list[TemporadaOut]:
    return db.query(Temporada).order_by(Temporada.fecha_inicio.desc()).all()


@router.get("/publico", response_model=list[TemporadaOut])
def list_temporadas_publico(
    tienda: str | None = Query(default=None, max_length=40), db: Session = Depends(get_db)
) -> list[TemporadaOut]:
    # tienda=<subdominio>: solo las temporadas de esa boutique (filtros de su catalogo).
    query = db.query(Temporada)
    if tienda:
        query = query.join(Empresa, Empresa.id == Temporada.empresa_id).filter(Empresa.subdominio == tienda.lower())
    return query.order_by(Temporada.fecha_inicio.desc()).all()


@router.post("", response_model=TemporadaOut, status_code=status.HTTP_201_CREATED)
def create_temporada(
    payload: TemporadaCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU07")),
) -> TemporadaOut:
    result = db.execute(
        text("SELECT sp_crear_temporada(:nombre, :fecha_inicio, :fecha_fin)"),
        {"nombre": payload.nombre, "fecha_inicio": payload.fecha_inicio, "fecha_fin": payload.fecha_fin},
    )
    temporada_id = result.scalar_one()
    db.commit()

    temporada = _get_temporada_or_404(db, temporada_id)
    log_bitacora(db, admin, "CREAR", "temporada", temporada.id, f"Alta de temporada: {temporada.nombre}", request)
    return temporada


@router.put("/{temporada_id}", response_model=TemporadaOut)
def update_temporada(
    temporada_id: int,
    payload: TemporadaUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU07")),
) -> TemporadaOut:
    _get_temporada_or_404(db, temporada_id)

    db.execute(
        text("SELECT sp_actualizar_temporada(:id, :nombre, :fecha_inicio, :fecha_fin)"),
        {
            "id": temporada_id,
            "nombre": payload.nombre,
            "fecha_inicio": payload.fecha_inicio,
            "fecha_fin": payload.fecha_fin,
        },
    )
    db.commit()

    temporada = _get_temporada_or_404(db, temporada_id)
    log_bitacora(db, admin, "ACTUALIZAR", "temporada", temporada.id, f"Edicion de temporada: {temporada.nombre}", request)
    return temporada


@router.delete("/{temporada_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_temporada(
    temporada_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU07")),
) -> None:
    temporada = _get_temporada_or_404(db, temporada_id)
    nombre = temporada.nombre

    try:
        db.execute(text("SELECT sp_eliminar_temporada(:id)"), {"id": temporada_id})
        db.commit()
    except DBAPIError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No se puede eliminar: la temporada tiene colecciones o productos asociados.",
        )

    log_bitacora(db, admin, "ELIMINAR", "temporada", temporada_id, f"Baja de temporada: {nombre}", request)
