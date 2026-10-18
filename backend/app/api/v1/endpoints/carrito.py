from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_permiso, require_permiso_cliente
from app.db.session import get_db
from app.models import Carrito, Cliente, Color, DetalleCarrito, Inventario, Producto, Sucursal, Talla, Usuario
from app.schemas.carrito import CarritoAdminOut, CarritoItemCreate, CarritoItemUpdate, CarritoOut, DetalleCarritoOut

router = APIRouter()
admin_router = APIRouter()


def _get_cliente_o_403(db: Session, usuario: Usuario) -> Cliente:
    cliente = db.query(Cliente).filter(Cliente.id == usuario.id).first()
    if cliente is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo los clientes tienen carrito de compras.")
    return cliente


def _query_con_detalles(db: Session):
    return db.query(Carrito).options(
        joinedload(Carrito.detalles).joinedload(DetalleCarrito.producto).joinedload(Producto.imagenes),
        joinedload(Carrito.detalles).joinedload(DetalleCarrito.talla),
        joinedload(Carrito.detalles).joinedload(DetalleCarrito.color),
        joinedload(Carrito.detalles).joinedload(DetalleCarrito.sucursal),
    )


def _get_carrito_activo(db: Session, cliente_id: int) -> Carrito:
    """El carrito lo crea/obtiene sp_obtener_o_crear_carrito -- aca solo se
    recarga con los joinedload necesarios para armar la respuesta."""
    result = db.execute(text("SELECT sp_obtener_o_crear_carrito(:cliente_id)"), {"cliente_id": cliente_id})
    db.commit()
    carrito_id = result.scalar_one()
    return _query_con_detalles(db).filter(Carrito.id == carrito_id).first()


def _to_detalle_out(d: DetalleCarrito) -> DetalleCarritoOut:
    # Precio VIGENTE del producto, no el guardado al agregarlo: es el que
    # usan el checkout (orden de PayPal) y sp_crear_venta_digital_* al
    # cobrar, asi que el total que ve el cliente es el que se le cobra.
    precio = d.producto.precio
    subtotal = precio * d.cantidad
    return DetalleCarritoOut(
        id=d.id,
        producto_id=d.producto_id,
        producto_nombre=d.producto.nombre,
        producto_imagen_url=d.producto.imagenes[0].url if d.producto.imagenes else None,
        talla_id=d.talla_id,
        talla_codigo=d.talla.codigo,
        color_id=d.color_id,
        color_nombre=d.color.nombre,
        sucursal_id=d.sucursal_id,
        sucursal_nombre=d.sucursal.nombre,
        cantidad=d.cantidad,
        precio_unitario=precio,
        subtotal=subtotal,
    )


def _to_out(carrito: Carrito) -> CarritoOut:
    detalles = [_to_detalle_out(d) for d in carrito.detalles]
    total = sum((d.subtotal for d in detalles), Decimal("0"))
    return CarritoOut(id=carrito.id, estado=carrito.estado, detalles=detalles, total=total)


def _get_detalle_o_404(carrito: Carrito, detalle_id: int) -> DetalleCarrito:
    for detalle in carrito.detalles:
        if detalle.id == detalle_id:
            return detalle
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese producto no esta en tu carrito.")


@router.get("", response_model=CarritoOut)
def obtener_carrito(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU13")),
) -> CarritoOut:
    cliente = _get_cliente_o_403(db, usuario)
    carrito = _get_carrito_activo(db, cliente.id)
    return _to_out(carrito)


@router.post("/items", response_model=CarritoOut, status_code=status.HTTP_201_CREATED)
def agregar_item(
    payload: CarritoItemCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU13")),
) -> CarritoOut:
    cliente = _get_cliente_o_403(db, usuario)

    producto = db.query(Producto).filter(Producto.id == payload.producto_id, Producto.estado == "activo").first()
    if producto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado.")
    talla = db.query(Talla).filter(Talla.id == payload.talla_id).first()
    color = db.query(Color).filter(Color.id == payload.color_id).first()
    sucursal = db.query(Sucursal).filter(Sucursal.id == payload.sucursal_id).first()
    if talla is None or color is None or sucursal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talla, color o sucursal no encontrado.")

    # Pedido del usuario: la sucursal de retiro se fija ACA (no recien en el
    # checkout), asi que el stock se valida de una contra la sucursal real
    # elegida -- no alcanza con que exista stock "en algun lado".
    inventario = (
        db.query(Inventario)
        .filter(
            Inventario.producto_id == payload.producto_id,
            Inventario.talla_id == payload.talla_id,
            Inventario.color_id == payload.color_id,
            Inventario.sucursal_id == payload.sucursal_id,
        )
        .first()
    )
    carrito = _get_carrito_activo(db, cliente.id)

    # sp_agregar_item_carrito SUMA a la linea existente si ya esta la misma
    # combinacion: el stock se valida contra el total resultante, no solo
    # contra lo que se agrega ahora.
    ya_en_carrito = sum(
        d.cantidad
        for d in carrito.detalles
        if (d.producto_id, d.talla_id, d.color_id, d.sucursal_id)
        == (payload.producto_id, payload.talla_id, payload.color_id, payload.sucursal_id)
    )
    if inventario is None or inventario.cantidad < ya_en_carrito + payload.cantidad:
        disponible = inventario.cantidad if inventario else 0
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f'No hay suficiente stock de "{producto.nombre}" ({talla.codigo}, {color.nombre}) en {sucursal.nombre}'
            + (f" (ya tienes {ya_en_carrito} en tu carrito, quedan {disponible})." if ya_en_carrito else "."),
        )

    # sp_agregar_item_carrito ya resuelve el "sumar si es la misma
    # combinacion producto/talla/color/sucursal" (UX estandar de carrito).
    db.execute(
        text(
            "SELECT sp_agregar_item_carrito(:carrito_id, :producto_id, :talla_id, :color_id, "
            ":sucursal_id, :cantidad, :precio)"
        ),
        {
            "carrito_id": carrito.id,
            "producto_id": payload.producto_id,
            "talla_id": payload.talla_id,
            "color_id": payload.color_id,
            "sucursal_id": payload.sucursal_id,
            "cantidad": payload.cantidad,
            "precio": producto.precio,
        },
    )
    db.commit()

    carrito = _get_carrito_activo(db, cliente.id)
    return _to_out(carrito)


@router.put("/items/{detalle_id}", response_model=CarritoOut)
def actualizar_item(
    detalle_id: int,
    payload: CarritoItemUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU13")),
) -> CarritoOut:
    cliente = _get_cliente_o_403(db, usuario)
    carrito = _get_carrito_activo(db, cliente.id)
    detalle = _get_detalle_o_404(carrito, detalle_id)

    inventario = (
        db.query(Inventario)
        .filter(
            Inventario.producto_id == detalle.producto_id,
            Inventario.talla_id == detalle.talla_id,
            Inventario.color_id == detalle.color_id,
            Inventario.sucursal_id == detalle.sucursal_id,
        )
        .first()
    )
    if inventario is None or inventario.cantidad < payload.cantidad:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f'No hay suficiente stock de "{detalle.producto.nombre}" ({detalle.talla.codigo}, '
            f'{detalle.color.nombre}) en {detalle.sucursal.nombre}.',
        )

    db.execute(text("SELECT sp_actualizar_item_carrito(:id, :cantidad)"), {"id": detalle_id, "cantidad": payload.cantidad})
    db.commit()

    carrito = _get_carrito_activo(db, cliente.id)
    return _to_out(carrito)


@router.delete("/items/{detalle_id}", response_model=CarritoOut)
def eliminar_item(
    detalle_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU13")),
) -> CarritoOut:
    cliente = _get_cliente_o_403(db, usuario)
    carrito = _get_carrito_activo(db, cliente.id)
    _get_detalle_o_404(carrito, detalle_id)

    db.execute(text("SELECT sp_eliminar_item_carrito(:id)"), {"id": detalle_id})
    db.commit()

    carrito = _get_carrito_activo(db, cliente.id)
    return _to_out(carrito)


@router.delete("", response_model=CarritoOut)
def vaciar_carrito(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU13")),
) -> CarritoOut:
    cliente = _get_cliente_o_403(db, usuario)
    carrito = _get_carrito_activo(db, cliente.id)

    db.execute(text("SELECT sp_vaciar_carrito(:carrito_id)"), {"carrito_id": carrito.id})
    db.commit()

    carrito = _get_carrito_activo(db, cliente.id)
    return _to_out(carrito)


# ------------------------------------------------------------ CU13: staff --
# Vista de staff sobre los carritos activos (quien tiene items en su carrito
# y cuales) -- de solo lectura, se refresca con polling desde el frontend.
# No incluye carritos vacios ni ya convertidos en venta.


@admin_router.get("", response_model=list[CarritoAdminOut])
def listar_carritos_activos(
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU13")),
) -> list[CarritoAdminOut]:
    carritos = (
        _query_con_detalles(db)
        .join(Cliente, Carrito.cliente_id == Cliente.id)
        .filter(Carrito.estado == "activo")
        .filter(Carrito.detalles.any())
        .order_by(Carrito.fecha_actualizacion.desc())
        .all()
    )

    salida: list[CarritoAdminOut] = []
    for carrito in carritos:
        base = _to_out(carrito)
        salida.append(
            CarritoAdminOut(
                **base.model_dump(),
                cliente_id=carrito.cliente_id,
                cliente_nombre=carrito.cliente.nombre,
                cliente_email=carrito.cliente.email,
                fecha_creacion=carrito.fecha_creacion,
                fecha_actualizacion=carrito.fecha_actualizacion,
                cantidad_items=sum(d.cantidad for d in carrito.detalles),
            )
        )
    return salida
