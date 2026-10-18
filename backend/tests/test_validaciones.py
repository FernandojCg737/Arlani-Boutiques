"""Pruebas unitarias (sin base de datos) de las validaciones que protegen
stock, reembolsos y tokens."""

import time

import pytest
from fastapi import HTTPException
from jose import jwt
from pydantic import ValidationError

from app.core import rate_limit
from app.core.config import settings
from app.core.security import create_ar_job_token, create_reset_token, decode_ar_job_token
from app.schemas.devoluciones import DevolucionCreate
from app.schemas.reservas import ReservaCreate
from app.schemas.ventas import VentaEditIn, VentaPresencialCreate

ITEM = {"producto_id": 1, "talla_id": 2, "color_id": 3, "cantidad": 2}


# ---------------------------------------------------------- items repetidos --


def test_venta_presencial_rechaza_combinacion_repetida():
    with pytest.raises(ValidationError, match="repetidos"):
        VentaPresencialCreate(cliente_id=1, sucursal_id=1, items=[ITEM, ITEM])


def test_venta_presencial_acepta_combinaciones_distintas():
    otro = {**ITEM, "color_id": 99}
    venta = VentaPresencialCreate(cliente_id=1, sucursal_id=1, items=[ITEM, otro])
    assert len(venta.items) == 2


def test_editar_venta_rechaza_combinacion_repetida():
    with pytest.raises(ValidationError, match="repetidos"):
        VentaEditIn(sucursal_id=1, items=[ITEM, ITEM], metodo_pago="efectivo", estado_pago="completado")


def test_reserva_rechaza_combinacion_repetida():
    with pytest.raises(ValidationError, match="repetidos"):
        ReservaCreate(sucursal_id=1, horario_atencion="2030-01-01T10:00:00", items=[ITEM, ITEM])


def test_devolucion_rechaza_item_repetido():
    with pytest.raises(ValidationError, match="una sola vez"):
        DevolucionCreate(
            motivo="otro",
            tipo="parcial",
            metodo_reembolso="efectivo",
            items=[{"item_linea_id": 5, "cantidad_devuelta": 1}, {"item_linea_id": 5, "cantidad_devuelta": 1}],
        )


def test_devolucion_valida():
    dev = DevolucionCreate(
        motivo="defecto",
        tipo="parcial",
        metodo_reembolso="mismo_medio",
        items=[{"item_linea_id": 5, "cantidad_devuelta": 1}, {"item_linea_id": 6, "cantidad_devuelta": 2}],
    )
    assert [i.item_linea_id for i in dev.items] == [5, 6]


# ------------------------------------------------------------- rate limit --


def test_rate_limit_bloquea_al_superar_el_maximo():
    rate_limit.reiniciar_limites()
    for _ in range(3):
        rate_limit.verificar_limite("test", "clave", maximo=3, segundos=60)
    with pytest.raises(HTTPException) as exc:
        rate_limit.verificar_limite("test", "clave", maximo=3, segundos=60)
    assert exc.value.status_code == 429


def test_rate_limit_es_por_clave_y_sin_distinguir_mayusculas():
    rate_limit.reiniciar_limites()
    rate_limit.verificar_limite("test", "A@x.com", maximo=1, segundos=60)
    with pytest.raises(HTTPException):
        rate_limit.verificar_limite("test", "a@X.com", maximo=1, segundos=60)
    rate_limit.verificar_limite("test", "otra@x.com", maximo=1, segundos=60)


def test_rate_limit_libera_al_vencer_la_ventana(monkeypatch):
    rate_limit.reiniciar_limites()
    ahora = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: ahora[0])
    rate_limit.verificar_limite("test", "k", maximo=1, segundos=10)
    ahora[0] += 11
    rate_limit.verificar_limite("test", "k", maximo=1, segundos=10)


# ----------------------------------------------------------------- tokens --


def test_reset_token_lleva_jti():
    token = create_reset_token("7", jti="abc123")
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["jti"] == "abc123" and payload["scope"] == "password_reset"


def test_ar_job_token_ida_y_vuelta():
    token = create_ar_job_token("job-real-42", usuario_id=9)
    assert decode_ar_job_token(token) == ("job-real-42", 9)


def test_ar_job_token_manipulado_o_ajeno_no_sirve():
    token = create_ar_job_token("job-real-42", usuario_id=9)
    assert decode_ar_job_token(token[:-2] + "xx") is None
    assert decode_ar_job_token("job-real-42") is None
    # un token valido pero de otro scope (ej. reset) tampoco
    assert decode_ar_job_token(create_reset_token("9", jti="j")) is None


def test_ar_job_token_vencido():
    token = create_ar_job_token("job", usuario_id=1, minutes=-1)
    time.sleep(0.01)
    assert decode_ar_job_token(token) is None
