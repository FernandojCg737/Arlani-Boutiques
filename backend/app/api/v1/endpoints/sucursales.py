from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, joinedload

from app.api.deps import require_permiso
from app.core.audit import log_bitacora
from app.core.errores_db import http_desde_pg
from app.db.session import get_db
from app.models import Sucursal, Usuario
from app.schemas.sucursales import SucursalCreate, SucursalOut, SucursalPublicaOut, SucursalUpdate

router = APIRouter()


@router.get("/publico", response_model=list[SucursalPublicaOut])
def list_sucursales_publico(db: Session = Depends(get_db)) -> list[SucursalPublicaOut]:
    sucursales = db.query(Sucursal).filter(Sucursal.estado == "activa").order_by(Sucursal.nombre).all()
    return [
        SucursalPublicaOut(id=s.id, nombre=s.nombre, direccion=s.direccion, horario_atencion=s.horario_atencion)
        for s in sucursales
    ]


def _to_out(sucursal: Sucursal) -> SucursalOut:
    return SucursalOut(
        id=sucursal.id,
        nombre=sucursal.nombre,
        ciudad_id=sucursal.ciudad_id,
        ciudad_nombre=sucursal.ciudad.nombre,
        departamento=sucursal.ciudad.departamento,
        direccion=sucursal.direccion,
        horario_atencion=sucursal.horario_atencion,
        telefono=sucursal.telefono,
        estado=sucursal.estado,
        fecha_creacion=sucursal.fecha_creacion,
        latitud=sucursal.latitud,
        longitud=sucursal.longitud,
        empresa_id=sucursal.empresa_id,
    )


def _get_sucursal_or_404(db: Session, sucursal_id: int) -> Sucursal:
    sucursal = (
        db.query(Sucursal)
        .options(joinedload(Sucursal.ciudad))
        .filter(Sucursal.id == sucursal_id)
        .first()
    )
    if sucursal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sucursal no encontrada.")
    return sucursal


@router.get("", response_model=list[SucursalOut])
def list_sucursales(
    db: Session = Depends(get_db), usuario: Usuario = Depends(require_permiso("CU04"))
) -> list[SucursalOut]:
    query = db.query(Sucursal).options(joinedload(Sucursal.ciudad))
    # Cada tienda ve sus sucursales; el SuperAdministrador, las de todas.
    if usuario.empresa_id is not None:
        query = query.filter(Sucursal.empresa_id == usuario.empresa_id)
    sucursales = query.order_by(Sucursal.nombre).all()
    return [_to_out(s) for s in sucursales]


@router.post("", response_model=SucursalOut, status_code=status.HTTP_201_CREATED)
def create_sucursal(
    payload: SucursalCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU04")),
) -> SucursalOut:
    # El alta corre en Postgres via sp_crear_sucursal (incluye el get-or-create
    # de la ciudad); el backend solo llama a la funcion, no arma el INSERT.
    # El trigger trg_sucursal_limite_plan puede rechazarla si la empresa ya
    # uso todas las sucursales de su plan (CU10).
    try:
        result = db.execute(
            text(
                "SELECT sp_crear_sucursal(:nombre, :ciudad_nombre, :departamento, :direccion, "
                ":horario_atencion, :telefono, :estado, :latitud, :longitud)"
            ),
            {
                "nombre": payload.nombre,
                "ciudad_nombre": payload.ciudad_nombre,
                "departamento": payload.departamento,
                "direccion": payload.direccion,
                "horario_atencion": payload.horario_atencion,
                "telefono": payload.telefono,
                "estado": payload.estado,
                "latitud": payload.latitud,
                "longitud": payload.longitud,
            },
        )
        sucursal_id = result.scalar_one()
        db.commit()
    except DBAPIError as err:
        db.rollback()
        http = http_desde_pg(err)
        if http is None:
            raise
        raise http from err

    sucursal = _get_sucursal_or_404(db, sucursal_id)
    log_bitacora(db, admin, "CREAR", "sucursal", sucursal.id, f"Alta de sucursal: {sucursal.nombre}", request)
    return _to_out(sucursal)


@router.put("/{sucursal_id}", response_model=SucursalOut)
def update_sucursal(
    sucursal_id: int,
    payload: SucursalUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU04")),
) -> SucursalOut:
    _get_sucursal_or_404(db, sucursal_id)

    try:
        db.execute(
            text(
                "SELECT sp_actualizar_sucursal(:id, :nombre, :ciudad_nombre, :departamento, :direccion, "
                ":horario_atencion, :telefono, :estado, :latitud, :longitud)"
            ),
            {
                "id": sucursal_id,
                "nombre": payload.nombre,
                "ciudad_nombre": payload.ciudad_nombre,
                "departamento": payload.departamento,
                "direccion": payload.direccion,
                "horario_atencion": payload.horario_atencion,
                "telefono": payload.telefono,
                "estado": payload.estado,
                "latitud": payload.latitud,
                "longitud": payload.longitud,
            },
        )
        db.commit()
    except DBAPIError as err:
        db.rollback()
        http = http_desde_pg(err)
        if http is None:
            raise
        raise http from err

    sucursal = _get_sucursal_or_404(db, sucursal_id)
    log_bitacora(db, admin, "ACTUALIZAR", "sucursal", sucursal.id, f"Edicion de sucursal: {sucursal.nombre}", request)
    return _to_out(sucursal)


@router.delete("/{sucursal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sucursal(
    sucursal_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU04")),
) -> None:
    sucursal = _get_sucursal_or_404(db, sucursal_id)
    nombre = sucursal.nombre

    try:
        db.execute(text("SELECT sp_eliminar_sucursal(:id)"), {"id": sucursal_id})
        db.commit()
    except DBAPIError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No se puede eliminar: la sucursal tiene datos asociados (inventario, ventas, etc).",
        )

    log_bitacora(db, admin, "ELIMINAR", "sucursal", sucursal_id, f"Baja de sucursal: {nombre}", request)
