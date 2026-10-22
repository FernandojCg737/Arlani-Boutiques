from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Rol sin privilegios especiales con el que corren las peticiones del personal
# de una tienda: las politicas de Row Level Security (migracion a8d3f1c6e924)
# solo le dejan ver y modificar filas de su empresa (arlani.empresa_scope).
ROL_TIENDA = "arlani_tenant"


def _aplicar_empresa(conexion, empresa_id: int) -> None:
    conexion.execute(text("SELECT set_config('arlani.empresa_scope', :e, true)"), {"e": str(empresa_id)})
    conexion.execute(text(f"SET LOCAL ROLE {ROL_TIENDA}"))


@event.listens_for(SessionLocal, "after_begin")
def _al_empezar_transaccion(session: Session, _transaccion, conexion) -> None:
    # SET LOCAL dura una transaccion: tras cada commit/rollback se vuelve a aplicar.
    empresa_id = session.info.get("empresa_scope")
    if empresa_id is not None:
        _aplicar_empresa(conexion, empresa_id)


def limitar_a_empresa(db: Session, empresa_id: int) -> None:
    """Desde aqui, esta sesion solo ve y modifica datos de la empresa."""
    db.info["empresa_scope"] = empresa_id
    # La transaccion actual ya empezo (se cargo el usuario): se aplica ya.
    _aplicar_empresa(db, empresa_id)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
