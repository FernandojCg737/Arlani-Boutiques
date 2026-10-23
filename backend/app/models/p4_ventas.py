from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ItemLinea(Base):
    __tablename__ = "item_linea"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("producto.id"))
    talla_id: Mapped[int] = mapped_column(ForeignKey("talla.id"))
    color_id: Mapped[int] = mapped_column(ForeignKey("color.id"))
    cantidad: Mapped[int] = mapped_column()
    tipo: Mapped[str] = mapped_column(String(30))

    producto: Mapped["Producto"] = relationship(back_populates="items_linea")
    talla: Mapped["Talla"] = relationship(back_populates="items_linea")
    color: Mapped["Color"] = relationship(back_populates="items_linea")

    __mapper_args__ = {
        "polymorphic_identity": "item_linea",
        "polymorphic_on": "tipo",
    }


class Reserva(Base):
    __tablename__ = "reserva"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"))
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursal.id"))
    horario_atencion: Mapped[datetime] = mapped_column(DateTime)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    cliente: Mapped["Cliente"] = relationship(back_populates="reservas")
    sucursal: Mapped["Sucursal"] = relationship(back_populates="reservas")
    detalles: Mapped[list["DetalleReserva"]] = relationship(back_populates="reserva", cascade="all, delete-orphan")


class DetalleReserva(ItemLinea):
    __tablename__ = "detalle_reserva"

    id: Mapped[int] = mapped_column(ForeignKey("item_linea.id"), primary_key=True)
    reserva_id: Mapped[int] = mapped_column(ForeignKey("reserva.id"))

    reserva: Mapped["Reserva"] = relationship(back_populates="detalles")

    __mapper_args__ = {"polymorphic_identity": "detalle_reserva"}


class Carrito(Base):
    __tablename__ = "carrito"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    estado: Mapped[str] = mapped_column(String(20), default="activo")

    cliente: Mapped["Cliente"] = relationship(back_populates="carritos")
    detalles: Mapped[list["DetalleCarrito"]] = relationship(back_populates="carrito", cascade="all, delete-orphan")
    venta_digital: Mapped["VentaDigital | None"] = relationship(back_populates="carrito")


class DetalleCarrito(ItemLinea):
    __tablename__ = "detalle_carrito"

    id: Mapped[int] = mapped_column(ForeignKey("item_linea.id"), primary_key=True)
    carrito_id: Mapped[int] = mapped_column(ForeignKey("carrito.id"))
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # Sucursal de retiro elegida AL AGREGAR el producto (pedido del usuario):
    # si el carrito termina con items de mas de una sucursal, el checkout
    # reparte el pago en varias ventas, una por sucursal -- ver
    # capturar_orden_paypal/checkout_qr en ventas.py.
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursal.id"))

    carrito: Mapped["Carrito"] = relationship(back_populates="detalles")
    sucursal: Mapped["Sucursal"] = relationship()

    __mapper_args__ = {"polymorphic_identity": "detalle_carrito"}


class Venta(Base):
    __tablename__ = "venta"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"))
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursal.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")
    tipo: Mapped[str] = mapped_column(String(30))

    cliente: Mapped["Cliente"] = relationship(back_populates="ventas")
    sucursal: Mapped["Sucursal"] = relationship(back_populates="ventas")
    pago: Mapped["Pago | None"] = relationship(back_populates="venta")
    calificacion: Mapped["Calificacion | None"] = relationship(back_populates="venta")
    devoluciones: Mapped[list["Devolucion"]] = relationship(back_populates="venta", cascade="all, delete-orphan")
    # Envio a domicilio (sin fila = recojo en sucursal).
    envio: Mapped["VentaEnvio | None"] = relationship(cascade="all, delete-orphan", passive_deletes=True)

    __mapper_args__ = {
        "polymorphic_identity": "venta",
        "polymorphic_on": "tipo",
    }


class VentaEnvio(Base):
    """Copia de la direccion y la ubicacion del momento de la compra."""

    __tablename__ = "venta_envio"

    venta_id: Mapped[int] = mapped_column(ForeignKey("venta.id", ondelete="CASCADE"), primary_key=True)
    destinatario: Mapped[str] = mapped_column(String(150))
    telefono: Mapped[str | None] = mapped_column(String(30))
    direccion: Mapped[str] = mapped_column(String(250))
    referencia: Mapped[str | None] = mapped_column(String(250))
    ciudad: Mapped[str | None] = mapped_column(String(80))
    latitud: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitud: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VentaPresencial(Venta):
    __tablename__ = "venta_presencial"

    id: Mapped[int] = mapped_column(ForeignKey("venta.id"), primary_key=True)
    # CU11: cualquier tipo de empleado puede atender una venta de mostrador
    # (Administrador, Encargado de Sucursal o Cajero), no solo un Cajero.
    empleado_id: Mapped[int] = mapped_column(ForeignKey("empleado.id"))

    atendido_por: Mapped["Empleado"] = relationship(back_populates="ventas_atendidas")
    detalles: Mapped[list["DetalleVentaPresencial"]] = relationship(
        back_populates="venta_presencial", cascade="all, delete-orphan"
    )

    __mapper_args__ = {"polymorphic_identity": "venta_presencial"}


class DetalleVentaPresencial(ItemLinea):
    __tablename__ = "detalle_venta_presencial"

    id: Mapped[int] = mapped_column(ForeignKey("item_linea.id"), primary_key=True)
    venta_presencial_id: Mapped[int] = mapped_column(ForeignKey("venta_presencial.id"))
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    venta_presencial: Mapped["VentaPresencial"] = relationship(back_populates="detalles")

    __mapper_args__ = {"polymorphic_identity": "detalle_venta_presencial"}


class VentaDigital(Venta):
    __tablename__ = "venta_digital"

    id: Mapped[int] = mapped_column(ForeignKey("venta.id"), primary_key=True)
    carrito_id: Mapped[int] = mapped_column(ForeignKey("carrito.id"), unique=True)

    carrito: Mapped["Carrito"] = relationship(back_populates="venta_digital")
    detalles: Mapped[list["DetalleVentaDigital"]] = relationship(
        back_populates="venta_digital", cascade="all, delete-orphan"
    )

    __mapper_args__ = {"polymorphic_identity": "venta_digital"}


class DetalleVentaDigital(ItemLinea):
    __tablename__ = "detalle_venta_digital"

    id: Mapped[int] = mapped_column(ForeignKey("item_linea.id"), primary_key=True)
    venta_digital_id: Mapped[int] = mapped_column(ForeignKey("venta_digital.id"))
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    venta_digital: Mapped["VentaDigital"] = relationship(back_populates="detalles")

    __mapper_args__ = {"polymorphic_identity": "detalle_venta_digital"}


class Pago(Base):
    __tablename__ = "pago"

    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("venta.id"), unique=True)
    monto: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    metodo: Mapped[str] = mapped_column(String(30))
    # estados: pendiente | verificando (QR subido, falta revision) |
    # completado | rechazado
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Pago por QR (CU11): el cliente sube la foto del comprobante de
    # transferencia y un cajero/encargado la revisa manualmente para
    # aprobar o rechazar el pago -- no hay forma de verificar un QR
    # automaticamente, a diferencia de PayPal.
    comprobante_url: Mapped[str | None] = mapped_column(String(500))
    revisado_por_id: Mapped[int | None] = mapped_column(ForeignKey("empleado.id"))
    # Metodo de pago de la tienda con el que se pago, y por que se rechazo.
    metodo_pago_id: Mapped[int | None] = mapped_column(ForeignKey("metodo_pago_empresa.id", ondelete="SET NULL"))
    motivo_rechazo: Mapped[str | None] = mapped_column(Text)

    venta: Mapped["Venta"] = relationship(back_populates="pago")
    metodo_pago: Mapped["MetodoPagoEmpresa | None"] = relationship()
    transaccion: Mapped["Transaccion | None"] = relationship(back_populates="pago")
    revisado_por: Mapped["Empleado | None"] = relationship()


class UsoArPrenda(Base):
    """Registro de cada uso del probador de realidad aumentada (CU09): quien
    lo uso, que prenda, en que modo (online = camara en vivo, virtual = foto)
    y cuando. Se muestra en el dashboard de administracion (P4 > CU09)."""

    __tablename__ = "uso_ar_prenda"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("producto.id"))
    modo: Mapped[str] = mapped_column(String(20))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    usuario: Mapped["Usuario"] = relationship()
    producto: Mapped["Producto"] = relationship()


class Transaccion(Base):
    __tablename__ = "transaccion"

    id: Mapped[int] = mapped_column(primary_key=True)
    pago_id: Mapped[int] = mapped_column(ForeignKey("pago.id"), unique=True)
    pasarela: Mapped[str] = mapped_column(String(30))
    referencia_externa: Mapped[str | None] = mapped_column(String(150))
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    pago: Mapped["Pago"] = relationship(back_populates="transaccion")


class Devolucion(Base):
    """CU11: devolucion total o parcial de una venta ya pagada. Un empleado
    (Administrador/Encargado/Cajero) la procesa desde el panel de Gestion de
    Ventas; al aprobarla y completarla se reingresa el stock al inventario y
    se actualiza el estado de la venta a 'devuelto' o 'devuelto_parcial'."""

    __tablename__ = "devolucion"

    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("venta.id"))
    empleado_id: Mapped[int | None] = mapped_column(ForeignKey("empleado.id"), nullable=True)
    motivo: Mapped[str] = mapped_column(String(30))
    tipo: Mapped[str] = mapped_column(String(20))  # 'total' | 'parcial'
    monto_reembolso: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    metodo_reembolso: Mapped[str] = mapped_column(String(30))  # 'mismo_medio' | 'credito_tienda' | 'efectivo'
    # estados: solicitada -> aprobada -> completada | rechazada
    estado: Mapped[str] = mapped_column(String(20), default="solicitada")
    fecha_solicitud: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    fecha_resolucion: Mapped[datetime | None] = mapped_column(DateTime)
    observaciones: Mapped[str | None] = mapped_column(Text)

    venta: Mapped["Venta"] = relationship(back_populates="devoluciones")
    empleado: Mapped["Empleado | None"] = relationship()
    detalles: Mapped[list["DetalleDevolucion"]] = relationship(
        back_populates="devolucion", cascade="all, delete-orphan"
    )


class DetalleDevolucion(Base):
    """Items que se devuelven en una devolucion -- referencia al detalle
    original de la venta (item_linea) para saber que producto/talla/color era,
    y cuantas unidades de ese item se devuelven."""

    __tablename__ = "detalle_devolucion"

    id: Mapped[int] = mapped_column(primary_key=True)
    devolucion_id: Mapped[int] = mapped_column(ForeignKey("devolucion.id"))
    item_linea_id: Mapped[int] = mapped_column(ForeignKey("item_linea.id"))
    cantidad_devuelta: Mapped[int] = mapped_column()

    devolucion: Mapped["Devolucion"] = relationship(back_populates="detalles")
    item_linea: Mapped["ItemLinea"] = relationship()
