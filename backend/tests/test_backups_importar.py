"""CU21: importar un backup desde un ZIP descargado.

El restaurador escribe las filas del ZIP tal cual, asi que importar solo
acepta ZIP firmados por este servidor y sin cambios, y una tienda solo puede
importar los backups de su propia tienda.
"""

import hashlib
import io
import json
import zipfile

import pytest
from sqlalchemy import text

from app.core import backups as motor
from app.db.session import engine

API = "/api/v1/backups"


def _version_actual() -> str:
    with engine.connect() as c:
        return c.execute(text("SELECT version_num FROM alembic_version")).scalar()


def zip_backup(empresa_id, alcance="tienda", secciones=("catalogo", "inventario"), version=None,
               firmado=True, cambiar_meta=None, cambiar_datos=False, imagen_extra=False) -> bytes:
    """Un ZIP con la misma forma que arma generar_backup."""
    datos = {"categoria": [{"id": 1, "nombre": "Vestidos", "empresa_id": empresa_id}]}
    datos_json = json.dumps(datos, ensure_ascii=False).encode()
    imagen = b"\x89PNG imagen de prueba"
    meta = {
        "backup_id": 999, "alcance": alcance, "empresa_id": empresa_id, "secciones": sorted(secciones),
        "creado_en": "2026-11-01T12:00:00", "version_base": version or _version_actual(),
        "conteos": {"categoria": 1}, "datos_sha256": hashlib.sha256(datos_json).hexdigest(),
        "imagenes_sha256": {"productos/a.png": hashlib.sha256(imagen).hexdigest()},
    }
    if firmado:
        meta["firma"] = motor.firmar(meta)
    if cambiar_meta:
        meta.update(cambiar_meta)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("datos.json", datos_json + (b" " if cambiar_datos else b""))
        z.writestr("imagenes/productos/a.png", imagen)
        if imagen_extra:
            z.writestr("imagenes/productos/b.svg", b"<svg onload='alert(1)'/>")
        z.writestr("meta.json", json.dumps(meta))
    return buffer.getvalue()


# ------------------------------------------------------- validacion del ZIP


def test_zip_firmado_de_la_tienda_se_acepta():
    meta, secciones = motor.leer_importacion(zip_backup(7), 7)
    assert meta["backup_id"] == 999
    assert secciones == ["catalogo", "inventario"]


@pytest.mark.parametrize(
    "zip_args, motivo",
    [
        ({"firmado": False}, "firma"),                                  # backups de antes (sin firma)
        ({"cambiar_meta": {"empresa_id": 8}}, "firma"),                 # se cambio la tienda a mano
        ({"cambiar_datos": True}, "modificados"),                       # se edito datos.json
        ({"imagen_extra": True}, "imagen"),                             # se agrego una imagen
    ],
)
def test_zip_modificado_se_rechaza(zip_args, motivo):
    with pytest.raises(motor.ImportacionInvalida, match=motivo):
        motor.leer_importacion(zip_backup(7, **zip_args), 7)


def test_backup_de_otra_tienda_se_rechaza():
    with pytest.raises(motor.ImportacionInvalida, match="otra tienda"):
        motor.leer_importacion(zip_backup(8), 7)


def test_backup_del_sistema_no_entra_en_una_tienda_y_al_reves():
    with pytest.raises(motor.ImportacionInvalida, match="otra tienda"):
        motor.leer_importacion(zip_backup(None, alcance="sistema"), 7)
    with pytest.raises(motor.ImportacionInvalida, match="de una tienda"):
        motor.leer_importacion(zip_backup(7), None)
    _, secciones = motor.leer_importacion(zip_backup(None, alcance="sistema", secciones=("plataforma", "catalogo")), None)
    assert secciones == ["catalogo", "plataforma"]


def test_version_mas_nueva_se_rechaza():
    with pytest.raises(motor.ImportacionInvalida, match="más nueva"):
        motor.leer_importacion(zip_backup(7, version="ffffffffffff"), 7)


def test_archivo_que_no_es_backup():
    with pytest.raises(motor.ImportacionInvalida, match="ZIP válido"):
        motor.leer_importacion(b"no soy un zip", 7)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("hola.txt", "x")
    with pytest.raises(motor.ImportacionInvalida, match="no es un backup"):
        motor.leer_importacion(buffer.getvalue(), 7)


# ------------------------------------------------------------- endpoint


@pytest.fixture()
def sin_almacenamiento(monkeypatch):
    """El ZIP no se sube a Supabase durante la prueba."""
    subidos = []
    monkeypatch.setattr(motor, "_asegurar_bucket", lambda: None)
    monkeypatch.setattr(motor, "_subir", lambda ruta, datos, tipo, bucket=motor.BUCKET: subidos.append(ruta))
    return subidos


def _subir(prueba, headers, contenido, empresa_id=None):
    params = {"empresa_id": empresa_id} if empresa_id else None
    return prueba.client.post(f"{API}/importar", headers=headers, params=params,
                              files={"archivo": ("backup.zip", contenido, "application/zip")})


def test_tienda_importa_su_backup_y_queda_listo_para_restaurar(prueba, tienda_basica, sin_almacenamiento):
    r = _subir(prueba, tienda_basica.headers, zip_backup(tienda_basica.empresa_id))
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["origen"] == "importado" and b["estado"] == "completado"
    assert b["secciones"] == ["catalogo", "inventario"]
    assert len(sin_almacenamiento) == 1 and sin_almacenamiento[0].startswith(f"tiendas/{tienda_basica.empresa_id}/importado-")
    fila = prueba.sql("SELECT empresa_id, archivos FROM backup WHERE id = :i", i=b["id"]).first()
    assert fila.empresa_id == tienda_basica.empresa_id and fila.archivos == sin_almacenamiento
    assert prueba.valor("SELECT count(*) FROM bitacora WHERE accion = 'IMPORTAR' AND entidad_id = :i", i=b["id"]) == 1


def test_tienda_no_puede_importar_el_backup_de_otra(prueba, tienda_basica, tienda_profesional, sin_almacenamiento):
    antes = prueba.valor("SELECT count(*) FROM backup")
    r = _subir(prueba, tienda_basica.headers, zip_backup(tienda_profesional.empresa_id))
    assert r.status_code == 422 and "otra tienda" in r.json()["detail"]
    assert prueba.valor("SELECT count(*) FROM backup") == antes
    assert sin_almacenamiento == []


def test_zip_editado_no_se_importa(prueba, tienda_basica, sin_almacenamiento):
    r = _subir(prueba, tienda_basica.headers, zip_backup(tienda_basica.empresa_id, cambiar_datos=True))
    assert r.status_code == 422
    assert sin_almacenamiento == []


def test_superadmin_importa_el_backup_de_una_tienda_eligiendola(prueba, tienda_basica, sin_almacenamiento):
    headers = prueba.superadmin()
    contenido = zip_backup(tienda_basica.empresa_id)
    # Sin elegir la tienda (sistema completo) no se acepta un backup de tienda.
    assert _subir(prueba, headers, contenido).status_code == 422
    r = _subir(prueba, headers, contenido, empresa_id=tienda_basica.empresa_id)
    assert r.status_code == 201, r.text
    assert r.json()["origen"] == "importado"
