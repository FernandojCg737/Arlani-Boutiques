"""Fixtures de las pruebas de integracion de reglas criticas.

Cada prueba corre dentro de UNA transaccion de PostgreSQL que se deshace al
final: los commit de los endpoints solo cierran savepoints, asi que nada de
lo que la prueba crea (tiendas, usuarios, ventas...) queda en la base. Se
usa la base local de docker compose; si no esta disponible, se saltean.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.core.security import create_access_token
from app.db.session import SessionLocal, engine, get_db

try:
    with engine.connect() as _c:
        _c.execute(text("SELECT 1"))
    BASE_DISPONIBLE = True
except Exception:
    BASE_DISPONIBLE = False


@dataclass
class Tienda:
    empresa_id: int
    sucursal_id: int
    admin_id: int
    headers: dict


class Prueba:
    """Conexion en una transaccion externa + cliente HTTP de la API."""

    def __init__(self, conexion, client):
        self.conexion = conexion
        self.client = client

    def sql(self, consulta: str, **params):
        # Una peticion de una tienda deja SET LOCAL ROLE en la transaccion:
        # las consultas de la prueba vuelven al rol normal (sin RLS).
        self.conexion.execute(text("RESET ROLE"))
        return self.conexion.execute(text(consulta), params)

    def valor(self, consulta: str, **params):
        return self.sql(consulta, **params).scalar()

    def admin_de(self, empresa_id: int, sucursal_id: int | None = None) -> tuple[int, dict]:
        """Administrador de prueba de la empresa, con su token de acceso."""
        sesion = uuid.uuid4().hex
        rol = self.valor("SELECT id FROM rol WHERE nombre = 'Administrador'")
        usuario_id = self.valor(
            """INSERT INTO usuario (nombre, email, password_hash, estado, fecha_registro, tipo, metodo_registro,
                                    rol_id, empresa_id, session_id, sesion_expira_en, reset_code_intentos)
               VALUES ('Pytest Admin', :email, 'sin-clave', 'activo', CURRENT_DATE, 'administrador', 'email',
                       :rol, :e, :sid, :exp, 0) RETURNING id""",
            email=f"pytest_{sesion[:12]}@example.com", rol=rol, e=empresa_id, sid=sesion,
            exp=datetime.utcnow() + timedelta(hours=2),
        )
        self.sql("INSERT INTO empleado (id, sucursal_id) VALUES (:i, :s)", i=usuario_id, s=sucursal_id)
        self.sql("INSERT INTO administrador (id) VALUES (:i)", i=usuario_id)
        token = create_access_token(str(usuario_id), sesion)
        return usuario_id, {"Authorization": f"Bearer {token}"}

    def tienda(self, plan_codigo: str) -> Tienda:
        """Empresa nueva con suscripcion activa al plan, una sucursal y su administrador."""
        sufijo = uuid.uuid4().hex[:8]
        empresa_id = self.valor(
            """INSERT INTO empresa (nombre, subdominio, ciudad, color_marca, publicos, estado, fecha_creacion, fecha_actualizacion)
               VALUES (:n, :s, 'Santa Cruz', '#1f2a44', '{}', 'activa', now(), now()) RETURNING id""",
            n=f"Pytest {plan_codigo} {sufijo}", s=f"pytest-{sufijo}",
        )
        self.sql(
            """INSERT INTO suscripcion (empresa_id, plan_id, periodo, monto, fecha_inicio, fecha_fin, estado, fecha_registro)
               SELECT :e, id, 'mensual', 0, CURRENT_DATE, CURRENT_DATE + 30, 'activa', now()
               FROM plan_suscripcion WHERE codigo = :p""",
            e=empresa_id, p=plan_codigo,
        )
        ciudad = self.valor("SELECT id FROM ciudad ORDER BY id LIMIT 1")
        sucursal_id = self.valor(
            """INSERT INTO sucursal (ciudad_id, nombre, direccion, estado, empresa_id, fecha_creacion)
               VALUES (:c, :n, 'Calle de prueba 1', 'activa', :e, CURRENT_DATE) RETURNING id""",
            c=ciudad, n=f"Sucursal Pytest {sufijo}", e=empresa_id,
        )
        admin_id, headers = self.admin_de(empresa_id)
        return Tienda(empresa_id, sucursal_id, admin_id, headers)


@pytest.fixture()
def prueba():
    if not BASE_DISPONIBLE:
        pytest.skip("base de datos local no disponible")
    from fastapi.testclient import TestClient

    from app.core import rate_limit
    from app.main import app

    conexion = engine.connect()
    externa = conexion.begin()

    def get_db_de_prueba():
        db = SessionLocal(bind=conexion, join_transaction_mode="create_savepoint")
        # Cada peticion empieza sin el rol ni la empresa de la anterior.
        db.execute(text("RESET ROLE"))
        db.execute(text("SELECT set_config('arlani.empresa_scope', '', true)"))
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = get_db_de_prueba
    rate_limit.reiniciar_limites()
    try:
        yield Prueba(conexion, TestClient(app))
    finally:
        app.dependency_overrides.pop(get_db, None)
        externa.rollback()
        conexion.close()


@pytest.fixture()
def tienda_basica(prueba) -> Tienda:
    return prueba.tienda("basico")


@pytest.fixture()
def tienda_profesional(prueba) -> Tienda:
    return prueba.tienda("profesional")
