from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import ADMIN_TIPOS, require_permiso
from app.db.session import get_db
from app.models import Inventario, Producto, Sucursal, Usuario
from app.schemas.catalogo import CatalogoProductoOut, CatalogoVarianteOut, SucursalOpcion

router = APIRouter()


@router.get("/sucursales", response_model=list[SucursalOpcion])
def list_sucursales_catalogo(
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_permiso("CU08")),
) -> list[SucursalOpcion]:
    return db.query(Sucursal).order_by(Sucursal.nombre).all()


@router.get("/sucursales/{sucursal_id}/productos", response_model=list[CatalogoProductoOut])
def list_catalogo_sucursal(
    sucursal_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU08")),
) -> list[CatalogoProductoOut]:
    sucursal = db.query(Sucursal).filter(Sucursal.id == sucursal_id).first()
    if sucursal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sucursal no encontrada.")

    # CU08/CU12: Encargado/Cajero solo consultan el catalogo/inventario de SU
    # sucursal -- antes esto solo se ocultaba en el frontend, pero la API en
    # si no lo exigia (se podia pedir cualquier sucursal_id directo).
    # Administrador ve todas.
    if usuario.tipo not in ADMIN_TIPOS and sucursal_id != getattr(usuario, "sucursal_id", None):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No podes consultar el catalogo de otra sucursal.")

    productos = (
        db.query(Producto)
        .join(Inventario, Inventario.producto_id == Producto.id)
        .filter(Inventario.sucursal_id == sucursal_id, Producto.estado == "activo")
        .options(
            joinedload(Producto.marca),
            joinedload(Producto.categoria),
            joinedload(Producto.imagenes),
            joinedload(Producto.inventarios).joinedload(Inventario.talla),
            joinedload(Producto.inventarios).joinedload(Inventario.color),
        )
        .distinct()
        .order_by(Producto.nombre)
        .all()
    )

    resultado: list[CatalogoProductoOut] = []
    for producto in productos:
        variantes_sucursal = [i for i in producto.inventarios if i.sucursal_id == sucursal_id]
        cantidad_total = sum(i.cantidad for i in variantes_sucursal)
        resultado.append(
            CatalogoProductoOut(
                id=producto.id,
                nombre=producto.nombre,
                marca_nombre=producto.marca.nombre,
                categoria_nombre=producto.categoria.nombre,
                precio=producto.precio,
                imagen_url=producto.imagenes[0].url if producto.imagenes else None,
                cantidad_total=cantidad_total,
                disponible=cantidad_total > 0,
                variantes=[
                    CatalogoVarianteOut(
                        id=i.id, talla_codigo=i.talla.codigo, color_nombre=i.color.nombre, cantidad=i.cantidad
                    )
                    for i in variantes_sucursal
                ],
            )
        )
    return resultado
