from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Notificacion(Base):
    __tablename__ = "notificacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"))
    canal: Mapped[str] = mapped_column(String(30))
    tipo_evento: Mapped[str] = mapped_column(String(50))
    mensaje: Mapped[str] = mapped_column(Text)
    fecha_envio: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")
    leida: Mapped[bool] = mapped_column(Boolean, default=False)
    entidad_tipo: Mapped[str | None] = mapped_column(String(30))
    entidad_id: Mapped[int | None] = mapped_column()

    cliente: Mapped["Cliente"] = relationship(back_populates="notificaciones")


class Reporte(Base):
    __tablename__ = "reporte"

    id: Mapped[int] = mapped_column(primary_key=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("empleado.id"))
    tipo: Mapped[str] = mapped_column(String(50))
    formato: Mapped[str] = mapped_column(String(20))
    fecha_generacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    empleado: Mapped["Empleado"] = relationship(back_populates="reportes")


class Dashboard(Base):
    __tablename__ = "dashboard"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    rol_destino: Mapped[str] = mapped_column(String(50))


class Recomendacion(Base):
    __tablename__ = "recomendacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("producto.id"))
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    origen: Mapped[str] = mapped_column(String(50))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Redactada por Gemini (o una frase generica de respaldo si no hay API
    # key o la llamada falla) -- el ranking/origen los calcula el motor de
    # reglas en SQL, la IA solo explica el por que.
    razon: Mapped[str | None] = mapped_column(Text)
    # Se marca sola via trigger cuando el cliente compra el producto
    # recomendado (ver migracion) -- mide si la recomendacion sirvio.
    convertido: Mapped[bool] = mapped_column(Boolean, default=False)

    cliente: Mapped["Cliente"] = relationship(back_populates="recomendaciones")
    producto: Mapped["Producto"] = relationship(back_populates="recomendaciones")


class Calificacion(Base):
    __tablename__ = "calificacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("venta.id"), unique=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"))
    estrellas: Mapped[int] = mapped_column()
    comentario: Mapped[str | None] = mapped_column(Text)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    venta: Mapped["Venta"] = relationship(back_populates="calificacion")
    cliente: Mapped["Cliente"] = relationship(back_populates="calificaciones")


class VistaProducto(Base):
    __tablename__ = "vista_producto"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("producto.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    cliente: Mapped["Cliente"] = relationship(back_populates="vistas_producto")
    producto: Mapped["Producto"] = relationship(back_populates="vistas")


class ProductoRelacionado(Base):
    """Cache de "tambien te puede interesar" para el detalle de producto
    (CU18) -- se recalcula por producto (no por cliente) cada 24h, igual
    criterio que Recomendacion, para no depender de Gemini en cada visita.
    Tiene DOS FK a producto (el que se esta viendo y el sugerido), por eso
    no se le pone relationship() de ida y vuelta -- se consulta con SQL
    directo en el endpoint, igual que el resto del motor de recomendaciones."""

    __tablename__ = "producto_relacionado"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("producto.id"))
    relacionado_id: Mapped[int] = mapped_column(ForeignKey("producto.id"))
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    origen: Mapped[str] = mapped_column(String(50))
    razon: Mapped[str | None] = mapped_column(Text)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Chatbot(Base):
    __tablename__ = "chatbot"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"))
    canal: Mapped[str] = mapped_column(String(30))
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresa.id"))
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime)

    cliente: Mapped["Cliente"] = relationship(back_populates="chats")
    mensajes: Mapped[list["ChatbotMensaje"]] = relationship(
        back_populates="chatbot", cascade="all, delete-orphan", order_by="ChatbotMensaje.fecha"
    )


class ChatbotMensaje(Base):
    __tablename__ = "chatbot_mensaje"

    id: Mapped[int] = mapped_column(primary_key=True)
    chatbot_id: Mapped[int] = mapped_column(ForeignKey("chatbot.id"))
    remitente: Mapped[str] = mapped_column(String(10))  # 'cliente' | 'bot'
    mensaje: Mapped[str] = mapped_column(Text)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # CU18: lo que el modelo de la tienda entendio del mensaje del cliente.
    intencion: Mapped[str | None] = mapped_column(String(30))
    confianza: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))

    chatbot: Mapped["Chatbot"] = relationship(back_populates="mensajes")
