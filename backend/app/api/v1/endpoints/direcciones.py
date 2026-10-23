"""Direcciones de envio del cliente (con su ubicacion en el mapa).

Son del cliente: las agrega, edita y borra desde Mi cuenta y elige una al
pagar si quiere envio a domicilio. La venta guarda una copia (venta_envio),
asi que editar o borrar una direccion no cambia las compras ya hechas.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.ventas import _get_cliente_o_403
from app.db.session import get_db
from app.models import Usuario
from app.schemas.direcciones import DireccionIn, DireccionOut

router = APIRouter()

_CAMPOS = "id, alias, direccion, referencia, ciudad, latitud, longitud, predeterminada, actualizado_en"
MAX_DIRECCIONES = 10


def _de_cliente(db: Session, direccion_id: int, cliente_id: int):
    fila = db.execute(
        text(f"SELECT {_CAMPOS} FROM direccion_cliente WHERE id = :id AND cliente_id = :c"),
        {"id": direccion_id, "c": cliente_id},
    ).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dirección no encontrada.")
    return fila


def _limpio(texto: str | None) -> str | None:
    texto = (texto or "").strip()
    return texto or None


def _datos(payload: DireccionIn) -> dict:
    return {
        "alias": payload.alias.strip(),
        "direccion": payload.direccion.strip(),
        "referencia": _limpio(payload.referencia),
        "ciudad": _limpio(payload.ciudad),
        "lat": payload.latitud,
        "lng": payload.longitud,
        "pred": payload.predeterminada,
    }


def _quitar_predeterminada(db: Session, cliente_id: int, salvo: int | None = None) -> None:
    # Solo una predeterminada por cliente.
    db.execute(
        text("UPDATE direccion_cliente SET predeterminada = FALSE WHERE cliente_id = :c AND id IS DISTINCT FROM :s"),
        {"c": cliente_id, "s": salvo},
    )


@router.get("", response_model=list[DireccionOut])
def mis_direcciones(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)) -> list[DireccionOut]:
    cliente = _get_cliente_o_403(db, usuario)
    filas = db.execute(
        text(f"SELECT {_CAMPOS} FROM direccion_cliente WHERE cliente_id = :c ORDER BY predeterminada DESC, alias"),
        {"c": cliente.id},
    ).mappings().all()
    return [DireccionOut(**f) for f in filas]


@router.post("", response_model=DireccionOut, status_code=status.HTTP_201_CREATED)
def agregar_direccion(
    payload: DireccionIn, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)
) -> DireccionOut:
    cliente = _get_cliente_o_403(db, usuario)
    total = db.execute(text("SELECT count(*) FROM direccion_cliente WHERE cliente_id = :c"), {"c": cliente.id}).scalar()
    if total >= MAX_DIRECCIONES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Puedes guardar hasta {MAX_DIRECCIONES} direcciones.")
    datos = _datos(payload)
    # La primera direccion queda como predeterminada.
    datos["pred"] = datos["pred"] or total == 0
    if datos["pred"]:
        _quitar_predeterminada(db, cliente.id)
    nuevo_id = db.execute(
        text(
            "INSERT INTO direccion_cliente (cliente_id, alias, direccion, referencia, ciudad, latitud, longitud, predeterminada) "
            "VALUES (:c, :alias, :direccion, :referencia, :ciudad, :lat, :lng, :pred) RETURNING id"
        ),
        {"c": cliente.id, **datos},
    ).scalar_one()
    db.commit()
    return DireccionOut(**_de_cliente(db, nuevo_id, cliente.id))


@router.put("/{direccion_id}", response_model=DireccionOut)
def editar_direccion(
    direccion_id: int,
    payload: DireccionIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> DireccionOut:
    cliente = _get_cliente_o_403(db, usuario)
    _de_cliente(db, direccion_id, cliente.id)
    datos = _datos(payload)
    if datos["pred"]:
        _quitar_predeterminada(db, cliente.id, direccion_id)
    db.execute(
        text(
            "UPDATE direccion_cliente SET alias = :alias, direccion = :direccion, referencia = :referencia, "
            "ciudad = :ciudad, latitud = :lat, longitud = :lng, predeterminada = :pred, actualizado_en = now() "
            "WHERE id = :id"
        ),
        {"id": direccion_id, **datos},
    )
    db.commit()
    return DireccionOut(**_de_cliente(db, direccion_id, cliente.id))


@router.delete("/{direccion_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_direccion(
    direccion_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)
) -> None:
    cliente = _get_cliente_o_403(db, usuario)
    fila = _de_cliente(db, direccion_id, cliente.id)
    db.execute(text("DELETE FROM direccion_cliente WHERE id = :id"), {"id": direccion_id})
    # Si era la predeterminada, pasa a serlo la mas reciente.
    if fila["predeterminada"]:
        db.execute(
            text(
                "UPDATE direccion_cliente SET predeterminada = TRUE WHERE id = "
                "(SELECT id FROM direccion_cliente WHERE cliente_id = :c ORDER BY actualizado_en DESC LIMIT 1)"
            ),
            {"c": cliente.id},
        )
    db.commit()


def guardar_envio(db: Session, venta_ids: list[int], cliente_id: int, direccion_id: int) -> None:
    """Copia la direccion elegida a cada venta (envio a domicilio). La usan
    los endpoints de checkout antes de confirmar la transaccion."""
    fila = db.execute(
        text(
            "SELECT d.direccion, d.referencia, d.ciudad, d.latitud, d.longitud, u.nombre, c.telefono "
            "FROM direccion_cliente d JOIN cliente c ON c.id = d.cliente_id JOIN usuario u ON u.id = c.id "
            "WHERE d.id = :d AND d.cliente_id = :c"
        ),
        {"d": direccion_id, "c": cliente_id},
    ).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Elige una de tus direcciones para el envío.")
    for venta_id in venta_ids:
        db.execute(
            text(
                "INSERT INTO venta_envio (venta_id, destinatario, telefono, direccion, referencia, ciudad, latitud, longitud) "
                "VALUES (:v, :nombre, :telefono, :direccion, :referencia, :ciudad, :latitud, :longitud)"
            ),
            {"v": venta_id, **fila},
        )
