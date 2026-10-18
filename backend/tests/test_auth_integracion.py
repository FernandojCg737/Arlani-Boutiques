"""Pruebas de integracion del flujo de autenticacion contra la base local
(la de docker compose). El envio de correos se intercepta: no sale ningun
correo real. Si la base no esta disponible, se saltean.

Correr dentro del contenedor:  docker compose exec backend pytest"""

import uuid

import pytest
from sqlalchemy import text

from app.core import rate_limit
from app.db.session import SessionLocal

try:
    with SessionLocal() as _db:
        _db.execute(text("SELECT 1"))
    BASE_DISPONIBLE = True
except Exception:
    BASE_DISPONIBLE = False

pytestmark = pytest.mark.skipif(not BASE_DISPONIBLE, reason="base de datos local no disponible")

API = "/api/v1"
PASSWORD = "Prueba#2026x"


@pytest.fixture()
def correos(monkeypatch):
    """Captura los correos en vez de enviarlos."""
    enviados: list[dict] = []

    def falso_send_email(to, subject, html_body):
        enviados.append({"to": to, "subject": subject, "html": html_body})

    import app.api.v1.endpoints.auth as auth_endpoints

    monkeypatch.setattr(auth_endpoints, "send_email", falso_send_email)
    return enviados


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    rate_limit.reiniciar_limites()
    return TestClient(app)


@pytest.fixture()
def cliente_nuevo(client, correos):
    email = f"pytest_{uuid.uuid4().hex[:10]}@example.com"
    r = client.post(f"{API}/auth/register", json={"nombre": "Pytest <b>Cliente</b>", "email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    yield email
    # Limpieza: la cuenta de prueba queda inactiva (no se borra porque
    # sp_crear_cliente crea filas relacionadas).
    with SessionLocal() as db:
        db.execute(text("UPDATE usuario SET estado='inactivo', session_id=NULL WHERE email=:e"), {"e": email})
        db.commit()


def _ultimo_codigo(correos, email):
    import re

    for c in reversed(correos):
        if c["to"] == email and "verificacion" in c["subject"].lower():
            return re.search(r"<h2>(\d{6})</h2>", c["html"]).group(1)
    return None


def test_bienvenida_sin_contrasena_y_con_nombre_escapado(cliente_nuevo, correos):
    bienvenida = next(c for c in correos if c["to"] == cliente_nuevo)
    assert PASSWORD not in bienvenida["html"]
    assert "&lt;b&gt;" in bienvenida["html"]


def test_forgot_password_no_revela_si_la_cuenta_existe(client, cliente_nuevo, correos):
    inexistente = client.post(f"{API}/auth/forgot-password", json={"email": "nadie@example.com"})
    existente = client.post(f"{API}/auth/forgot-password", json={"email": cliente_nuevo})
    assert inexistente.status_code == existente.status_code == 200
    assert inexistente.json() == existente.json()
    assert _ultimo_codigo(correos, cliente_nuevo) is not None
    assert not any(c["to"] == "nadie@example.com" for c in correos)


def test_codigo_se_invalida_tras_5_intentos_fallidos(client, cliente_nuevo, correos):
    client.post(f"{API}/auth/forgot-password", json={"email": cliente_nuevo})
    codigo = _ultimo_codigo(correos, cliente_nuevo)
    malo = "000000" if codigo != "000000" else "111111"
    for _ in range(5):
        assert client.post(f"{API}/auth/verify-reset-code", json={"email": cliente_nuevo, "code": malo}).status_code == 400
    r = client.post(f"{API}/auth/verify-reset-code", json={"email": cliente_nuevo, "code": codigo})
    assert r.status_code == 400


def test_reset_token_es_de_un_solo_uso(client, cliente_nuevo, correos):
    client.post(f"{API}/auth/forgot-password", json={"email": cliente_nuevo})
    codigo = _ultimo_codigo(correos, cliente_nuevo)
    r = client.post(f"{API}/auth/verify-reset-code", json={"email": cliente_nuevo, "code": codigo})
    assert r.status_code == 200, r.text
    reset_token = r.json()["reset_token"]

    assert client.post(f"{API}/auth/login-with-reset-code", json={"reset_token": reset_token}).status_code == 200
    r = client.post(f"{API}/auth/reset-password", json={"reset_token": reset_token, "new_password": "Otra#Clave99"})
    assert r.status_code == 400

    # El codigo tampoco se puede volver a usar
    r = client.post(f"{API}/auth/verify-reset-code", json={"email": cliente_nuevo, "code": codigo})
    assert r.status_code == 400


def test_login_limitado_por_cuenta(client):
    email = f"victima_{uuid.uuid4().hex[:6]}@example.com"
    codigos = [client.post(f"{API}/auth/login", json={"email": email, "password": "x"}).status_code for _ in range(11)]
    assert codigos[:10] == [401] * 10
    assert codigos[10] == 429
