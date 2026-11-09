"""CU21 Gestionar backups y restauracion: el motor.

Un backup es un ZIP en el bucket privado "backups" de Supabase Storage con:
- meta.json: de que es (tienda o sistema), secciones, fecha, version de la base;
- datos.json: las filas de cada tabla (clave logica -> lista de filas);
- imagenes/<ruta>: los archivos de las imagenes que usan esas filas (productos,
  logo, prendas AR, comprobantes, fotos), tal cual estaban en el bucket publico.

Restaurar es un MERGE por secciones, nunca borra lo que existe hoy:
- "upsert": vuelve lo que se borro y lo modificado regresa a como estaba
  (catalogo, inventario, sucursales, ajustes);
- "agregar": solo vuelve lo que hoy falta; lo que existe no se toca (historial
  de ventas, pagos, cajas...; personal). Asi las ventas hechas despues del
  backup quedan intactas;
- "permisos": la matriz de permisos de la tienda queda como en el backup;
- "empresa": se actualizan los datos de la tienda (nombre, logo, colores...).
Si una fila que vuelve necesita otra que ya no existe (p. ej. una venta de un
producto borrado), esa tambien vuelve desde el backup. Los triggers del
sistema (comisiones, notificaciones, caja) se apagan mientras se restaura:
lo que vuelve es el registro, no se cobra ni se avisa de nuevo.

Importar: el ZIP descargado se puede volver a subir y queda como un backup
mas (origen "importado"). Como el restaurador escribe las filas tal cual, el
meta.json lleva una firma HMAC (clave del servidor) sobre el hash de
datos.json y de cada imagen: un ZIP editado a mano no se acepta, y una tienda
solo puede importar los backups de su propia tienda.
"""

import hashlib
import hmac
import io
import json
import logging
import zipfile
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

import requests
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.db.session import engine

logger = logging.getLogger(__name__)

BUCKET = "backups"
# El plan gratis de Supabase acepta archivos de hasta 50 MB.
TAMANO_PARTE = 45 * 1024 * 1024
# Bolivia no cambia de horario: UTC-4 todo el año.
BOLIVIA = timezone(timedelta(hours=-4))

SECCIONES = {
    "catalogo": "Catálogo",
    "inventario": "Inventario",
    "sucursales": "Sucursales",
    "ajustes": "Ajustes de la tienda",
    "personal": "Personal, roles y permisos",
    "historial": "Historial (ventas, reservas, pagos, cajas, devoluciones)",
}
SECCIONES_SISTEMA = {**SECCIONES, "plataforma": "Plataforma (planes, suscripciones, clientes)"}


class Tabla(NamedTuple):
    clave: str
    tabla: str
    # Seccion en un backup de tienda / del sistema. "referencia": se guarda
    # solo para devolver filas que otra necesita; "consulta": solo se guarda.
    seccion_tienda: str | None
    seccion_sistema: str
    filtro_tienda: str | None
    filtro_sistema: str
    modo: str


S = "(SELECT id FROM sucursal WHERE empresa_id = :e)"
V = f"(SELECT id FROM venta WHERE sucursal_id IN {S})"
R = f"(SELECT id FROM reserva WHERE sucursal_id IN {S})"
P = "(SELECT id FROM producto WHERE empresa_id = :e)"
U = "(SELECT id FROM usuario WHERE empresa_id = :e)"
CLIENTES = f"(SELECT cliente_id FROM venta WHERE sucursal_id IN {S} UNION SELECT cliente_id FROM reserva WHERE sucursal_id IN {S})"
ITEMS = (
    f"id IN (SELECT id FROM detalle_venta_presencial WHERE venta_presencial_id IN {V})"
    f" OR id IN (SELECT id FROM detalle_venta_digital WHERE venta_digital_id IN {V})"
    f" OR id IN (SELECT id FROM detalle_reserva WHERE reserva_id IN {R})"
)
PERSONAL = "('administrador', 'encargado_sucursal', 'cajero')"

# En orden de restauracion: cada tabla despues de las que necesita.
TABLAS = [
    Tabla("ciudad", "ciudad", "referencia", "plataforma", "TRUE", "TRUE", "upsert"),
    Tabla("talla", "talla", "referencia", "plataforma", "TRUE", "TRUE", "upsert"),
    Tabla("color", "color", "referencia", "plataforma", "TRUE", "TRUE", "upsert"),
    Tabla("rol", "rol", None, "plataforma", None, "TRUE", "agregar"),
    Tabla("permiso", "permiso", None, "plataforma", None, "TRUE", "agregar"),
    Tabla("rol_permiso", "rol_permiso", None, "plataforma", None, "TRUE", "agregar"),
    Tabla("plan_suscripcion", "plan_suscripcion", None, "plataforma", None, "TRUE", "upsert"),
    Tabla("empresa", "empresa", "ajustes", "ajustes", "id = :e", "TRUE", "empresa"),
    Tabla("suscripcion", "suscripcion", None, "plataforma", None, "TRUE", "agregar"),
    Tabla("pago_suscripcion", "pago_suscripcion", None, "plataforma", None, "TRUE", "agregar"),
    Tabla("categoria_global", "categoria", "referencia", "plataforma", "empresa_id IS NULL", "empresa_id IS NULL", "agregar"),
    Tabla("sucursal", "sucursal", "sucursales", "sucursales", "empresa_id = :e", "TRUE", "upsert"),
    Tabla("configuracion_asistencia", "configuracion_asistencia", "ajustes", "ajustes", "empresa_id = :e", "TRUE", "upsert"),
    Tabla("metodo_pago_empresa", "metodo_pago_empresa", "ajustes", "ajustes", "empresa_id = :e", "TRUE", "upsert"),
    Tabla("usuario_superadmin", "usuario", None, "plataforma", None, "tipo = 'superadministrador'", "agregar"),
    Tabla("usuario_personal", "usuario", "personal", "personal",
          f"empresa_id = :e AND tipo IN {PERSONAL}", f"tipo IN {PERSONAL}", "agregar"),
    Tabla("empleado", "empleado", "personal", "personal", f"id IN {U}", "TRUE", "agregar"),
    Tabla("administrador", "administrador", "personal", "personal", f"id IN {U}", "TRUE", "agregar"),
    Tabla("superadministrador", "superadministrador", None, "plataforma", None, "TRUE", "agregar"),
    Tabla("encargado_sucursal", "encargado_sucursal", "personal", "personal", f"id IN {U}", "TRUE", "agregar"),
    Tabla("cajero", "cajero", "personal", "personal", f"id IN {U}", "TRUE", "agregar"),
    Tabla("empresa_rol_permiso", "empresa_rol_permiso", "personal", "personal", "empresa_id = :e", "TRUE", "permisos"),
    Tabla("usuario_proveedor", "usuario", "catalogo", "catalogo",
          "empresa_id = :e AND tipo = 'proveedor'", "tipo = 'proveedor'", "upsert"),
    Tabla("proveedor", "proveedor", "catalogo", "catalogo", f"id IN {U}", "TRUE", "upsert"),
    Tabla("categoria", "categoria", "catalogo", "catalogo", "empresa_id = :e", "empresa_id IS NOT NULL", "upsert"),
    Tabla("marca", "marca", "catalogo", "catalogo", "empresa_id = :e", "TRUE", "upsert"),
    Tabla("temporada", "temporada", "catalogo", "catalogo", "empresa_id = :e", "TRUE", "upsert"),
    Tabla("coleccion", "coleccion", "catalogo", "catalogo",
          "temporada_id IN (SELECT id FROM temporada WHERE empresa_id = :e)", "TRUE", "upsert"),
    Tabla("producto", "producto", "catalogo", "catalogo", "empresa_id = :e", "TRUE", "upsert"),
    Tabla("producto_imagen", "producto_imagen", "catalogo", "catalogo", f"producto_id IN {P}", "TRUE", "upsert"),
    Tabla("prenda_ar", "prenda_ar", "catalogo", "catalogo", f"producto_id IN {P}", "TRUE", "upsert"),
    Tabla("producto_relacionado", "producto_relacionado", "catalogo", "catalogo", f"producto_id IN {P}", "TRUE", "agregar"),
    Tabla("inventario", "inventario", "inventario", "inventario", f"sucursal_id IN {S}", "TRUE", "upsert"),
    Tabla("usuario_cliente", "usuario", "historial", "plataforma", f"id IN {CLIENTES}", "tipo = 'cliente'", "agregar"),
    Tabla("cliente", "cliente", "historial", "plataforma", f"id IN {CLIENTES}", "TRUE", "agregar"),
    Tabla("direccion_cliente", "direccion_cliente", None, "plataforma", None, "TRUE", "agregar"),
    Tabla("cliente_metodo_pago", "cliente_metodo_pago", None, "plataforma", None, "TRUE", "agregar"),
    Tabla("cliente_paypal_token_tienda", "cliente_paypal_token_tienda", None, "plataforma", None, "TRUE", "agregar"),
    Tabla("carrito", "carrito", "historial", "historial",
          f"id IN (SELECT carrito_id FROM venta_digital WHERE id IN {V})", "TRUE", "agregar"),
    Tabla("caja", "caja", "historial", "historial", "empresa_id = :e", "TRUE", "agregar"),
    Tabla("movimiento_caja", "movimiento_caja", "historial", "historial",
          "caja_id IN (SELECT id FROM caja WHERE empresa_id = :e)", "TRUE", "agregar"),
    Tabla("liquidacion_tienda", "liquidacion_tienda", "historial", "historial", "empresa_id = :e", "TRUE", "agregar"),
    Tabla("venta", "venta", "historial", "historial", f"sucursal_id IN {S}", "TRUE", "agregar"),
    Tabla("venta_presencial", "venta_presencial", "historial", "historial", f"id IN {V}", "TRUE", "agregar"),
    Tabla("venta_digital", "venta_digital", "historial", "historial", f"id IN {V}", "TRUE", "agregar"),
    Tabla("venta_envio", "venta_envio", "historial", "historial", f"venta_id IN {V}", "TRUE", "agregar"),
    Tabla("reserva", "reserva", "historial", "historial", f"sucursal_id IN {S}", "TRUE", "agregar"),
    Tabla("item_linea", "item_linea", "historial", "historial", ITEMS, "TRUE", "agregar"),
    Tabla("detalle_venta_presencial", "detalle_venta_presencial", "historial", "historial",
          f"venta_presencial_id IN {V}", "TRUE", "agregar"),
    Tabla("detalle_venta_digital", "detalle_venta_digital", "historial", "historial",
          f"venta_digital_id IN {V}", "TRUE", "agregar"),
    Tabla("detalle_reserva", "detalle_reserva", "historial", "historial", f"reserva_id IN {R}", "TRUE", "agregar"),
    Tabla("detalle_carrito", "detalle_carrito", None, "historial", None, "TRUE", "agregar"),
    Tabla("pago", "pago", "historial", "historial", f"venta_id IN {V}", "TRUE", "agregar"),
    Tabla("transaccion", "transaccion", "historial", "historial",
          f"pago_id IN (SELECT id FROM pago WHERE venta_id IN {V})", "TRUE", "agregar"),
    Tabla("devolucion", "devolucion", "historial", "historial", f"venta_id IN {V}", "TRUE", "agregar"),
    Tabla("detalle_devolucion", "detalle_devolucion", "historial", "historial",
          f"devolucion_id IN (SELECT id FROM devolucion WHERE venta_id IN {V})", "TRUE", "agregar"),
    Tabla("cambio_prenda", "cambio_prenda", "historial", "historial", f"venta_id IN {V}", "TRUE", "agregar"),
    Tabla("reposicion_prenda", "reposicion_prenda", "historial", "historial", f"sucursal_id IN {S}", "TRUE", "agregar"),
    Tabla("cuenta_tienda_movimiento", "cuenta_tienda_movimiento", "historial", "historial", "empresa_id = :e", "TRUE", "agregar"),
    Tabla("calificacion", "calificacion", "historial", "historial", f"venta_id IN {V}", "TRUE", "agregar"),
    Tabla("movimiento_inventario", "movimiento_inventario", "historial", "historial",
          f"inventario_id IN (SELECT id FROM inventario WHERE sucursal_id IN {S})", "TRUE", "agregar"),
    Tabla("marcado_asistencia", "marcado_asistencia", "historial", "historial", f"empleado_id IN {U}", "TRUE", "agregar"),
    Tabla("operacion_offline", "operacion_offline", "historial", "historial", "empresa_id = :e", "TRUE", "agregar"),
    Tabla("notificacion", "notificacion", None, "historial", None, "TRUE", "agregar"),
    Tabla("chatbot", "chatbot", None, "historial", None, "TRUE", "agregar"),
    Tabla("chatbot_mensaje", "chatbot_mensaje", None, "historial", None, "TRUE", "agregar"),
    Tabla("recomendacion", "recomendacion", None, "historial", None, "TRUE", "agregar"),
    Tabla("vista_producto", "vista_producto", None, "historial", None, "TRUE", "agregar"),
    Tabla("uso_ar_prenda", "uso_ar_prenda", None, "historial", None, "TRUE", "agregar"),
    Tabla("descarga_offline", "descarga_offline", None, "historial", None, "TRUE", "agregar"),
    Tabla("bitacora", "bitacora", "consulta", "consulta", "empresa_id = :e", "TRUE", "consulta"),
]

# Datos de la tienda que vuelven con "Ajustes" (no su estado ni su dueño).
CAMPOS_EMPRESA = ("nombre", "subdominio", "ciudad", "color_marca", "logo_url", "email_contacto", "razon_social",
                  "nit", "direccion_fiscal", "telefono", "publicos")
# Lo que no viaja en un backup: la sesion y los codigos de recuperacion.
CAMPOS_FUERA = {"usuario": ("session_id", "reset_code_hash", "reset_code_expires_at", "reset_token_jti")}
# Tablas cuyos triggers se apagan al restaurar (comisiones, notificaciones,
# caja, bitacora de altas): vuelve el registro, no se repiten sus efectos.
SIN_TRIGGERS = ("usuario", "venta", "pago", "reserva", "detalle_venta_digital", "detalle_venta_presencial",
                "devolucion", "detalle_carrito")
# empresa.propietario_id apunta a un usuario que se restaura despues.
DIFERIDAS = {("empresa", "propietario_id")}
# Columnas con imagenes del bucket publico.
COLUMNAS_IMAGEN = {
    "producto_imagen": ("url",), "prenda_ar": ("url",), "empresa": ("logo_url",), "metodo_pago_empresa": ("qr_url",),
    "pago": ("comprobante_url",), "cambio_prenda": ("comprobante_url",), "usuario": ("foto_url",),
    "marcado_asistencia": ("foto_url",),
}


def tablas_de(sistema: bool, secciones: set[str] | None = None) -> list[Tabla]:
    """Tablas que van en un backup de tienda o del sistema (con las de
    referencia), opcionalmente solo las de esas secciones."""
    salida = []
    for t in TABLAS:
        seccion = t.seccion_sistema if sistema else t.seccion_tienda
        if seccion is None:
            continue
        if secciones is not None and seccion not in secciones and seccion not in ("referencia", "consulta"):
            continue
        salida.append(t)
    return salida


def seccion_de(t: Tabla, sistema: bool) -> str | None:
    return t.seccion_sistema if sistema else t.seccion_tienda


# ==================================================================== bitacora


def registrar_bitacora(conn: Connection, usuario_id: int | None, accion: str, entidad: str, entidad_id: int | None,
                       detalle: str, empresa_id: int | None, ip: str | None = None, plataforma: str | None = "servidor") -> None:
    """CU08: deja constancia de cada backup y restauracion, con la tienda a la
    que pertenece (tambien cuando lo hace el SuperAdministrador o es
    automatico). Sin usuario (lo automatico), firma quien lo programo o, si ya
    no existe, el dueño de la tienda."""
    if usuario_id is None:
        usuario_id = conn.execute(
            text("""SELECT coalesce((SELECT propietario_id FROM empresa WHERE id = :e),
                                    (SELECT id FROM usuario WHERE tipo = 'superadministrador' ORDER BY id LIMIT 1))"""),
            {"e": empresa_id},
        ).scalar()
    if usuario_id is None:
        return
    conn.execute(
        text(
            """INSERT INTO bitacora (usuario_id, accion, entidad_afectada, entidad_id, detalle, ip_address, plataforma, empresa_id, fecha)
               VALUES (:u, :a, :en, :id, :d, :ip, :p, :e, now())"""
        ),
        {"u": usuario_id, "a": accion, "en": entidad, "id": entidad_id, "d": detalle[:1000], "ip": ip, "p": plataforma,
         "e": empresa_id},
    )


def _tamano(bytes_: int) -> str:
    return f"{bytes_ / 1024:.0f} KB" if bytes_ < 1024 * 1024 else f"{bytes_ / 1024 / 1024:.1f} MB"


_ORIGEN = {"manual": "Backup manual", "programado": "Backup programado", "antes_de_restaurar": "Backup automático antes de restaurar",
           "importado": "Backup importado"}


# ================================================================ almacenamiento


def _cabeceras(extra: dict | None = None) -> dict:
    return {"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}", "apikey": settings.SUPABASE_SERVICE_KEY,
            **(extra or {})}


def _prefijo_publico() -> str:
    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{settings.SUPABASE_STORAGE_BUCKET}/"


def _asegurar_bucket() -> None:
    """Crea el bucket privado la primera vez (si ya existe, Supabase responde
    400/409 y se sigue)."""
    requests.post(
        f"{settings.SUPABASE_URL}/storage/v1/bucket", headers=_cabeceras(),
        json={"id": BUCKET, "name": BUCKET, "public": False}, timeout=15,
    )


def _subir(ruta: str, datos: bytes, tipo: str, bucket: str = BUCKET) -> None:
    resp = requests.post(
        f"{settings.SUPABASE_URL}/storage/v1/object/{bucket}/{ruta}",
        headers=_cabeceras({"Content-Type": tipo, "x-upsert": "true"}), data=datos, timeout=120,
    )
    if not resp.ok:
        raise RuntimeError(f"No se pudo guardar {ruta} en el almacenamiento ({resp.status_code}).")


def descargar_archivos(archivos: list[str]) -> bytes:
    """El ZIP de un backup (une las partes si se guardo en varias)."""
    partes = []
    for ruta in archivos:
        resp = requests.get(f"{settings.SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}", headers=_cabeceras(), timeout=120)
        if not resp.ok:
            raise RuntimeError("El archivo del backup ya no está en el almacenamiento.")
        partes.append(resp.content)
    return b"".join(partes)


def borrar_archivos(archivos: list[str]) -> None:
    if archivos:
        requests.delete(
            f"{settings.SUPABASE_URL}/storage/v1/object/{BUCKET}", headers=_cabeceras(),
            json={"prefixes": archivos}, timeout=30,
        )


# ====================================================================== backup


def _exportar(conn: Connection, empresa_id: int | None, secciones: set[str]) -> dict[str, list[dict]]:
    sistema = empresa_id is None
    datos = {}
    for t in tablas_de(sistema, secciones):
        filtro = t.filtro_sistema if sistema else t.filtro_tienda
        filas = conn.execute(
            text(f"SELECT coalesce(json_agg(x), '[]'::json) FROM (SELECT * FROM {t.tabla} WHERE {filtro} ORDER BY 1) x"),
            {"e": empresa_id},
        ).scalar()
        for campo in CAMPOS_FUERA.get(t.tabla, ()):
            for f in filas:
                f[campo] = None
        datos[t.clave] = filas
    return datos


def _imagenes_de(datos: dict[str, list[dict]], claves: set[str] | None = None) -> set[str]:
    """Rutas (dentro del bucket publico) de las imagenes que usan las filas."""
    prefijo = _prefijo_publico()
    rutas = set()
    for t in TABLAS:
        if t.clave not in datos or (claves is not None and t.clave not in claves):
            continue
        for columna in COLUMNAS_IMAGEN.get(t.tabla, ()):
            for f in datos[t.clave]:
                url = f.get(columna)
                if isinstance(url, str) and url.startswith(prefijo):
                    rutas.add(url[len(prefijo):].split("?")[0])
    return rutas


def generar_backup(backup_id: int) -> None:
    """Arma el ZIP del backup (ya creado 'en_proceso') y lo guarda."""
    with engine.connect() as conn:
        fila = conn.execute(text("SELECT * FROM backup WHERE id = :i"), {"i": backup_id}).mappings().first()
        conn.commit()
    if fila is None:
        return
    try:
        secciones = set(fila["secciones"])
        with engine.connect() as conn:
            # Una sola foto consistente de toda la base.
            conn.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            datos = _exportar(conn, fila["empresa_id"], secciones)
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            conn.rollback()

        buffer = io.BytesIO()
        imagenes = 0
        hashes: dict[str, str] = {}
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
            datos_json = json.dumps(datos, ensure_ascii=False, default=str).encode()
            z.writestr("datos.json", datos_json)
            for ruta in sorted(_imagenes_de(datos)):
                resp = requests.get(_prefijo_publico() + ruta, timeout=30)
                if resp.ok:
                    # Las imagenes ya vienen comprimidas.
                    z.writestr(f"imagenes/{ruta}", resp.content, compress_type=zipfile.ZIP_STORED)
                    hashes[ruta] = hashlib.sha256(resp.content).hexdigest()
                    imagenes += 1
            meta = {
                "backup_id": backup_id, "numero": fila["numero"], "alcance": fila["alcance"], "empresa_id": fila["empresa_id"],
                "secciones": sorted(secciones), "creado_en": fila["creado_en"].isoformat(),
                "version_base": version, "conteos": {k: len(v) for k, v in datos.items()},
                # Para poder importarlo despues (ver leer_importacion).
                "datos_sha256": hashlib.sha256(datos_json).hexdigest(), "imagenes_sha256": hashes,
            }
            meta["firma"] = firmar(meta)
            z.writestr("meta.json", json.dumps(meta, ensure_ascii=False))
        contenido = buffer.getvalue()

        _asegurar_bucket()
        carpeta = f"tiendas/{fila['empresa_id']}" if fila["empresa_id"] else "sistema"
        base = f"{carpeta}/backup-{backup_id}-{fila['creado_en']:%Y%m%d-%H%M%S}.zip"
        partes = [contenido[i:i + TAMANO_PARTE] for i in range(0, len(contenido), TAMANO_PARTE)] or [b""]
        archivos = [base] if len(partes) == 1 else [f"{base}.parte{n + 1}" for n in range(len(partes))]
        for ruta, parte in zip(archivos, partes):
            _subir(ruta, parte, "application/zip")

        with engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE backup SET estado = 'completado', archivos = CAST(:a AS JSONB), tamano_bytes = :t,
                              conteos = CAST(:c AS JSONB), imagenes = :im, completado_en = now() WHERE id = :i"""
                ),
                {"a": json.dumps(archivos), "t": len(contenido), "c": json.dumps(meta["conteos"]), "im": imagenes,
                 "i": backup_id},
            )
            donde = "del sistema completo" if fila["empresa_id"] is None else "de la tienda"
            programa = conn.execute(
                text("SELECT nombre FROM backup_programacion WHERE id = :p"), {"p": fila["programacion_id"]}
            ).scalar() if fila["programacion_id"] else None
            registrar_bitacora(
                conn, fila["creado_por_id"], "COMPLETAR", "backup", backup_id,
                f"{_ORIGEN[fila['origen']]}{' «' + programa + '»' if programa else ''} #{fila['numero'] or backup_id} {donde} completado"
                f"{' (atrasado: el servidor estaba dormido)' if fila['atrasado'] else ''}: "
                f"{sum(meta['conteos'].values())} registros, {imagenes} imágenes, {_tamano(len(contenido))}. "
                f"Secciones: {', '.join(sorted(secciones))}.",
                fila["empresa_id"],
            )
    except Exception as exc:  # noqa: BLE001 - el error queda en el backup
        logger.exception("Backup %s fallo", backup_id)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE backup SET estado = 'fallido', error = :m, completado_en = now() WHERE id = :i"),
                {"m": str(exc)[:500], "i": backup_id},
            )
            registrar_bitacora(conn, fila["creado_por_id"], "FALLO", "backup", backup_id,
                               f"{_ORIGEN[fila['origen']]} #{fila['numero'] or backup_id} falló: {str(exc)[:300]}", fila["empresa_id"])


def crear_backup(conn: Connection, empresa_id: int | None, secciones: list[str], origen: str,
                 usuario_id: int | None, programacion_id: int | None = None, atrasado: bool = False) -> int:
    return conn.execute(
        text(
            """INSERT INTO backup (empresa_id, alcance, secciones, origen, programacion_id, atrasado, creado_por_id)
               VALUES (:e, :a, :s, :o, :p, :at, :u) RETURNING id"""
        ),
        {"e": empresa_id, "a": "sistema" if empresa_id is None else "tienda", "s": secciones, "o": origen,
         "p": programacion_id, "at": atrasado, "u": usuario_id},
    ).scalar_one()


# ==================================================================== importar

# Lo mas grande que se acepta subir (y descomprimido, por si es un ZIP bomba).
MAX_IMPORTAR = 300 * 1024 * 1024
MAX_DESCOMPRIMIDO = 1024 * 1024 * 1024


class ImportacionInvalida(ValueError):
    """El ZIP no se puede importar (el mensaje es para el usuario)."""


def _clave_firma() -> bytes:
    return hashlib.sha256(b"arlani-backup:" + settings.SECRET_KEY.encode()).digest()


def firmar(meta: dict) -> str:
    """HMAC-SHA256 del meta.json (sin la firma), con la clave del servidor."""
    cuerpo = json.dumps({k: v for k, v in meta.items() if k != "firma"}, sort_keys=True, ensure_ascii=False,
                        separators=(",", ":"))
    return hmac.new(_clave_firma(), cuerpo.encode(), hashlib.sha256).hexdigest()


def _versiones_conocidas() -> set[str] | None:
    """Revisiones de Alembic que conoce este backend (todas <= la actual)."""
    try:
        from alembic.script import ScriptDirectory

        carpeta = Path(__file__).resolve().parents[2] / "migrations"
        return {r.revision for r in ScriptDirectory(str(carpeta)).walk_revisions()}
    except Exception:  # noqa: BLE001 - sin la lista no se bloquea la importacion
        logger.exception("No se pudieron leer las migraciones")
        return None


def leer_importacion(contenido: bytes, empresa_id: int | None) -> tuple[dict, list[str]]:
    """Valida un ZIP subido y devuelve su meta.json y las secciones que trae.

    Se exige: que sea un backup de Arlani, que la firma y los hashes coincidan
    (nadie lo edito), que sea del mismo ambito (esa tienda o el sistema) y que
    no venga de una version de la base mas nueva que la actual."""
    try:
        z = zipfile.ZipFile(io.BytesIO(contenido))
    except zipfile.BadZipFile:
        raise ImportacionInvalida("El archivo no es un ZIP válido.")
    with z:
        if sum(i.file_size for i in z.infolist()) > MAX_DESCOMPRIMIDO:
            raise ImportacionInvalida("El ZIP es demasiado grande para importarlo.")
        nombres = set(z.namelist())
        if not {"meta.json", "datos.json"} <= nombres:
            raise ImportacionInvalida("Ese ZIP no es un backup de Arlani Boutiques (le falta meta.json o datos.json).")
        try:
            meta = json.loads(z.read("meta.json"))
        except ValueError:
            raise ImportacionInvalida("El meta.json del backup está dañado.")
        if not isinstance(meta, dict):
            raise ImportacionInvalida("El meta.json del backup está dañado.")
        firma = meta.get("firma")
        if not isinstance(firma, str) or not hmac.compare_digest(firma, firmar(meta)):
            raise ImportacionInvalida(
                "El backup no tiene una firma válida: fue modificado, es de otro servidor o se hizo antes de que "
                "existiera la importación. Solo se pueden importar los ZIP descargados de este sistema, sin cambios."
            )
        if hashlib.sha256(z.read("datos.json")).hexdigest() != meta.get("datos_sha256"):
            raise ImportacionInvalida("Los datos del backup fueron modificados: no se puede importar.")
        hashes = meta.get("imagenes_sha256") or {}
        for nombre in nombres:
            if nombre.startswith("imagenes/") and not nombre.endswith("/"):
                if hashes.get(nombre[len("imagenes/"):]) != hashlib.sha256(z.read(nombre)).hexdigest():
                    raise ImportacionInvalida("Una imagen del backup fue modificada o agregada: no se puede importar.")

    if empresa_id is None:
        if meta.get("alcance") != "sistema":
            raise ImportacionInvalida("Ese ZIP es el backup de una tienda: impórtalo eligiendo esa tienda.")
    elif meta.get("alcance") != "tienda" or meta.get("empresa_id") != empresa_id:
        raise ImportacionInvalida("Ese backup es de otra tienda o del sistema completo: aquí solo se importan los backups de esta tienda.")
    permitidas = SECCIONES if empresa_id is not None else SECCIONES_SISTEMA
    secciones = [s for s in permitidas if s in (meta.get("secciones") or [])]
    if not secciones:
        raise ImportacionInvalida("El backup no trae ninguna sección que se pueda restaurar.")
    conocidas = _versiones_conocidas()
    if conocidas is not None and meta.get("version_base") not in conocidas:
        raise ImportacionInvalida("El backup es de una versión del sistema más nueva que la actual: no se puede importar.")
    return meta, secciones


def importar_backup(conn: Connection, contenido: bytes, empresa_id: int | None, usuario_id: int) -> tuple[int, dict]:
    """Registra el ZIP subido como un backup completado (origen "importado") y
    lo guarda en el almacenamiento: desde ahi se restaura como cualquier otro.
    Lanza ImportacionInvalida si el ZIP no pasa las validaciones."""
    meta, secciones = leer_importacion(contenido, empresa_id)
    backup_id = crear_backup(conn, empresa_id, secciones, "importado", usuario_id)
    _asegurar_bucket()
    carpeta = f"tiendas/{empresa_id}" if empresa_id else "sistema"
    base = f"{carpeta}/importado-{backup_id}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.zip"
    partes = [contenido[i:i + TAMANO_PARTE] for i in range(0, len(contenido), TAMANO_PARTE)] or [b""]
    archivos = [base] if len(partes) == 1 else [f"{base}.parte{n + 1}" for n in range(len(partes))]
    try:
        for ruta, parte in zip(archivos, partes):
            _subir(ruta, parte, "application/zip")
    except Exception:
        borrar_archivos(archivos)
        raise
    conn.execute(
        text(
            """UPDATE backup SET estado = 'completado', archivos = CAST(:a AS JSONB), tamano_bytes = :t,
                      conteos = CAST(:c AS JSONB), imagenes = :im, completado_en = now() WHERE id = :i"""
        ),
        {"a": json.dumps(archivos), "t": len(contenido), "c": json.dumps(meta.get("conteos") or {}),
         "im": len(meta.get("imagenes_sha256") or {}), "i": backup_id},
    )
    return backup_id, meta


# ================================================================= restauracion


class _Restaurador:
    def __init__(self, conn: Connection, datos: dict[str, list[dict]], sistema: bool, empresa_id: int | None):
        self.conn = conn
        self.datos = datos
        self.sistema = sistema
        self.empresa_id = empresa_id
        self.resumen: dict[str, dict] = {}
        # Filas del backup por tabla fisica e id (para devolver las que faltan).
        self.por_id: dict[str, dict] = {}
        for t in TABLAS:
            for f in datos.get(t.clave, []):
                if "id" in f:
                    self.por_id.setdefault(t.tabla, {})[f["id"]] = f
        self.columnas: dict[str, list[str]] = {}
        self.pk: dict[str, list[str]] = {}
        self.fks: dict[str, list[tuple[str, str]]] = {}
        for tabla, columna in conn.execute(
            text("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public' ORDER BY ordinal_position")
        ):
            self.columnas.setdefault(tabla, []).append(columna)
        for tabla, pk in conn.execute(
            text(
                """SELECT tc.table_name, kcu.column_name FROM information_schema.table_constraints tc
                   JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
                   WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public' ORDER BY kcu.ordinal_position"""
            )
        ):
            self.pk.setdefault(tabla, []).append(pk)
        for tabla, columna, padre in conn.execute(
            text(
                """SELECT tc.table_name, kcu.column_name, ccu.table_name FROM information_schema.table_constraints tc
                   JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
                   JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
                   WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'"""
            )
        ):
            if (tabla, columna) not in DIFERIDAS and padre != tabla:
                self.fks.setdefault(tabla, []).append((columna, padre))
        self.diferidas: list[dict] = []

    def _nota(self, tabla: str, campo: str, n: int = 1) -> None:
        r = self.resumen.setdefault(tabla, {"volvieron": 0, "actualizadas": 0, "omitidas": 0})
        r[campo] += n

    def _existentes(self, tabla: str, ids: set) -> set:
        if not ids:
            return set()
        return set(self.conn.execute(text(f"SELECT id FROM {tabla} WHERE id = ANY(:i)"), {"i": list(ids)}).scalars())

    def _devolver_padres(self, tabla: str, filas: list[dict], visitadas: set[str]) -> None:
        """Si las filas apuntan a otras que hoy no existen, las devuelve primero."""
        for columna, padre in self.fks.get(tabla, []):
            ids = {f[columna] for f in filas if f.get(columna) is not None}
            faltan = ids - self._existentes(padre, ids)
            respaldo = self.por_id.get(padre, {})
            volver = [respaldo[i] for i in faltan if i in respaldo]
            if volver and padre not in visitadas:
                self._insertar(padre, volver, "agregar", visitadas | {tabla})

    def _sql(self, tabla: str, columnas: list[str], modo: str) -> str:
        lista = ", ".join(f'"{c}"' for c in columnas)
        pk = self.pk.get(tabla, ["id"])
        if modo == "upsert":
            cambios = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in columnas if c not in pk)
            conflicto = f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {cambios}" if cambios else "ON CONFLICT DO NOTHING"
        else:
            conflicto = "ON CONFLICT DO NOTHING"
        return (f"INSERT INTO {tabla} ({lista}) SELECT {lista} FROM jsonb_populate_recordset(NULL::{tabla}, CAST(:f AS JSONB)) "
                f"{conflicto} RETURNING (xmax = 0) AS nueva")

    def _insertar(self, tabla: str, filas: list[dict], modo: str, visitadas: set[str] | None = None) -> None:
        if not filas:
            return
        visitadas = (visitadas or set()) | {tabla}
        actuales = self.columnas.get(tabla, [])
        columnas = [c for c in actuales if c in filas[0]]
        # Columnas que apuntan a filas que vuelven despues: van en NULL y se
        # completan al final.
        diferidas = [c for (t, c) in DIFERIDAS if t == tabla and c in columnas]
        if diferidas:
            self.diferidas += [{"tabla": tabla, "fila": f, "columnas": diferidas} for f in filas]
            filas = [{**f, **{c: None for c in diferidas}} for f in filas]
        if "id" in columnas and modo == "agregar":
            hoy = self._existentes(tabla, {f["id"] for f in filas})
            filas = [f for f in filas if f["id"] not in hoy]
            if not filas:
                return
        self._devolver_padres(tabla, filas, visitadas)
        sql = text(self._sql(tabla, columnas, modo))
        try:
            with self.conn.begin_nested():
                resultado = self.conn.execute(sql, {"f": json.dumps(filas, default=str)}).scalars().all()
            self._nota(tabla, "volvieron", sum(1 for nueva in resultado if nueva))
            self._nota(tabla, "actualizadas", sum(1 for nueva in resultado if not nueva))
        except DBAPIError:
            # Alguna fila choca (p. ej. un correo que hoy usa otra cuenta): se
            # intenta una por una y se cuentan las que no pudieron volver.
            for f in filas:
                try:
                    with self.conn.begin_nested():
                        resultado = self.conn.execute(sql, {"f": json.dumps([f], default=str)}).scalars().all()
                    for nueva in resultado:
                        self._nota(tabla, "volvieron" if nueva else "actualizadas")
                except DBAPIError as exc:
                    self._nota(tabla, "omitidas")
                    self.resumen[tabla].setdefault("motivo", str(exc.orig).splitlines()[0][:200])

    def _empresa(self, filas: list[dict]) -> None:
        for f in filas:
            campos = [c for c in CAMPOS_EMPRESA if c in f and c in self.columnas["empresa"]]
            asignar = ", ".join(f'"{c}" = r."{c}"' for c in campos)
            try:
                with self.conn.begin_nested():
                    n = self.conn.execute(
                        text(f"UPDATE empresa e SET {asignar} FROM jsonb_populate_record(NULL::empresa, CAST(:f AS JSONB)) r "
                             "WHERE e.id = r.id"),
                        {"f": json.dumps(f, default=str)},
                    ).rowcount
                self._nota("empresa", "actualizadas", n)
            except DBAPIError as exc:
                self._nota("empresa", "omitidas")
                self.resumen["empresa"]["motivo"] = str(exc.orig).splitlines()[0][:200]

    def _permisos(self, filas: list[dict]) -> None:
        # Sin matriz en el backup no se toca la de hoy (no se deja a nadie sin permisos).
        if not filas:
            return
        empresas = {f["empresa_id"] for f in filas}
        self.conn.execute(text("DELETE FROM empresa_rol_permiso WHERE empresa_id = ANY(:e)"), {"e": list(empresas)})
        n = self.conn.execute(
            text(
                """INSERT INTO empresa_rol_permiso (empresa_id, rol_id, permiso_id)
                   SELECT r.empresa_id, r.rol_id, r.permiso_id
                   FROM jsonb_populate_recordset(NULL::empresa_rol_permiso, CAST(:f AS JSONB)) r
                   WHERE EXISTS (SELECT 1 FROM rol WHERE id = r.rol_id) AND EXISTS (SELECT 1 FROM permiso WHERE id = r.permiso_id)
                     AND EXISTS (SELECT 1 FROM empresa WHERE id = r.empresa_id)
                   ON CONFLICT DO NOTHING"""
            ),
            {"f": json.dumps(filas)},
        ).rowcount
        self._nota("empresa_rol_permiso", "actualizadas", n)

    def restaurar(self, secciones: set[str]) -> dict:
        for tabla in SIN_TRIGGERS:
            self.conn.execute(text(f"ALTER TABLE {tabla} DISABLE TRIGGER USER"))
        for t in TABLAS:
            seccion = seccion_de(t, self.sistema)
            if seccion not in secciones or t.clave not in self.datos:
                continue
            filas = self.datos[t.clave]
            if t.modo == "empresa":
                if self.sistema:
                    self._insertar(t.tabla, filas, "upsert")
                else:
                    self._empresa(filas)
            elif t.modo == "permisos":
                self._permisos(filas)
            else:
                self._insertar(t.tabla, filas, t.modo)
        # empresa.propietario_id: su usuario ya volvio.
        for d in self.diferidas:
            for columna in d["columnas"]:
                valor = d["fila"].get(columna)
                if valor is not None:
                    self.conn.execute(
                        text(f"UPDATE {d['tabla']} SET {columna} = :v WHERE id = :i AND {columna} IS NULL "
                             "AND EXISTS (SELECT 1 FROM usuario WHERE id = :v)"),
                        {"v": valor, "i": d["fila"]["id"]},
                    )
        for tabla in SIN_TRIGGERS:
            self.conn.execute(text(f"ALTER TABLE {tabla} ENABLE TRIGGER USER"))
        # Lo que volvio sin numero de tienda (backups viejos o con los triggers
        # apagados) recibe el suyo, y los contadores quedan por encima.
        self.conn.execute(text("SELECT fn_numerar_faltantes()"))
        # Las filas volvieron con su id: el contador de cada tabla queda por
        # encima (si no, en una base nueva el proximo registro chocaria).
        for tabla in self.resumen:
            if "id" not in self.columnas.get(tabla, []):
                continue
            secuencia =self.conn.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": tabla}).scalar()
            if secuencia:
                self.conn.execute(text(
                    f"SELECT setval('{secuencia}', GREATEST((SELECT coalesce(max(id), 1) FROM {tabla}), "
                    f"(SELECT last_value FROM {secuencia})))"
                ))
        return self.resumen


def _devolver_imagenes(contenido: zipfile.ZipFile, rutas: set[str]) -> int:
    """Vuelve a subir al bucket publico las imagenes que ya no estan."""
    devueltas = 0
    nombres = set(contenido.namelist())
    for ruta in rutas:
        if f"imagenes/{ruta}" not in nombres:
            continue
        if requests.head(_prefijo_publico() + ruta, timeout=15).ok:
            continue
        extension = ruta.rsplit(".", 1)[-1].lower()
        tipo = {"png": "image/png", "webp": "image/webp", "svg": "image/svg+xml"}.get(extension, "image/jpeg")
        _subir(ruta, contenido.read(f"imagenes/{ruta}"), tipo, settings.SUPABASE_STORAGE_BUCKET)
        devueltas += 1
    return devueltas


def restaurar_backup(restauracion_id: int) -> None:
    """Hace el backup previo y restaura (ya creada 'en_proceso')."""
    with engine.connect() as conn:
        r = conn.execute(
            text("SELECT r.*, b.archivos, b.empresa_id AS backup_empresa, coalesce(b.numero, b.id) AS backup_numero FROM backup_restauracion r JOIN backup b ON b.id = r.backup_id WHERE r.id = :i"),
            {"i": restauracion_id},
        ).mappings().first()
        conn.commit()
    if r is None:
        return
    empresa_id = r["backup_empresa"]
    try:
        # 1) Backup de como esta todo AHORA, por si hay que volver atras.
        with engine.begin() as conn:
            previo = crear_backup(conn, empresa_id, list(SECCIONES_SISTEMA if empresa_id is None else SECCIONES),
                                  "antes_de_restaurar", r["hecho_por_id"])
            conn.execute(text("UPDATE backup_restauracion SET backup_previo_id = :b WHERE id = :i"),
                         {"b": previo, "i": restauracion_id})
        generar_backup(previo)
        with engine.connect() as conn:
            estado = conn.execute(text("SELECT estado, error FROM backup WHERE id = :i"), {"i": previo}).first()
            conn.commit()
        if estado.estado != "completado":
            raise RuntimeError(f"No se pudo hacer el backup previo: {estado.error}")

        # 2) Restaurar desde el ZIP.
        contenido = zipfile.ZipFile(io.BytesIO(descargar_archivos(r["archivos"])))
        datos = json.loads(contenido.read("datos.json"))
        secciones = set(r["secciones"])
        with engine.begin() as conn:
            resumen = _Restaurador(conn, datos, empresa_id is None, empresa_id).restaurar(secciones)
        claves = {t.clave for t in TABLAS if seccion_de(t, empresa_id is None) in secciones}
        try:
            imagenes = _devolver_imagenes(contenido, _imagenes_de(datos, claves))
        except Exception:  # noqa: BLE001 - los datos ya volvieron; las imagenes no la hacen fallar
            logger.exception("Restauracion %s: no se pudieron reponer las imagenes", restauracion_id)
            imagenes = 0
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE backup_restauracion SET estado = 'completada', resumen = CAST(:r AS JSONB), completado_en = now() WHERE id = :i"),
                {"r": json.dumps({"tablas": resumen, "imagenes": imagenes}), "i": restauracion_id},
            )
            totales = {k: sum(x[k] for x in resumen.values()) for k in ("volvieron", "actualizadas", "omitidas")}
            previo_numero = conn.execute(text("SELECT coalesce(numero, id) FROM backup WHERE id = :b"), {"b": previo}).scalar()
            registrar_bitacora(
                conn, r["hecho_por_id"], "COMPLETAR", "backup_restauracion", restauracion_id,
                f"Restauración del backup #{r['backup_numero']} completada ({', '.join(sorted(secciones))}): "
                f"volvieron {totales['volvieron']} registros, se restauraron {totales['actualizadas']}, "
                f"no pudieron volver {totales['omitidas']}, {imagenes} imágenes repuestas. "
                f"Para volver atrás: backup #{previo_numero}.",
                empresa_id,
            )
    except Exception as exc:  # noqa: BLE001 - el error queda en la restauracion
        logger.exception("Restauracion %s fallo", restauracion_id)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE backup_restauracion SET estado = 'fallida', error = :m, completado_en = now() WHERE id = :i"),
                {"m": str(exc)[:500], "i": restauracion_id},
            )
            registrar_bitacora(conn, r["hecho_por_id"], "FALLO", "backup_restauracion", restauracion_id,
                               f"Restauración del backup #{r['backup_numero']} falló, no se cambió nada: {str(exc)[:300]}", empresa_id)


# ================================================================ programacion


def proxima_ejecucion(frecuencia: str, hora: time, fecha: date | None, dia_semana: int | None,
                      dia_mes: int | None, desde: datetime) -> datetime | None:
    """Proxima fecha (UTC, sin zona) en que toca, contada desde `desde` (UTC)."""
    local = desde.replace(tzinfo=timezone.utc).astimezone(BOLIVIA)

    def en(d: date) -> datetime:
        return datetime.combine(d, hora, BOLIVIA)

    if frecuencia == "una_vez":
        candidato = en(fecha) if fecha else None
        if candidato is None or candidato <= local:
            return None
    elif frecuencia == "diaria":
        candidato = en(local.date())
        if candidato <= local:
            candidato = en(local.date() + timedelta(days=1))
    elif frecuencia == "semanal":
        candidato = en(local.date() + timedelta(days=(dia_semana - local.weekday()) % 7))
        if candidato <= local:
            candidato += timedelta(days=7)
    else:
        candidato = None
        anio, mes = local.year, local.month
        for _ in range(3):
            # Si el mes no tiene ese dia (31 en junio), toca el ultimo.
            dia = min(dia_mes, monthrange(anio, mes)[1])
            posible = en(date(anio, mes, dia))
            if posible > local:
                candidato = posible
                break
            anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    return candidato.astimezone(timezone.utc).replace(tzinfo=None) if candidato else None


def plan_con_backups(conn: Connection, empresa_id: int) -> tuple[bool, str | None]:
    fila = conn.execute(
        text("""SELECT p.backups, p.nombre FROM suscripcion s JOIN plan_suscripcion p ON p.id = s.plan_id
                WHERE s.empresa_id = :e AND s.estado = 'activa' ORDER BY s.fecha_inicio DESC LIMIT 1"""),
        {"e": empresa_id},
    ).first()
    return (bool(fila and fila.backups), fila.nombre if fila else None)


def _aplicar_retencion(conn: Connection, programacion_id: int, retener: int) -> None:
    viejos = conn.execute(
        text(
            """SELECT id, archivos FROM backup WHERE programacion_id = :p AND estado = 'completado'
               ORDER BY creado_en DESC OFFSET :n"""
        ),
        {"p": programacion_id, "n": retener},
    ).mappings().all()
    for v in viejos:
        borrar_archivos(v["archivos"])
        conn.execute(text("DELETE FROM backup WHERE id = :i"), {"i": v["id"]})


def ejecutar_programados() -> int:
    """Corre los backups programados que ya tocan (lo llama el proceso de
    fondo cada minuto). Si el servidor estaba dormido, corren al despertar."""
    hechos = 0
    with engine.begin() as conn:
        # Lo que quedo a medias por un reinicio del servidor.
        conn.execute(text("UPDATE backup SET estado = 'fallido', error = 'Se interrumpió (el servidor se reinició).', "
                          "completado_en = now() WHERE estado = 'en_proceso' AND creado_en < now() - interval '30 minutes'"))
        conn.execute(text("UPDATE backup_restauracion SET estado = 'fallida', error = 'Se interrumpió (el servidor se reinició).', "
                          "completado_en = now() WHERE estado = 'en_proceso' AND creado_en < now() - interval '30 minutes'"))
        tocan = conn.execute(
            text("SELECT * FROM backup_programacion WHERE activa AND proxima_ejecucion <= now() FOR UPDATE SKIP LOCKED")
        ).mappings().all()
        nuevos = []
        for p in tocan:
            ahora = conn.execute(text("SELECT now()::timestamp")).scalar()
            siguiente = proxima_ejecucion(p["frecuencia"], p["hora"], p["fecha"], p["dia_semana"], p["dia_mes"], ahora)
            conn.execute(
                text("UPDATE backup_programacion SET ultima_ejecucion = now(), proxima_ejecucion = :s, activa = :a WHERE id = :i"),
                {"s": siguiente, "a": siguiente is not None, "i": p["id"]},
            )
            # Una tienda que bajo a un plan sin backups: la programacion se salta.
            if p["empresa_id"] is not None and not plan_con_backups(conn, p["empresa_id"])[0]:
                registrar_bitacora(conn, p["creado_por_id"], "OMITIR", "backup_programacion", p["id"],
                                   f"Backup programado «{p['nombre']}» no se hizo: el plan de la tienda no incluye backups.",
                                   p["empresa_id"])
                continue
            atrasado = ahora - p["proxima_ejecucion"] > timedelta(minutes=10)
            nuevos.append((crear_backup(conn, p["empresa_id"], list(p["secciones"]), "programado", p["creado_por_id"],
                                        p["id"], atrasado), p["id"], p["retener"]))
    for backup_id, programacion_id, retener in nuevos:
        generar_backup(backup_id)
        with engine.begin() as conn:
            _aplicar_retencion(conn, programacion_id, retener)
        hechos += 1
    return hechos
