from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import func, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, joinedload

from app.api.deps import (
    ADMIN_TIPOS,
    PERSONAL_DE_TIENDA,
    cliente_sin_permiso,
    get_current_user,
    get_current_user_optional,
    require_permiso,
    require_permiso_cliente,
)
from app.core.audit import log_bitacora, set_client_ip_for_trigger
from app.core.decart import (
    construir_prompt_ar,
    consultar_estado_trabajo_foto,
    crear_token_cliente_decart,
    enviar_trabajo_foto_ar,
    obtener_resultado_trabajo_foto,
)
from app.core.security import create_ar_job_token, decode_ar_job_token
from app.core.storage import (
    MAX_IMAGE_BYTES,
    delete_prenda_ar_imagen,
    delete_producto_imagen,
    upload_prenda_ar_imagen,
    upload_producto_imagen,
)
from app.db.session import get_db
from app.models import (
    Categoria,
    Coleccion,
    Color,
    Empresa,
    Inventario,
    Marca,
    Producto,
    ProductoImagen,
    Proveedor,
    Sucursal,
    Talla,
    Temporada,
    Usuario,
    UsoArPrenda,
)
from app.schemas.productos import (
    ArFotoEstadoOut,
    ArFotoTrabajoOut,
    ArSesionOut,
    CatalogoBaseOut,
    ColorCreate,
    DisponibilidadOut,
    ImagenOut,
    InventarioCantidadUpdate,
    InventarioOut,
    InventarioUpsert,
    MarcaCreate,
    MarcaOut,
    OpcionOut,
    PrendaArOut,
    PrendaArUpsert,
    ProductoCreate,
    ProductoOut,
    ProductoPublicoOut,
    ProductoUpdate,
)

router = APIRouter()


def _sucursales_disponibles(producto: Producto) -> list[str]:
    nombres = {i.sucursal.nombre for i in producto.inventarios if i.cantidad > 0}
    return sorted(nombres)


def _disponibilidad_admin(producto: Producto) -> list[DisponibilidadOut]:
    totales: dict[str, int] = {}
    for i in producto.inventarios:
        totales[i.sucursal.nombre] = totales.get(i.sucursal.nombre, 0) + i.cantidad
    return [
        DisponibilidadOut(sucursal_nombre=nombre, cantidad=cantidad)
        for nombre, cantidad in sorted(totales.items())
        if cantidad > 0
    ]


def _to_out(producto: Producto) -> ProductoOut:
    return ProductoOut(
        id=producto.id,
        nombre=producto.nombre,
        descripcion=producto.descripcion,
        precio=producto.precio,
        precio_original=producto.precio_original,
        estado=producto.estado,
        categoria_id=producto.categoria_id,
        categoria_nombre=producto.categoria.nombre,
        marca_id=producto.marca_id,
        marca_nombre=producto.marca.nombre,
        proveedor_id=producto.proveedor_id,
        proveedor_nombre=producto.proveedor.nombre,
        temporada_id=producto.temporada_id,
        temporada_nombre=producto.temporada.nombre,
        coleccion_id=producto.coleccion_id,
        coleccion_nombre=producto.coleccion.nombre,
        imagenes=[ImagenOut.model_validate(i) for i in producto.imagenes],
        sucursales_disponibles=_disponibilidad_admin(producto),
        prenda_ar=PrendaArOut.model_validate(producto.prenda_ar) if producto.prenda_ar else None,
    )


def _get_producto_or_404(db: Session, producto_id: int) -> Producto:
    producto = (
        db.query(Producto)
        .options(
            joinedload(Producto.categoria),
            joinedload(Producto.marca),
            joinedload(Producto.proveedor),
            joinedload(Producto.temporada),
            joinedload(Producto.coleccion),
            joinedload(Producto.imagenes),
            joinedload(Producto.prenda_ar),
            joinedload(Producto.inventarios).joinedload(Inventario.sucursal),
        )
        .filter(Producto.id == producto_id)
        .first()
    )
    if producto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado.")
    return producto


@router.get("/catalogo-base", response_model=CatalogoBaseOut)
def get_catalogo_base(
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_permiso("CU05")),
) -> CatalogoBaseOut:
    colecciones = (
        db.query(Coleccion).options(joinedload(Coleccion.temporada)).order_by(Coleccion.nombre).all()
    )
    return CatalogoBaseOut(
        categorias=[OpcionOut.model_validate(c) for c in db.query(Categoria).order_by(Categoria.nombre).all()],
        marcas=[OpcionOut.model_validate(m) for m in db.query(Marca).order_by(Marca.nombre).all()],
        temporadas=[OpcionOut.model_validate(t) for t in db.query(Temporada).order_by(Temporada.nombre).all()],
        colecciones=[
            OpcionOut(id=c.id, nombre=f"{c.nombre} ({c.temporada.nombre})") for c in colecciones
        ],
        proveedores=[
            OpcionOut.model_validate(p)
            for p in db.query(Proveedor).filter(Proveedor.estado == "activo").order_by(Proveedor.nombre).all()
        ],
        sucursales=[OpcionOut.model_validate(s) for s in db.query(Sucursal).order_by(Sucursal.nombre).all()],
        tallas=[
            OpcionOut(id=t.id, nombre=t.codigo) for t in db.query(Talla).order_by(Talla.id).all()
        ],
        colores=[OpcionOut.model_validate(c) for c in db.query(Color).order_by(Color.nombre).all()],
    )


@router.post("/marcas", response_model=MarcaOut, status_code=status.HTTP_201_CREATED)
def create_marca(
    payload: MarcaCreate,
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_permiso("CU05")),
) -> MarcaOut:
    result = db.execute(text("SELECT sp_crear_marca(:nombre)"), {"nombre": payload.nombre})
    marca_id = result.scalar_one()
    db.commit()

    marca = db.query(Marca).filter(Marca.id == marca_id).first()
    return MarcaOut.model_validate(marca)


@router.post("/colores", response_model=OpcionOut, status_code=status.HTTP_201_CREATED)
def create_color(
    payload: ColorCreate,
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_permiso("CU05")),
) -> OpcionOut:
    """Igual que sp_crear_marca (find-or-create por nombre): usado por la
    opcion "Otro..." al cargar inventario, para colores que no estan en el
    catalogo fijo."""
    result = db.execute(text("SELECT sp_crear_color(:nombre)"), {"nombre": payload.nombre})
    color_id = result.scalar_one()
    db.commit()

    color = db.query(Color).filter(Color.id == color_id).first()
    return OpcionOut.model_validate(color)


def _to_publico(producto: Producto) -> ProductoPublicoOut:
    return ProductoPublicoOut(
        id=producto.id,
        tienda=producto.empresa.subdominio,
        tienda_nombre=producto.empresa.nombre,
        tienda_logo=producto.empresa.logo_url,
        tienda_color=producto.empresa.color_marca,
        nombre=producto.nombre,
        descripcion=producto.descripcion,
        precio=producto.precio,
        precio_original=producto.precio_original,
        marca_nombre=producto.marca.nombre,
        categoria_nombre=producto.categoria.nombre,
        temporada_nombre=producto.temporada.nombre,
        imagenes=[i.url for i in producto.imagenes],
        sucursales_disponibles=_sucursales_disponibles(producto),
        prenda_ar=PrendaArOut.model_validate(producto.prenda_ar) if producto.prenda_ar else None,
    )


@router.get("/publico", response_model=list[ProductoPublicoOut])
def list_productos_publico(
    tienda: str | None = Query(default=None, max_length=40),
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_current_user_optional),
) -> list[ProductoPublicoOut]:
    """Productos a la venta de las tiendas activas. tienda=<subdominio>:
    solo los de esa boutique. El personal de una tienda (punto de venta) ve
    solo los de su empresa."""
    if cliente_sin_permiso(usuario, "CU08"):
        return []
    query = (
        db.query(Producto)
        .join(Empresa, Empresa.id == Producto.empresa_id)
        # Tiendas suspendidas o con la suscripcion vencida no venden.
        .filter(Empresa.estado == "activa", func.fn_empresa_operativa(Empresa.id))
        .options(
            joinedload(Producto.empresa),
            joinedload(Producto.marca),
            joinedload(Producto.categoria),
            joinedload(Producto.temporada),
            joinedload(Producto.imagenes),
            joinedload(Producto.prenda_ar),
            joinedload(Producto.inventarios).joinedload(Inventario.sucursal),
        )
        .filter(Producto.estado == "activo")
    )
    if usuario is not None and usuario.empresa_id is not None and usuario.tipo in PERSONAL_DE_TIENDA:
        query = query.filter(Producto.empresa_id == usuario.empresa_id)
    elif tienda:
        query = query.filter(Empresa.subdominio == tienda.strip().lower())
    return [_to_publico(p) for p in query.order_by(Producto.nombre).all()]


@router.get("/publico/{producto_id}", response_model=ProductoPublicoOut)
def get_producto_publico(
    producto_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_current_user_optional),
) -> ProductoPublicoOut:
    if cliente_sin_permiso(usuario, "CU08"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta funcionalidad no esta habilitada por el momento.")
    producto = (
        db.query(Producto)
        .options(
            joinedload(Producto.empresa),
            joinedload(Producto.marca),
            joinedload(Producto.categoria),
            joinedload(Producto.temporada),
            joinedload(Producto.imagenes),
            joinedload(Producto.prenda_ar),
            joinedload(Producto.inventarios).joinedload(Inventario.sucursal),
        )
        .filter(Producto.id == producto_id, Producto.estado == "activo", func.fn_empresa_operativa(Producto.empresa_id))
        .first()
    )
    if producto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado.")
    return _to_publico(producto)


def _cargar_producto_para_ar(db: Session, producto_id: int) -> Producto | None:
    return (
        db.query(Producto)
        .options(
            joinedload(Producto.prenda_ar),
            joinedload(Producto.categoria),
            joinedload(Producto.marca),
            joinedload(Producto.imagenes),
        )
        .filter(Producto.id == producto_id, Producto.estado == "activo")
        .first()
    )


def _resolver_imagen_referencia(producto: Producto) -> str | None:
    """A diferencia del probador 2D/3D anterior (que necesitaba una imagen
    con fondo transparente y anclas de hombros calibradas a mano), Decart
    genera la superposicion el mismo con solo una imagen de referencia y
    el prompt: no hace falta un recorte especial. Por eso, si el producto
    no tiene una imagen AR dedicada (prenda_ar), usamos su primera foto de
    catalogo como referencia en su lugar, para que el probador funcione en
    cualquier producto sin trabajo manual adicional. La imagen dedicada
    sigue siendo la mejor opcion (foto limpia, sin fondo ni modelo) pero
    ya no es un requisito."""
    if producto.prenda_ar is not None:
        return producto.prenda_ar.url
    if producto.imagenes:
        candidata = producto.imagenes[0].url
        # Decart necesita una URL absoluta (la va a pedir el mismo por
        # fetch). Algunos productos de catalogo todavia tienen la foto
        # placeholder generica de antes de conectar el backend real (ruta
        # relativa tipo /img/productos/..., servida por Angular, no una
        # imagen subida): esas no sirven como referencia, asi que se
        # ignoran en vez de mandarlas rotas.
        if candidata.startswith("http://") or candidata.startswith("https://"):
            return candidata
    return None


def _registrar_uso_ar(db: Session, usuario: Usuario, producto_id: int, modo: str) -> None:
    """CU09: deja constancia de quien probo que prenda, en que modo (online
    = camara en vivo, virtual = foto) y cuando -- se ve en el dashboard de
    administracion (P4 > CU09). Se registra al iniciar el intento (no al
    terminar): asi queda igual el registro aunque la generacion en si falle
    despues, que es lo que de verdad importa para auditar "quien lo uso"."""
    db.add(UsoArPrenda(usuario_id=usuario.id, producto_id=producto_id, modo=modo))
    db.commit()


@router.post("/{producto_id}/ar-sesion", response_model=ArSesionOut)
def crear_ar_sesion(
    producto_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU09")),
) -> ArSesionOut:
    """Arranca una sesion del probador de realidad aumentada en vivo (CU09,
    modo ONLINE): genera un token de cliente de corta duracion (la key
    permanente nunca sale del backend) y arma el prompt de la prenda para
    que el frontend abra la conexion WebRTC directamente contra Decart.

    Requiere sesion iniciada (cualquier cliente registrado, no hace falta
    ser personal): asi queda registrado quien probo cada prenda."""
    producto = _cargar_producto_para_ar(db, producto_id)
    imagen_url = _resolver_imagen_referencia(producto) if producto else None
    if producto is None or imagen_url is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Este producto no tiene fotos para el probador de realidad aumentada.",
        )

    token = crear_token_cliente_decart()
    _registrar_uso_ar(db, usuario, producto_id, "online")
    return ArSesionOut(
        token=token.get("apiKey", ""),
        expira_en=token.get("expiresAt"),
        imagen_url=imagen_url,
        prompt=construir_prompt_ar(producto),
    )


@router.post("/{producto_id}/ar-foto", response_model=ArFotoTrabajoOut, status_code=status.HTTP_201_CREATED)
async def crear_ar_foto(
    producto_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU09")),
) -> ArFotoTrabajoOut:
    """Modo VIRTUAL (CU09): el cliente sube una foto suya en vez de abrir la
    camara en vivo. Se manda esa foto + la imagen de referencia de la
    prenda a un trabajo en cola de Decart (lucy-vton-3.5) y se devuelve el
    job_id para que el frontend consulte el resultado. Requiere sesion
    iniciada, igual que el modo ONLINE."""
    producto = _cargar_producto_para_ar(db, producto_id)
    imagen_url = _resolver_imagen_referencia(producto) if producto else None
    if producto is None or imagen_url is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Este producto no tiene fotos para el probador de realidad aumentada.",
        )

    # No se filtra por content-type aca: ese valor lo manda el navegador y
    # no es confiable (varia entre dispositivos, y las fotos de iPhone
    # suelen ser HEIC aunque el navegador diga otra cosa). El formato real
    # se valida mas abajo, dentro de enviar_trabajo_foto_ar, abriendo el
    # archivo con Pillow -- eso detecta el formato por el contenido real,
    # no por lo que declare el navegador.
    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La foto supera el tamano maximo de 5MB.")

    job_id = enviar_trabajo_foto_ar(content, imagen_url, construir_prompt_ar(producto))
    _registrar_uso_ar(db, usuario, producto_id, "virtual")
    # El cliente nunca ve el job_id real de Decart: recibe un token firmado
    # que lo envuelve junto con su usuario (ver create_ar_job_token). Para
    # el frontend sigue siendo un "job_id" opaco, asi que no cambia nada ahi.
    return ArFotoTrabajoOut(job_id=create_ar_job_token(job_id, usuario.id))


def _job_id_real(job_token: str) -> tuple[str, int]:
    datos = decode_ar_job_token(job_token)
    if datos is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El resultado no existe o ya vencio.")
    return datos


@router.get("/ar-foto/{job_id}", response_model=ArFotoEstadoOut)
def estado_ar_foto(
    job_id: str,
    usuario: Usuario = Depends(require_permiso_cliente("CU09")),
) -> ArFotoEstadoOut:
    """Estado del trabajo en cola (modo VIRTUAL). El frontend hace polling
    a este endpoint hasta que "listo" sea true, y ahi pide el resultado.
    Solo lo consulta quien creo el trabajo."""
    job_real, duenio_id = _job_id_real(job_id)
    if duenio_id != usuario.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El resultado no existe o ya vencio.")
    datos = consultar_estado_trabajo_foto(job_real)
    estado = str(datos.get("status", "desconocido"))
    return ArFotoEstadoOut(
        estado=estado,
        listo=estado.lower() in ("completed", "succeeded", "success"),
        error=estado.lower() in ("failed", "error", "cancelled"),
    )


@router.get("/ar-foto/{job_id}/resultado")
def resultado_ar_foto(job_id: str) -> Response:
    """Sin header de Authorization a proposito: lo carga un <img src> (web)
    o Image.network (movil). La proteccion es el token firmado del path:
    solo lo tiene quien creo el trabajo, y vence a los 30 minutos."""
    job_real, _ = _job_id_real(job_id)
    contenido, content_type = obtener_resultado_trabajo_foto(job_real)
    return Response(content=contenido, media_type=content_type, headers={"Cache-Control": "private, no-store"})


@router.get("", response_model=list[ProductoOut])
def list_productos(
    buscar: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_permiso("CU05")),
) -> list[ProductoOut]:
    query = db.query(Producto).options(
        joinedload(Producto.categoria),
        joinedload(Producto.marca),
        joinedload(Producto.proveedor),
        joinedload(Producto.temporada),
        joinedload(Producto.coleccion),
        joinedload(Producto.imagenes),
        joinedload(Producto.prenda_ar),
        joinedload(Producto.inventarios).joinedload(Inventario.sucursal),
    )
    if buscar:
        query = query.filter(Producto.nombre.ilike(f"%{buscar}%"))
    return [_to_out(p) for p in query.order_by(Producto.nombre).all()]


@router.post("", response_model=ProductoOut, status_code=status.HTTP_201_CREATED)
def create_producto(
    payload: ProductoCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU05")),
) -> ProductoOut:
    set_client_ip_for_trigger(db, request)
    result = db.execute(
        text(
            "SELECT sp_crear_producto(:nombre, :descripcion, :precio, :precio_original, :categoria_id, "
            ":marca_id, :proveedor_id, :temporada_id, :coleccion_id)"
        ),
        {
            "nombre": payload.nombre,
            "descripcion": payload.descripcion,
            "precio": payload.precio,
            "precio_original": payload.precio_original,
            "categoria_id": payload.categoria_id,
            "marca_id": payload.marca_id,
            "proveedor_id": payload.proveedor_id,
            "temporada_id": payload.temporada_id,
            "coleccion_id": payload.coleccion_id,
        },
    )
    producto_id = result.scalar_one()
    db.commit()

    producto = _get_producto_or_404(db, producto_id)
    log_bitacora(db, admin, "CREAR", "producto", producto.id, f"Alta de producto: {producto.nombre}", request)
    return _to_out(producto)


@router.put("/{producto_id}", response_model=ProductoOut)
def update_producto(
    producto_id: int,
    payload: ProductoUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU05")),
) -> ProductoOut:
    _get_producto_or_404(db, producto_id)

    db.execute(
        text(
            "SELECT sp_actualizar_producto(:id, :nombre, :descripcion, :precio, :precio_original, "
            ":categoria_id, :marca_id, :proveedor_id, :temporada_id, :coleccion_id, :estado)"
        ),
        {
            "id": producto_id,
            "nombre": payload.nombre,
            "descripcion": payload.descripcion,
            "precio": payload.precio,
            "precio_original": payload.precio_original,
            "categoria_id": payload.categoria_id,
            "marca_id": payload.marca_id,
            "proveedor_id": payload.proveedor_id,
            "temporada_id": payload.temporada_id,
            "coleccion_id": payload.coleccion_id,
            "estado": payload.estado,
        },
    )
    db.commit()

    producto = _get_producto_or_404(db, producto_id)
    log_bitacora(db, admin, "ACTUALIZAR", "producto", producto.id, f"Edicion de producto: {producto.nombre}", request)
    return _to_out(producto)


def _to_inventario_out(inv: Inventario) -> InventarioOut:
    return InventarioOut(
        id=inv.id,
        sucursal_id=inv.sucursal_id,
        sucursal_nombre=inv.sucursal.nombre,
        talla_id=inv.talla_id,
        talla_codigo=inv.talla.codigo,
        color_id=inv.color_id,
        color_nombre=inv.color.nombre,
        cantidad=inv.cantidad,
    )


@router.get("/{producto_id}/inventario", response_model=list[InventarioOut])
def list_inventario(
    producto_id: int,
    db: Session = Depends(get_db),
    _usuario: Usuario = Depends(require_permiso("CU05")),
) -> list[InventarioOut]:
    _get_producto_or_404(db, producto_id)
    inventarios = (
        db.query(Inventario)
        .options(joinedload(Inventario.sucursal), joinedload(Inventario.talla), joinedload(Inventario.color))
        .filter(Inventario.producto_id == producto_id)
        .join(Sucursal)
        .order_by(Sucursal.nombre)
        .all()
    )
    return [_to_inventario_out(i) for i in inventarios]


@router.post("/{producto_id}/inventario", response_model=InventarioOut, status_code=status.HTTP_201_CREATED)
def upsert_inventario(
    producto_id: int,
    payload: InventarioUpsert,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU05")),
) -> InventarioOut:
    producto = _get_producto_or_404(db, producto_id)

    result = db.execute(
        text(
            "SELECT sp_establecer_inventario(:producto_id, :talla_id, :color_id, :sucursal_id, :cantidad)"
        ),
        {
            "producto_id": producto_id,
            "talla_id": payload.talla_id,
            "color_id": payload.color_id,
            "sucursal_id": payload.sucursal_id,
            "cantidad": payload.cantidad,
        },
    )
    inventario_id = result.scalar_one()
    db.commit()

    inventario = (
        db.query(Inventario)
        .options(joinedload(Inventario.sucursal), joinedload(Inventario.talla), joinedload(Inventario.color))
        .filter(Inventario.id == inventario_id)
        .first()
    )
    log_bitacora(
        db, admin, "ACTUALIZAR", "producto", producto_id, f"Stock actualizado para: {producto.nombre}", request
    )
    return _to_inventario_out(inventario)


@router.put("/{producto_id}/inventario/{inventario_id}", response_model=InventarioOut)
def update_inventario_cantidad(
    producto_id: int,
    inventario_id: int,
    payload: InventarioCantidadUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU05", "CU12")),
) -> InventarioOut:
    producto = _get_producto_or_404(db, producto_id)

    inventario = (
        db.query(Inventario)
        .filter(Inventario.id == inventario_id, Inventario.producto_id == producto_id)
        .first()
    )
    if inventario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro de inventario no encontrado.")

    # CU12: Encargado/Cajero solo controlan el inventario de SU sucursal --
    # Administrador (con o sin sucursal asignada) sigue viendo/editando todas.
    if admin.tipo not in ADMIN_TIPOS and inventario.sucursal_id != getattr(admin, "sucursal_id", None):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No podes modificar el inventario de otra sucursal.")

    db.execute(
        text("SELECT sp_actualizar_inventario_cantidad(:id, :cantidad)"),
        {"id": inventario_id, "cantidad": payload.cantidad},
    )
    db.commit()

    db.refresh(inventario)
    log_bitacora(
        db, admin, "ACTUALIZAR", "producto", producto_id, f"Stock actualizado para: {producto.nombre}", request
    )
    return _to_inventario_out(inventario)


@router.delete("/{producto_id}/inventario/{inventario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inventario(
    producto_id: int,
    inventario_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU05", "CU12")),
) -> None:
    producto = _get_producto_or_404(db, producto_id)

    inventario = (
        db.query(Inventario)
        .filter(Inventario.id == inventario_id, Inventario.producto_id == producto_id)
        .first()
    )
    if inventario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro de inventario no encontrado.")

    # CU12: Encargado/Cajero solo controlan el inventario de SU sucursal --
    # Administrador (con o sin sucursal asignada) sigue viendo/editando todas.
    if admin.tipo not in ADMIN_TIPOS and inventario.sucursal_id != getattr(admin, "sucursal_id", None):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No podes modificar el inventario de otra sucursal.")

    try:
        db.delete(inventario)
        db.commit()
    except DBAPIError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No se puede eliminar: este registro tiene movimientos de stock asociados.",
        )

    log_bitacora(
        db, admin, "ELIMINAR", "producto", producto_id, f"Registro de stock eliminado para: {producto.nombre}", request
    )


@router.post("/{producto_id}/imagenes", response_model=ImagenOut, status_code=status.HTTP_201_CREATED)
async def add_imagen(
    producto_id: int,
    request: Request,
    file: UploadFile,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU05")),
) -> ImagenOut:
    producto = _get_producto_or_404(db, producto_id)
    content = await file.read()
    url = upload_producto_imagen(producto_id, content, file.content_type or "")

    siguiente_orden = len(producto.imagenes)
    result = db.execute(
        text("SELECT sp_agregar_imagen_producto(:producto_id, :url, :orden)"),
        {"producto_id": producto_id, "url": url, "orden": siguiente_orden},
    )
    imagen_id = result.scalar_one()
    db.commit()

    log_bitacora(db, admin, "ACTUALIZAR", "producto", producto_id, f"Se agrego una imagen a: {producto.nombre}", request)
    return ImagenOut(id=imagen_id, url=url, orden=siguiente_orden)


@router.delete("/{producto_id}/imagenes/{imagen_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_imagen(
    producto_id: int,
    imagen_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU05")),
) -> None:
    imagen = (
        db.query(ProductoImagen)
        .filter(ProductoImagen.id == imagen_id, ProductoImagen.producto_id == producto_id)
        .first()
    )
    if imagen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagen no encontrada.")

    url = imagen.url
    db.execute(text("SELECT sp_eliminar_imagen_producto(:id)"), {"id": imagen_id})
    db.commit()
    delete_producto_imagen(url)

    log_bitacora(db, admin, "ACTUALIZAR", "producto", producto_id, "Se elimino una imagen del producto", request)


@router.post("/{producto_id}/ar-imagen", response_model=PrendaArOut, status_code=status.HTTP_201_CREATED)
async def upsert_prenda_ar(
    producto_id: int,
    request: Request,
    file: UploadFile,
    ancla_hombro_izq_x: Decimal = Form(default=Decimal("0.20")),
    ancla_hombro_izq_y: Decimal = Form(default=Decimal("0.15")),
    ancla_hombro_der_x: Decimal = Form(default=Decimal("0.80")),
    ancla_hombro_der_y: Decimal = Form(default=Decimal("0.15")),
    ancla_torso_y: Decimal = Form(default=Decimal("0.65")),
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU05")),
) -> PrendaArOut:
    """Sube (o reemplaza) la imagen con fondo transparente para el probador
    virtual con realidad aumentada (CU09). Las anclas son opcionales: si no
    se envian, se usan los valores por defecto pensados para una foto
    centrada tipo "flat lay"."""
    datos = PrendaArUpsert(
        ancla_hombro_izq_x=ancla_hombro_izq_x,
        ancla_hombro_izq_y=ancla_hombro_izq_y,
        ancla_hombro_der_x=ancla_hombro_der_x,
        ancla_hombro_der_y=ancla_hombro_der_y,
        ancla_torso_y=ancla_torso_y,
    )
    producto = _get_producto_or_404(db, producto_id)
    content = await file.read()
    url = upload_prenda_ar_imagen(producto_id, content, file.content_type or "")

    if producto.prenda_ar is not None:
        delete_prenda_ar_imagen(producto.prenda_ar.url)

    result = db.execute(
        text(
            "SELECT sp_upsert_prenda_ar(:producto_id, :url, :ai_x, :ai_y, :ad_x, :ad_y, :torso_y)"
        ),
        {
            "producto_id": producto_id,
            "url": url,
            "ai_x": datos.ancla_hombro_izq_x,
            "ai_y": datos.ancla_hombro_izq_y,
            "ad_x": datos.ancla_hombro_der_x,
            "ad_y": datos.ancla_hombro_der_y,
            "torso_y": datos.ancla_torso_y,
        },
    )
    result.scalar_one()
    db.commit()

    log_bitacora(
        db, admin, "ACTUALIZAR", "producto", producto_id,
        f"Se configuro el probador de realidad aumentada para: {producto.nombre}", request,
    )
    return PrendaArOut(url=url, **datos.model_dump())


@router.delete("/{producto_id}/ar-imagen", status_code=status.HTTP_204_NO_CONTENT)
def delete_prenda_ar(
    producto_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU05")),
) -> None:
    producto = _get_producto_or_404(db, producto_id)
    if producto.prenda_ar is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este producto no tiene imagen de realidad aumentada.")

    url = producto.prenda_ar.url
    db.execute(text("SELECT sp_eliminar_prenda_ar(:producto_id)"), {"producto_id": producto_id})
    db.commit()
    delete_prenda_ar_imagen(url)

    log_bitacora(
        db, admin, "ACTUALIZAR", "producto", producto_id,
        f"Se elimino el probador de realidad aumentada de: {producto.nombre}", request,
    )
