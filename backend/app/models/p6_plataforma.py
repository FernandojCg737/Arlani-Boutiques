"""Paquete 6 -- Plataforma SaaS (2do parcial): empresas (tenants), planes y
suscripciones. Las escrituras van por funciones/PA de Postgres (ver la
migracion c4e8a1f7b2d9); estos modelos sirven para lecturas y relaciones."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class PlanSuscripcion(Base):
    __tablename__ = "plan_suscripcion"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(60))
    precio_mensual: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    max_sucursales: Mapped[int] = mapped_column()
    dias_prueba: Mapped[int | None] = mapped_column()
    ia_generativa: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    orden: Mapped[int] = mapped_column(default=0)


class Empresa(Base):
    __tablename__ = "empresa"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    subdominio: Mapped[str] = mapped_column(String(40), unique=True)
    ciudad: Mapped[str | None] = mapped_column(String(80))
    color_marca: Mapped[str] = mapped_column(String(7), default="#1f2a44")
    logo_url: Mapped[str | None] = mapped_column(String(500))
    email_contacto: Mapped[str | None] = mapped_column(String(150))
    estado: Mapped[str] = mapped_column(String(20), default="activa")
    propietario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    suscripciones: Mapped[list["Suscripcion"]] = relationship(back_populates="empresa")


class Suscripcion(Base):
    __tablename__ = "suscripcion"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"))
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan_suscripcion.id"))
    periodo: Mapped[str] = mapped_column(String(10))
    monto: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    fecha_inicio: Mapped[date] = mapped_column(Date, default=date.today)
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default="activa")
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    empresa: Mapped["Empresa"] = relationship(back_populates="suscripciones")
    plan: Mapped["PlanSuscripcion"] = relationship()
