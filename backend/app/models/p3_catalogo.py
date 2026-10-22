from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.p1_seguridad import Usuario


class Categoria(Base):
    __tablename__ = "categoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True)

    productos: Mapped[list["Producto"]] = relationship(back_populates="categoria")


class Talla(Base):
    __tablename__ = "talla"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)

    inventarios: Mapped[list["Inventario"]] = relationship(back_populates="talla")
    items_linea: Mapped[list["ItemLinea"]] = relationship(back_populates="talla")


class Color(Base):
    __tablename__ = "color"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50))
    codigo_hex: Mapped[str | None] = mapped_column(String(7))

    inventarios: Mapped[list["Inventario"]] = relationship(back_populates="color")
    items_linea: Mapped[list["ItemLinea"]] = relationship(back_populates="color")


class Temporada(Base):
    __tablename__ = "temporada"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date] = mapped_column(Date)
    # Cada tienda tiene sus temporadas (la base pone la empresa de quien la crea).
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"), server_default=text("fn_empresa_para_alta()"))

    colecciones: Mapped[list["Coleccion"]] = relationship(back_populates="temporada")
    productos: Mapped[list["Producto"]] = relationship(back_populates="temporada")


class Coleccion(Base):
    __tablename__ = "coleccion"

    id: Mapped[int] = mapped_column(primary_key=True)
    temporada_id: Mapped[int] = mapped_column(ForeignKey("temporada.id"))
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(Text)

    temporada: Mapped["Temporada"] = relationship(back_populates="colecciones")
    productos: Mapped[list["Producto"]] = relationship(back_populates="coleccion")


class Marca(Base):
    __tablename__ = "marca"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    # Cada tienda tiene sus marcas (unicas por empresa).
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"), server_default=text("fn_empresa_para_alta()"))

    productos: Mapped[list["Producto"]] = relationship(back_populates="marca")


class Proveedor(Usuario):
    __tablename__ = "proveedor"

    id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), primary_key=True)
    nit: Mapped[str] = mapped_column(String(30), unique=True)
    contacto_nombre: Mapped[str | None] = mapped_column(String(150))
    telefono: Mapped[str | None] = mapped_column(String(30))
    direccion: Mapped[str | None] = mapped_column(String(255))

    productos: Mapped[list["Producto"]] = relationship(back_populates="proveedor")

    __mapper_args__ = {"polymorphic_identity": "proveedor"}


class Producto(Base):
    __tablename__ = "producto"

    id: Mapped[int] = mapped_column(primary_key=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"))
    marca_id: Mapped[int] = mapped_column(ForeignKey("marca.id"))
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedor.id"))
    temporada_id: Mapped[int] = mapped_column(ForeignKey("temporada.id"))
    coleccion_id: Mapped[int] = mapped_column(ForeignKey("coleccion.id"))
    # Tienda duena del producto (la pone la base: la empresa de quien lo crea).
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"), server_default=text("fn_empresa_para_alta()"))
    nombre: Mapped[str] = mapped_column(String(150))
    descripcion: Mapped[str | None] = mapped_column(Text)
    precio: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    precio_original: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    estado: Mapped[str] = mapped_column(String(20), default="activo")

    categoria: Mapped["Categoria"] = relationship(back_populates="productos")
    marca: Mapped["Marca"] = relationship(back_populates="productos")
    proveedor: Mapped["Proveedor"] = relationship(back_populates="productos")
    temporada: Mapped["Temporada"] = relationship(back_populates="productos")
    coleccion: Mapped["Coleccion"] = relationship(back_populates="productos")
    empresa: Mapped["Empresa"] = relationship()
    inventarios: Mapped[list["Inventario"]] = relationship(back_populates="producto")
    items_linea: Mapped[list["ItemLinea"]] = relationship(back_populates="producto")
    recomendaciones: Mapped[list["Recomendacion"]] = relationship(back_populates="producto")
    vistas: Mapped[list["VistaProducto"]] = relationship(back_populates="producto")
    imagenes: Mapped[list["ProductoImagen"]] = relationship(
        back_populates="producto", order_by="ProductoImagen.orden", cascade="all, delete-orphan"
    )
    prenda_ar: Mapped["PrendaAr | None"] = relationship(
        back_populates="producto", uselist=False, cascade="all, delete-orphan"
    )


class ProductoImagen(Base):
    __tablename__ = "producto_imagen"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("producto.id"))
    url: Mapped[str] = mapped_column(String(500))
    orden: Mapped[int] = mapped_column(default=0)

    producto: Mapped["Producto"] = relationship(back_populates="imagenes")


class Inventario(Base):
    __tablename__ = "inventario"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("producto.id"))
    talla_id: Mapped[int] = mapped_column(ForeignKey("talla.id"))
    color_id: Mapped[int] = mapped_column(ForeignKey("color.id"))
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursal.id"))
    cantidad: Mapped[int] = mapped_column(default=0)
    estado: Mapped[str] = mapped_column(String(20), default="disponible")

    producto: Mapped["Producto"] = relationship(back_populates="inventarios")
    talla: Mapped["Talla"] = relationship(back_populates="inventarios")
    color: Mapped["Color"] = relationship(back_populates="inventarios")
    sucursal: Mapped["Sucursal"] = relationship(back_populates="inventarios")
    movimientos: Mapped[list["MovimientoInventario"]] = relationship(back_populates="inventario")


class PrendaAr(Base):
    """Imagen con fondo transparente + anclas para el probador virtual (CU09)."""

    __tablename__ = "prenda_ar"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("producto.id"), unique=True)
    url: Mapped[str] = mapped_column(String(500))

    # Anclas como fraccion (0.0-1.0) del ancho/alto de la imagen. Los valores
    # por defecto asumen una prenda centrada tipo "flat lay" u hombro fantasma;
    # se pueden ajustar por prenda si la foto no sigue ese encuadre.
    ancla_hombro_izq_x: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.20"))
    ancla_hombro_izq_y: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.15"))
    ancla_hombro_der_x: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.80"))
    ancla_hombro_der_y: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.15"))
    ancla_torso_y: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.65"))

    producto: Mapped["Producto"] = relationship(back_populates="prenda_ar")


class MovimientoInventario(Base):
    __tablename__ = "movimiento_inventario"

    id: Mapped[int] = mapped_column(primary_key=True)
    inventario_id: Mapped[int] = mapped_column(ForeignKey("inventario.id"))
    # Nulo cuando el movimiento lo dispara el sistema (CU10: retener stock
    # al reservar, liberarlo si la reserva vence sin pagar) en vez de una
    # accion puntual de un empleado.
    empleado_id: Mapped[int | None] = mapped_column(ForeignKey("empleado.id"))
    tipo: Mapped[str] = mapped_column(String(20))
    cantidad: Mapped[int] = mapped_column()
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    documento_referencia: Mapped[str | None] = mapped_column(String(100))

    inventario: Mapped["Inventario"] = relationship(back_populates="movimientos")
    empleado: Mapped["Empleado | None"] = relationship(back_populates="movimientos_inventario")
