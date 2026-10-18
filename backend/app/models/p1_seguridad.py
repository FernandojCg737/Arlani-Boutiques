from datetime import date, datetime, time

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, String, Table, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

rol_permiso = Table(
    "rol_permiso",
    Base.metadata,
    Column("rol_id", ForeignKey("rol.id"), primary_key=True),
    Column("permiso_id", ForeignKey("permiso.id"), primary_key=True),
)


class Rol(Base):
    __tablename__ = "rol"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(255))

    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="rol")
    permisos: Mapped[list["Permiso"]] = relationship(secondary=rol_permiso, back_populates="roles")


class Permiso(Base):
    __tablename__ = "permiso"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(255))

    roles: Mapped[list["Rol"]] = relationship(secondary=rol_permiso, back_populates="permisos")


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(150), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    estado: Mapped[str] = mapped_column(String(20), default="activo")
    fecha_registro: Mapped[date] = mapped_column(Date, default=date.today)
    tipo: Mapped[str] = mapped_column(String(30))
    metodo_registro: Mapped[str] = mapped_column(String(20), default="email")

    rol_id: Mapped[int | None] = mapped_column(ForeignKey("rol.id"))
    rol: Mapped["Rol | None"] = relationship(back_populates="usuarios")

    # session_id identifica la sesion activa: cada login la reemplaza, asi
    # que un token viejo (de otro dispositivo) deja de pasar la verificacion.
    session_id: Mapped[str | None] = mapped_column(String(64))
    # Mismo instante de expiracion que lleva el JWT (60 min desde el login).
    # Sin esto, "sesion activa" en CU01 solo significaba "session_id no es
    # null", que nunca se limpiaba si el usuario cerraba la pestana sin
    # desloguearse -- quedaba listado como activo para siempre.
    sesion_expira_en: Mapped[datetime | None] = mapped_column(DateTime)
    reset_code_hash: Mapped[str | None] = mapped_column(String(255))
    reset_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Intentos fallidos del codigo vigente: al llegar al limite se invalida
    # (ver MAX_INTENTOS_CODIGO en auth.py), asi no se puede probar el millon
    # de combinaciones de 6 digitos dentro de los 10 minutos.
    reset_code_intentos: Mapped[int] = mapped_column(default=0)
    # jti del reset_token emitido: cada token de recuperacion sirve una sola
    # vez (se limpia al usarlo en reset-password / login-with-reset-code).
    reset_token_jti: Mapped[str | None] = mapped_column(String(64))

    bitacoras: Mapped[list["Bitacora"]] = relationship(back_populates="usuario")

    __mapper_args__ = {
        "polymorphic_identity": "usuario",
        "polymorphic_on": "tipo",
    }


class Bitacora(Base):
    __tablename__ = "bitacora"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    accion: Mapped[str] = mapped_column(String(100))
    entidad_afectada: Mapped[str] = mapped_column(String(100))
    entidad_id: Mapped[int | None] = mapped_column()
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    detalle: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    # "web" | "movil" -- de que app vino la accion, ver X-Client-Platform en
    # `app/core/audit.py`. Nullable: acciones registradas antes de este
    # campo (o llamadas directas a la API sin el header) quedan sin dato.
    plataforma: Mapped[str | None] = mapped_column(String(20))

    usuario: Mapped["Usuario"] = relationship(back_populates="bitacoras")


class Empleado(Usuario):
    __tablename__ = "empleado"

    id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), primary_key=True)
    sucursal_id: Mapped[int | None] = mapped_column(ForeignKey("sucursal.id"))

    sucursal: Mapped["Sucursal | None"] = relationship(back_populates="empleados")
    movimientos_inventario: Mapped[list["MovimientoInventario"]] = relationship(back_populates="empleado")
    reportes: Mapped[list["Reporte"]] = relationship(back_populates="empleado")
    # CU11: cualquier tipo de empleado (Administrador, Encargado, Cajero)
    # puede atender una venta presencial, no solo un Cajero.
    ventas_atendidas: Mapped[list["VentaPresencial"]] = relationship(back_populates="atendido_por")

    __mapper_args__ = {"polymorphic_identity": "empleado"}


class Administrador(Empleado):
    __tablename__ = "administrador"

    id: Mapped[int] = mapped_column(ForeignKey("empleado.id"), primary_key=True)

    __mapper_args__ = {"polymorphic_identity": "administrador"}


class EncargadoSucursal(Empleado):
    __tablename__ = "encargado_sucursal"

    id: Mapped[int] = mapped_column(ForeignKey("empleado.id"), primary_key=True)

    __mapper_args__ = {"polymorphic_identity": "encargado_sucursal"}


class Cajero(Empleado):
    __tablename__ = "cajero"

    id: Mapped[int] = mapped_column(ForeignKey("empleado.id"), primary_key=True)

    __mapper_args__ = {"polymorphic_identity": "cajero"}


class ConfiguracionAsistencia(Base):
    # Fila unica (id=1) con la hora de liberacion y la clave del dia -- la
    # clave se regenera sola en fn_estado_asistencia_hoy() cuando cambia el
    # dia (barrido perezoso, sin proceso en segundo plano).
    __tablename__ = "configuracion_asistencia"

    id: Mapped[int] = mapped_column(primary_key=True)
    hora_liberacion: Mapped[time] = mapped_column(Time)
    codigo: Mapped[str | None] = mapped_column(String(10))
    codigo_fecha: Mapped[date | None] = mapped_column(Date)
    # Instante (hora Bolivia) en que arranco la ventana de 5 minutos vigente
    # hoy -- ya sea porque se alcanzo hora_liberacion o porque el
    # Administrador la libero manualmente antes. Se resetea a NULL cada dia.
    ventana_inicio: Mapped[datetime | None] = mapped_column(DateTime)


class MarcadoAsistencia(Base):
    __tablename__ = "marcado_asistencia"

    id: Mapped[int] = mapped_column(primary_key=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("empleado.id"))
    fecha: Mapped[date] = mapped_column(Date)
    hora_marcado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    latitud: Mapped[float] = mapped_column(Float)
    longitud: Mapped[float] = mapped_column(Float)
    foto_url: Mapped[str | None] = mapped_column(String(500))

    empleado: Mapped["Empleado"] = relationship()
