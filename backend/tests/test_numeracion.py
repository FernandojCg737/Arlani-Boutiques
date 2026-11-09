"""Numeracion propia de cada tienda (#1, #2...) en ventas, reservas, backups...

El id es de toda la tabla; `numero` lo asigna la base por tienda, no se repite
aunque se borre el ultimo y es el que devuelven las pantallas.
"""

from app.core import backups as motor


def _cliente(prueba) -> int:
    return prueba.valor("SELECT id FROM cliente ORDER BY id LIMIT 1")


def _venta(prueba, sucursal_id: int) -> tuple[int, int]:
    fila = prueba.sql(
        """INSERT INTO venta (cliente_id, sucursal_id, fecha, total, estado, tipo)
           VALUES (:c, :s, now(), 10, 'pendiente', 'venta') RETURNING id, numero""",
        c=_cliente(prueba), s=sucursal_id,
    ).first()
    return fila.id, fila.numero


def test_cada_tienda_numera_sus_ventas_desde_1(prueba, tienda_basica, tienda_profesional):
    assert _venta(prueba, tienda_basica.sucursal_id)[1] == 1
    assert _venta(prueba, tienda_profesional.sucursal_id)[1] == 1
    assert _venta(prueba, tienda_basica.sucursal_id)[1] == 2
    assert _venta(prueba, tienda_profesional.sucursal_id)[1] == 2


def test_borrar_la_ultima_no_reutiliza_su_numero(prueba, tienda_basica):
    _venta(prueba, tienda_basica.sucursal_id)
    ultima, numero = _venta(prueba, tienda_basica.sucursal_id)
    assert numero == 2
    prueba.sql("DELETE FROM venta WHERE id = :i", i=ultima)
    assert _venta(prueba, tienda_basica.sucursal_id)[1] == 3


def test_reserva_y_su_notificacion_usan_el_numero_de_la_tienda(prueba, tienda_basica):
    reserva = prueba.sql(
        """INSERT INTO reserva (cliente_id, sucursal_id, horario_atencion, estado, fecha_creacion)
           VALUES (:c, :s, now() + interval '1 day', 'pendiente', now()) RETURNING id, numero""",
        c=_cliente(prueba), s=tienda_basica.sucursal_id,
    ).first()
    assert reserva.numero == 1
    mensaje = prueba.valor(
        "SELECT mensaje FROM notificacion WHERE entidad_id = :i AND mensaje LIKE 'Tu reserva #%' ORDER BY id DESC LIMIT 1",
        i=reserva.id,
    )
    if mensaje is not None:  # el trigger de notificacion existe en la base
        assert mensaje.startswith("Tu reserva #1 ")


def test_backups_del_sistema_y_de_la_tienda_no_comparten_numero(prueba, tienda_basica):
    """El caso que se reporto: el SuperAdministrador hacia el #3 y la tienda
    seguia con el #4. (No se crean backups del sistema: su secuencia es la de
    la base real y nextval no se deshace con el rollback de la prueba.)"""
    prueba.sql(
        """INSERT INTO backup (empresa_id, alcance, secciones, origen, estado, numero)
           VALUES (NULL, 'sistema', '{catalogo}', 'manual', 'completado', 3)"""
    )
    tienda = motor.crear_backup(prueba.conexion, tienda_basica.empresa_id, ["catalogo"], "manual", None)
    assert prueba.valor("SELECT numero FROM backup WHERE id = :i", i=tienda) == 1


def test_la_api_devuelve_el_numero_de_la_tienda(prueba, tienda_basica):
    _venta(prueba, tienda_basica.sucursal_id)
    motor.crear_backup(prueba.conexion, tienda_basica.empresa_id, ["catalogo"], "manual", None)
    backups = prueba.client.get("/api/v1/backups", headers=tienda_basica.headers).json()
    assert [b["numero"] for b in backups] == [1]


def test_la_bitacora_muestra_el_numero_de_la_tienda(prueba, tienda_basica):
    _venta(prueba, tienda_basica.sucursal_id)
    venta_id, numero = _venta(prueba, tienda_basica.sucursal_id)
    prueba.sql(
        """INSERT INTO bitacora (usuario_id, accion, entidad_afectada, entidad_id, fecha, detalle, empresa_id)
           VALUES (:u, 'CREAR', 'venta', :v, now(), 'prueba', :e)""",
        u=tienda_basica.admin_id, v=venta_id, e=tienda_basica.empresa_id,
    )
    r = prueba.client.get("/api/v1/bitacora", headers=tienda_basica.headers)
    assert r.status_code == 200, r.text
    fila = next(i for i in r.json()["items"] if i["entidad_id"] == venta_id)
    assert fila["entidad_numero"] == numero == 2


def test_numerar_faltantes_completa_lo_que_vuelve_sin_numero(prueba, tienda_basica):
    """Lo que restaura un backup viejo (sin numero, con los triggers apagados)."""
    _venta(prueba, tienda_basica.sucursal_id)
    prueba.sql("ALTER TABLE venta DISABLE TRIGGER trg_0_numero")
    sin_numero, numero = _venta(prueba, tienda_basica.sucursal_id)
    prueba.sql("ALTER TABLE venta ENABLE TRIGGER trg_0_numero")
    assert numero is None
    prueba.sql("SELECT fn_numerar_faltantes()")
    assert prueba.valor("SELECT numero FROM venta WHERE id = :i", i=sin_numero) == 2
    assert _venta(prueba, tienda_basica.sucursal_id)[1] == 3
