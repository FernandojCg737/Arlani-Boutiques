"""Pruebas de integracion de las reglas criticas del 2do parcial, contra la
API real y PostgreSQL (todo se deshace al final, ver conftest.py):

- Aislamiento multitenant (9.6, RNF02): la Empresa B no ve, no modifica ni
  borra datos de la Empresa A, y la base lo impide aunque se salte la API.
- Planes (9.4, 9.5): limite de sucursales, configurable desde el backend, y
  reportes con IA solo en el plan Profesional.
- Ventas offline (Desafio IV, RNF04, RNF05, RNF06): la venta sincronizada
  descuenta stock con su movimiento de inventario, el reenvio del mismo
  uuid no duplica, sin stock queda en conflicto (sin perderse) y no se puede
  sincronizar en una sucursal de otra tienda.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

API = "/api/v1"

NUEVA_SUCURSAL = {
    "nombre": "Sucursal extra", "ciudad_nombre": "Santa Cruz de la Sierra", "departamento": "Santa Cruz",
    "direccion": "Av. de prueba 123",
}


# ------------------------------------------------------- aislamiento por tenant


def test_una_tienda_no_ve_las_sucursales_de_otra(prueba, tienda_basica, tienda_profesional):
    r = prueba.client.get(f"{API}/sucursales", headers=tienda_profesional.headers)
    assert r.status_code == 200, r.text
    ids = {s["id"] for s in r.json()}
    assert tienda_profesional.sucursal_id in ids
    assert tienda_basica.sucursal_id not in ids


def test_una_tienda_no_puede_modificar_ni_borrar_datos_de_otra(prueba, tienda_basica, tienda_profesional):
    ajena = tienda_basica.sucursal_id
    cambio = {**NUEVA_SUCURSAL, "nombre": "Hackeada", "estado": "inactiva"}
    r = prueba.client.put(f"{API}/sucursales/{ajena}", json=cambio, headers=tienda_profesional.headers)
    assert r.status_code in (403, 404), r.text
    r = prueba.client.delete(f"{API}/sucursales/{ajena}", headers=tienda_profesional.headers)
    assert r.status_code in (403, 404), r.text
    fila = prueba.sql("SELECT nombre, estado FROM sucursal WHERE id = :s", s=ajena).one()
    assert fila.nombre != "Hackeada" and fila.estado == "activa"


def test_la_base_aisla_las_empresas_aunque_se_salte_la_api(prueba, tienda_basica, tienda_profesional):
    # Row Level Security: con el rol de una tienda, las filas de otra no existen.
    prueba.sql("SELECT set_config('arlani.empresa_scope', :e, true)", e=str(tienda_profesional.empresa_id))
    prueba.conexion.exec_driver_sql("SET LOCAL ROLE arlani_tenant")
    vistas = prueba.conexion.execute(
        text("SELECT count(*) FROM sucursal WHERE id IN (:a, :b)"),
        {"a": tienda_basica.sucursal_id, "b": tienda_profesional.sucursal_id},
    ).scalar()
    assert vistas == 1


# ----------------------------------------------------------------- planes (CU10)


def _cuantas_sucursales(prueba, empresa_id: int) -> int:
    return prueba.valor("SELECT count(*) FROM sucursal WHERE empresa_id = :e AND estado = 'activa'", e=empresa_id)


def test_plan_basico_permite_hasta_2_sucursales(prueba, tienda_basica):
    h = tienda_basica.headers
    r = prueba.client.post(f"{API}/sucursales", json=NUEVA_SUCURSAL, headers=h)
    assert r.status_code == 201, r.text
    assert _cuantas_sucursales(prueba, tienda_basica.empresa_id) == 2
    r = prueba.client.post(f"{API}/sucursales", json={**NUEVA_SUCURSAL, "nombre": "Sucursal de mas"}, headers=h)
    assert r.status_code in (400, 402, 403, 409, 422), r.text
    assert _cuantas_sucursales(prueba, tienda_basica.empresa_id) == 2


def test_limite_de_sucursales_se_configura_desde_el_backend(prueba, tienda_basica):
    # El limite sale de plan_suscripcion (no esta fijo en el codigo): con 1, ya no entra otra.
    prueba.sql("UPDATE plan_suscripcion SET max_sucursales = 1 WHERE codigo = 'basico'")
    r = prueba.client.post(f"{API}/sucursales", json=NUEVA_SUCURSAL, headers=tienda_basica.headers)
    assert r.status_code in (400, 402, 403, 409, 422), r.text
    assert _cuantas_sucursales(prueba, tienda_basica.empresa_id) == 1


def test_plan_profesional_permite_mas_sucursales(prueba, tienda_profesional):
    h = tienda_profesional.headers
    for i in range(3):
        r = prueba.client.post(f"{API}/sucursales", json={**NUEVA_SUCURSAL, "nombre": f"Sucursal {i}"}, headers=h)
        assert r.status_code == 201, r.text
    assert _cuantas_sucursales(prueba, tienda_profesional.empresa_id) == 4


def test_reportes_con_ia_solo_en_plan_profesional(prueba, tienda_basica, tienda_profesional):
    basico = prueba.client.get(f"{API}/reportes-voz/estado", headers=tienda_basica.headers)
    profesional = prueba.client.get(f"{API}/reportes-voz/estado", headers=tienda_profesional.headers)
    assert basico.status_code == profesional.status_code == 200
    assert basico.json()["disponible"] is False
    assert profesional.json()["disponible"] is True
    # Y el backend lo exige al generar, no solo lo oculta en la pantalla.
    r = prueba.client.post(f"{API}/reportes-voz", json={"texto": "ventas por sucursal"}, headers=tienda_basica.headers)
    assert r.status_code == 403, r.text


# --------------------------------------------------------- ventas offline (CU12)


@pytest.fixture()
def stock(prueba):
    """Una variante con stock en una sucursal de una tienda que tiene operacion
    offline, y un administrador de prueba de esa tienda."""
    fila = prueba.sql(
        """SELECT i.id AS inventario_id, i.sucursal_id, i.producto_id, i.talla_id, i.color_id, i.cantidad,
                  s.empresa_id, pr.precio
           FROM inventario i
           JOIN sucursal s ON s.id = i.sucursal_id AND s.estado = 'activa'
           JOIN producto pr ON pr.id = i.producto_id AND pr.estado = 'activo'
           JOIN suscripcion su ON su.empresa_id = s.empresa_id AND su.estado = 'activa'
           JOIN plan_suscripcion pl ON pl.id = su.plan_id AND pl.operacion_offline
           WHERE i.cantidad BETWEEN 2 AND 90 AND fn_empresa_operativa(s.empresa_id)
           ORDER BY i.id LIMIT 1"""
    ).mappings().first()
    if fila is None:
        pytest.skip("no hay inventario con stock en una tienda con operacion offline")
    _, headers = prueba.admin_de(fila["empresa_id"])
    return {**fila, "headers": headers}


def _venta(stock, cantidad: int, uuid_op: str | None = None) -> dict:
    return {
        "uuid": uuid_op or str(uuid.uuid4()), "tipo": "venta", "sucursal_id": stock["sucursal_id"],
        "registrada_en": datetime.now(timezone.utc).isoformat(), "factura_nombre": "Pytest",
        "items": [{"producto_id": stock["producto_id"], "talla_id": stock["talla_id"], "color_id": stock["color_id"],
                   "cantidad": cantidad, "precio": str(stock["precio"])}],
    }


def _stock_actual(prueba, stock) -> int:
    return prueba.valor("SELECT cantidad FROM inventario WHERE id = :i", i=stock["inventario_id"])


def test_venta_offline_confirmada_descuenta_stock_con_su_movimiento(prueba, stock):
    movimientos = prueba.valor("SELECT count(*) FROM movimiento_inventario WHERE inventario_id = :i", i=stock["inventario_id"])
    r = prueba.client.post(f"{API}/offline/sincronizar", json={"operaciones": [_venta(stock, 1)]}, headers=stock["headers"])
    assert r.status_code == 200, r.text
    resultado = r.json()[0]
    assert resultado["estado"] == "confirmada", resultado
    assert resultado["venta_id"]
    assert _stock_actual(prueba, stock) == stock["cantidad"] - 1
    assert prueba.valor(
        "SELECT count(*) FROM movimiento_inventario WHERE inventario_id = :i", i=stock["inventario_id"]
    ) == movimientos + 1
    assert prueba.valor("SELECT origen FROM venta WHERE id = :v", v=resultado["venta_id"]) == "offline"


def test_reenviar_la_misma_operacion_no_duplica_la_venta(prueba, stock):
    op = _venta(stock, 1)
    primero = prueba.client.post(f"{API}/offline/sincronizar", json={"operaciones": [op]}, headers=stock["headers"]).json()[0]
    segundo = prueba.client.post(f"{API}/offline/sincronizar", json={"operaciones": [op]}, headers=stock["headers"]).json()[0]
    assert primero["estado"] == segundo["estado"] == "confirmada"
    assert primero["venta_id"] == segundo["venta_id"]
    assert _stock_actual(prueba, stock) == stock["cantidad"] - 1
    assert prueba.valor("SELECT count(*) FROM operacion_offline WHERE uuid = :u", u=op["uuid"]) == 1
    assert prueba.valor("SELECT intentos FROM operacion_offline WHERE uuid = :u", u=op["uuid"]) >= 1


def test_venta_sin_stock_suficiente_queda_en_conflicto_y_no_se_pierde(prueba, stock):
    op = _venta(stock, stock["cantidad"] + 1)
    r = prueba.client.post(f"{API}/offline/sincronizar", json={"operaciones": [op]}, headers=stock["headers"])
    resultado = r.json()[0]
    assert resultado["estado"] == "conflicto", resultado
    assert resultado["venta_id"] is None
    assert _stock_actual(prueba, stock) == stock["cantidad"]
    guardada = prueba.sql("SELECT estado, conflicto FROM operacion_offline WHERE uuid = :u", u=op["uuid"]).one()
    assert guardada.estado == "conflicto" and guardada.conflicto


def test_no_se_sincroniza_una_venta_en_la_sucursal_de_otra_tienda(prueba, stock, tienda_profesional):
    if tienda_profesional.empresa_id == stock["empresa_id"]:
        pytest.skip("misma empresa")
    r = prueba.client.post(f"{API}/offline/sincronizar", json={"operaciones": [_venta(stock, 1)]}, headers=tienda_profesional.headers)
    assert r.status_code == 200, r.text
    assert r.json()[0]["estado"] == "rechazada"
    assert _stock_actual(prueba, stock) == stock["cantidad"]
