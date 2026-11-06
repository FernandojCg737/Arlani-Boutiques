"""CU22 Gestionar live commerce (P3 Operacion de Tiendas).

- Tienda (plan Profesional; Administrador o personal con 2P-CU22): inicia un
  live (uno a la vez por tienda), muestra prendas y fija una en pantalla, ve
  quien esta conectado y quien comenta, oculta comentarios, silencia o expulsa,
  lo termina, y ve o borra sus grabaciones.
- Cualquier usuario con sesion: ve los lives en curso, entra, comenta (texto o
  emojis), reacciona y agrega la prenda fijada al carrito.
- SuperAdministrador: ve todos, corta un live que incumple los terminos y ve o
  borra grabaciones de cualquier tienda.
El video va por LiveKit (app/core/live.py); este modulo guarda todo y reparte
los comentarios a la sala.
"""

import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import STAFF_TIPOS, get_current_user, require_permiso, require_superadmin
from app.core import live as lk
from app.core.audit import client_ip, client_platform
from app.core.aviso_cliente import programar_correo
from app.core.backups import registrar_bitacora
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models import Usuario

logger = logging.getLogger(__name__)
router = APIRouter()

PERMISO = "2P-CU22"


# ------------------------------------------------------------------ esquemas


class LiveOut(BaseModel):
    id: int
    empresa_id: int
    tienda: str
    subdominio: str
    logo_url: str | None
    color_marca: str | None
    titulo: str
    descripcion: str | None
    estado: str
    inicio: datetime
    fin: datetime | None
    espectadores: int
    espectadores_max: int
    comentarios: int
    iniciado_por: str | None
    grabacion_estado: str
    grabacion_segundos: int | None
    grabacion_bytes: int | None
    grabacion_error: str | None
    motivo_corte: str | None
    cortado_por: str | None


class VarianteOut(BaseModel):
    talla_id: int
    talla: str
    color_id: int
    color: str
    sucursal_id: int
    sucursal: str
    stock: int


class ProductoLiveOut(BaseModel):
    id: int
    nombre: str
    precio: float
    precio_original: float | None
    imagen: str | None
    fijado: bool
    variantes: list[VarianteOut]


class ComentarioOut(BaseModel):
    id: int
    usuario_id: int
    usuario: str
    foto_url: str | None
    texto: str
    fecha: datetime
    oculto: bool
    es_tienda: bool


class EspectadorOut(BaseModel):
    usuario_id: int
    nombre: str
    foto_url: str | None
    entro_en: datetime
    conectado: bool
    comentarios: int
    bloqueo: str | None


class SalaOut(BaseModel):
    live: LiveOut
    url: str
    token: str
    vendedor: bool
    silenciado: bool
    productos: list[ProductoLiveOut]
    comentarios: list[ComentarioOut]
    espectadores: list[EspectadorOut] | None


class EstadoTiendaOut(BaseModel):
    disponible: bool
    configurado: bool
    plan: str | None
    actual: LiveOut | None


class ProductoTiendaOut(BaseModel):
    id: int
    nombre: str
    precio: float
    imagen: str | None
    stock: int


class IniciarIn(BaseModel):
    titulo: str = Field(min_length=3, max_length=120)
    descripcion: str | None = Field(default=None, max_length=500)
    producto_ids: list[int] = Field(default_factory=list, max_length=60)


class FijarIn(BaseModel):
    producto_id: int | None


class AgregarProductoIn(BaseModel):
    producto_id: int


class ComentarIn(BaseModel):
    texto: str = Field(min_length=1, max_length=300)


class ReaccionIn(BaseModel):
    emoji: str = Field(min_length=1, max_length=8)


class BloqueoIn(BaseModel):
    usuario_id: int
    tipo: str = Field(pattern="^(silenciado|expulsado)$")


class CortarIn(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


# ------------------------------------------------------------------ consultas

_SQL_LIVE = """
    SELECT l.*, e.nombre AS tienda, e.subdominio, e.logo_url, e.color_marca,
           (SELECT count(*) FROM live_espectador x WHERE x.live_id = l.id AND x.salio_en IS NULL) AS espectadores,
           (SELECT count(*) FROM live_comentario c WHERE c.live_id = l.id AND NOT c.oculto) AS comentarios,
           ui.nombre AS iniciado_por, uc.nombre AS cortado_por
    FROM live l JOIN empresa e ON e.id = l.empresa_id
    LEFT JOIN usuario ui ON ui.id = l.iniciado_por_id
    LEFT JOIN usuario uc ON uc.id = l.cortado_por_id
"""


def _lives(db: Session, donde: str, params: dict) -> list[LiveOut]:
    filas = db.execute(text(f"{_SQL_LIVE} WHERE {donde} ORDER BY l.inicio DESC LIMIT 200"), params).mappings().all()
    return [LiveOut(**f) for f in filas]


def _live(db: Session, live_id: int) -> LiveOut:
    vivos = _lives(db, "l.id = :i", {"i": live_id})
    if not vivos:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Live no encontrado.")
    return vivos[0]


def _es_de_la_tienda(usuario: Usuario, live: LiveOut) -> bool:
    return usuario.tipo == "superadministrador" or (usuario.tipo in STAFF_TIPOS and usuario.empresa_id == live.empresa_id)


def _puede_gestionar(db: Session, usuario: Usuario, live: LiveOut) -> None:
    """Personal de esa tienda con el permiso del CU (o el SuperAdministrador)."""
    if usuario.tipo == "superadministrador":
        return
    if not _es_de_la_tienda(usuario, live):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ese live es de otra tienda.")
    require_permiso(PERMISO)(usuario)


def _plan(db: Session, empresa_id: int) -> tuple[bool, str | None]:
    fila = db.execute(
        text("""SELECT p.live_commerce, p.nombre FROM suscripcion s JOIN plan_suscripcion p ON p.id = s.plan_id
                WHERE s.empresa_id = :e AND s.estado = 'activa' ORDER BY s.fecha_inicio DESC LIMIT 1"""),
        {"e": empresa_id},
    ).first()
    return (bool(fila and fila.live_commerce), fila.nombre if fila else None)


def _productos(db: Session, live_id: int) -> list[ProductoLiveOut]:
    filas = db.execute(
        text(
            """SELECT p.id, p.nombre, p.precio, p.precio_original, lp.fijado_en IS NOT NULL AS fijado,
                      (SELECT url FROM producto_imagen i WHERE i.producto_id = p.id ORDER BY i.orden, i.id LIMIT 1) AS imagen,
                      coalesce((SELECT json_agg(json_build_object(
                                  'talla_id', t.id, 'talla', t.codigo, 'color_id', c.id, 'color', c.nombre,
                                  'sucursal_id', s.id, 'sucursal', s.nombre, 'stock', inv.cantidad) ORDER BY t.id, c.nombre, s.nombre)
                                FROM inventario inv JOIN talla t ON t.id = inv.talla_id JOIN color c ON c.id = inv.color_id
                                JOIN sucursal s ON s.id = inv.sucursal_id
                                WHERE inv.producto_id = p.id AND inv.cantidad > 0 AND s.estado = 'activa'), '[]') AS variantes
               FROM live_producto lp JOIN producto p ON p.id = lp.producto_id
               WHERE lp.live_id = :l AND p.estado = 'activo' ORDER BY lp.fijado_en DESC NULLS LAST, lp.orden"""
        ),
        {"l": live_id},
    ).mappings().all()
    return [ProductoLiveOut(**{**f, "precio": float(f["precio"]),
                               "precio_original": float(f["precio_original"]) if f["precio_original"] else None})
            for f in filas]


def _comentarios(db: Session, live: LiveOut, con_ocultos: bool, limite: int = 150) -> list[ComentarioOut]:
    filas = db.execute(
        text(
            f"""SELECT * FROM (
                  SELECT c.id, c.usuario_id, u.nombre AS usuario, u.foto_url, c.texto, c.fecha, c.oculto,
                         (u.empresa_id = :e AND u.tipo <> 'cliente') AS es_tienda
                  FROM live_comentario c JOIN usuario u ON u.id = c.usuario_id
                  WHERE c.live_id = :l {'' if con_ocultos else 'AND NOT c.oculto'}
                  ORDER BY c.fecha DESC LIMIT :n) x ORDER BY fecha"""
        ),
        {"l": live.id, "e": live.empresa_id, "n": limite},
    ).mappings().all()
    return [ComentarioOut(**{**f, "es_tienda": bool(f["es_tienda"])}) for f in filas]


def _espectadores(db: Session, live_id: int) -> list[EspectadorOut]:
    filas = db.execute(
        text(
            """SELECT x.usuario_id, u.nombre, u.foto_url, x.entro_en, x.salio_en IS NULL AS conectado,
                      (SELECT count(*) FROM live_comentario c WHERE c.live_id = x.live_id AND c.usuario_id = x.usuario_id) AS comentarios,
                      b.tipo AS bloqueo
               FROM live_espectador x JOIN usuario u ON u.id = x.usuario_id
               LEFT JOIN live_bloqueo b ON b.live_id = x.live_id AND b.usuario_id = x.usuario_id
               WHERE x.live_id = :l ORDER BY (x.salio_en IS NULL) DESC, x.entro_en"""
        ),
        {"l": live_id},
    ).mappings().all()
    return [EspectadorOut(**f) for f in filas]


def _bitacora(db: Session, usuario: Usuario, accion: str, entidad_id: int, detalle: str, empresa_id: int,
              request: Request) -> None:
    registrar_bitacora(db.connection(), usuario.id, accion, "live", entidad_id, detalle, empresa_id,
                       client_ip(request), client_platform(request))


def _avisar(sala: str, mensaje: dict) -> None:
    lk.enviar(sala, mensaje)


# --------------------------------------------------------------- avisos


def _notificar_inicio(live_id: int) -> None:
    """Notificacion a todos los clientes y, a los que ya compraron en la tienda,
    tambien por correo."""
    db = SessionLocal()
    try:
        live = db.execute(
            text("SELECT l.id, l.titulo, l.empresa_id, e.nombre FROM live l JOIN empresa e ON e.id = l.empresa_id WHERE l.id = :i"),
            {"i": live_id},
        ).first()
        if live is None:
            return
        mensaje = f"{live.nombre} está EN VIVO: {live.titulo}. Entra a verlo y compra en directo."
        db.execute(
            text(
                """INSERT INTO notificacion (cliente_id, canal, tipo_evento, mensaje, fecha_envio, estado, leida,
                                             entidad_tipo, entidad_id, empresa_id)
                   SELECT c.id, 'app', 'live', :m, now(), 'enviada', FALSE, 'live', :l, :e
                   FROM cliente c JOIN usuario u ON u.id = c.id WHERE u.estado = 'activo'"""
            ),
            {"m": mensaje, "l": live.id, "e": live.empresa_id},
        )
        compradores = db.execute(
            text(
                """SELECT DISTINCT v.cliente_id FROM venta v JOIN sucursal s ON s.id = v.sucursal_id
                   JOIN usuario u ON u.id = v.cliente_id
                   WHERE s.empresa_id = :e AND v.cliente_id IS NOT NULL AND u.estado = 'activo' LIMIT 300"""
            ),
            {"e": live.empresa_id},
        ).scalars().all()
        for cliente_id in compradores:
            programar_correo(db, cliente_id, live.empresa_id, f"{live.nombre} está en vivo",
                             f"{live.titulo}. Como ya compraste en {live.nombre}, te avisamos primero: entra a Arlani "
                             "Boutiques y toca el botón LIVE para verlo y comprar en directo.")
        db.commit()
    except Exception:  # noqa: BLE001 - el aviso nunca hace fallar el live
        db.rollback()
        logger.exception("No se pudo avisar el inicio del live %s", live_id)
    finally:
        db.close()


# ===================================================================== tienda


@router.get("/tienda/estado", response_model=EstadoTiendaOut)
def estado_tienda(
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> EstadoTiendaOut:
    empresa = usuario.empresa_id if usuario.tipo != "superadministrador" else empresa_id
    if empresa is None:
        return EstadoTiendaOut(disponible=False, configurado=lk.configurado(), plan=None, actual=None)
    disponible, plan = _plan(db, empresa)
    actual = _lives(db, "l.empresa_id = :e AND l.estado = 'en_vivo'", {"e": empresa})
    return EstadoTiendaOut(disponible=disponible, configurado=lk.configurado(), plan=plan, actual=actual[0] if actual else None)


@router.get("/tienda/productos", response_model=list[ProductoTiendaOut])
def productos_tienda(db: Session = Depends(get_db), usuario: Usuario = Depends(require_permiso(PERMISO))) -> list[ProductoTiendaOut]:
    filas = db.execute(
        text(
            """SELECT p.id, p.nombre, p.precio,
                      (SELECT url FROM producto_imagen i WHERE i.producto_id = p.id ORDER BY i.orden, i.id LIMIT 1) AS imagen,
                      coalesce((SELECT sum(cantidad) FROM inventario i WHERE i.producto_id = p.id), 0) AS stock
               FROM producto p WHERE p.empresa_id = :e AND p.estado = 'activo' ORDER BY p.nombre"""
        ),
        {"e": usuario.empresa_id},
    ).mappings().all()
    return [ProductoTiendaOut(**{**f, "precio": float(f["precio"])}) for f in filas]


@router.post("/tienda", response_model=SalaOut, status_code=status.HTTP_201_CREATED)
def iniciar(
    payload: IniciarIn,
    request: Request,
    tareas: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> SalaOut:
    if usuario.empresa_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El live lo inicia el personal de una tienda.")
    disponible, plan = _plan(db, usuario.empresa_id)
    if not disponible:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"El live commerce es del plan Profesional (la tienda tiene el plan {plan or 'actual'}).")
    if db.execute(text("SELECT 1 FROM live WHERE empresa_id = :e AND estado = 'en_vivo'"), {"e": usuario.empresa_id}).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "La tienda ya tiene un live en curso.")
    sala = f"tienda-{usuario.empresa_id}-{uuid.uuid4().hex[:10]}"
    lk.crear_sala(sala)
    live_id = db.execute(
        text("INSERT INTO live (empresa_id, titulo, descripcion, sala, iniciado_por_id) VALUES (:e, :t, :d, :s, :u) RETURNING id"),
        {"e": usuario.empresa_id, "t": payload.titulo.strip(), "d": (payload.descripcion or "").strip() or None,
         "s": sala, "u": usuario.id},
    ).scalar_one()
    for orden, producto_id in enumerate(dict.fromkeys(payload.producto_ids)):
        db.execute(
            text("""INSERT INTO live_producto (live_id, producto_id, orden)
                    SELECT :l, id, :o FROM producto WHERE id = :p AND empresa_id = :e AND estado = 'activo'"""),
            {"l": live_id, "p": producto_id, "o": orden, "e": usuario.empresa_id},
        )
    _bitacora(db, usuario, "INICIAR", live_id, f"Inició el live «{payload.titulo.strip()}»", usuario.empresa_id, request)
    db.commit()
    tareas.add_task(_notificar_inicio, live_id)
    return sala_live(live_id, db, usuario)


@router.get("/tienda/historial", response_model=list[LiveOut])
def historial(
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> list[LiveOut]:
    """Lives de la tienda (el SuperAdministrador: de una tienda o de todas)."""
    if usuario.tipo == "superadministrador":
        donde, params = ("l.empresa_id = :e", {"e": empresa_id}) if empresa_id else ("TRUE", {})
    else:
        donde, params = "l.empresa_id = :e", {"e": usuario.empresa_id}
    vivos = _lives(db, donde, params)
    # Si LiveKit no aviso por el webhook, se pregunta como va la grabacion.
    cambio = False
    for v in vivos:
        if v.estado != "en_vivo" and v.grabacion_estado in ("grabando", "procesando"):
            cambio |= _actualizar_grabacion(db, v.id)
    if cambio:
        db.commit()
        vivos = _lives(db, donde, params)
    return vivos


def _actualizar_grabacion(db: Session, live_id: int) -> bool:
    egress_id = db.execute(text("SELECT egress_id FROM live WHERE id = :i"), {"i": live_id}).scalar()
    if not egress_id:
        return False
    try:
        info = lk.estado_grabacion(egress_id)
    except Exception:  # noqa: BLE001 - LiveKit no respondio: se intenta la proxima vez
        return False
    return _guardar_grabacion(db, info) if info else False


def _guardar_grabacion(db: Session, info) -> bool:
    from livekit import api

    if info.status == api.EgressStatus.EGRESS_COMPLETE and info.file_results:
        archivo = info.file_results[0]
        db.execute(
            text("""UPDATE live SET grabacion_estado = 'lista', grabacion_bytes = :b, grabacion_segundos = :s
                    WHERE egress_id = :g AND grabacion_estado <> 'borrada'"""),
            {"b": archivo.size, "s": round(archivo.duration / 1e9), "g": info.egress_id},
        )
        return True
    if info.status in (api.EgressStatus.EGRESS_FAILED, api.EgressStatus.EGRESS_ABORTED, api.EgressStatus.EGRESS_LIMIT_REACHED):
        db.execute(
            text("UPDATE live SET grabacion_estado = 'fallida', grabacion_error = :m WHERE egress_id = :g AND grabacion_estado <> 'borrada'"),
            {"m": (info.error or "LiveKit no pudo grabar el live.")[:300], "g": info.egress_id},
        )
        return True
    if info.status == api.EgressStatus.EGRESS_ENDING:
        db.execute(text("UPDATE live SET grabacion_estado = 'procesando' WHERE egress_id = :g AND grabacion_estado = 'grabando'"),
                   {"g": info.egress_id})
    return False


@router.post("/{live_id}/grabar", response_model=LiveOut)
def grabar(live_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)) -> LiveOut:
    """El vendedor ya esta transmitiendo: empieza la grabacion (una sola vez)."""
    live = _live(db, live_id)
    _puede_gestionar(db, usuario, live)
    if live.estado != "en_vivo" or live.grabacion_estado != "pendiente":
        return live
    sala = db.execute(text("SELECT sala FROM live WHERE id = :i"), {"i": live_id}).scalar()
    clave = f"tiendas/{live.empresa_id}/live-{live_id}-{live.inicio:%Y%m%d-%H%M}.mp4"
    try:
        egress_id = lk.iniciar_grabacion(sala, clave)
    except Exception as exc:  # noqa: BLE001 - el live sigue aunque no se grabe
        logger.exception("No se pudo iniciar la grabacion del live %s", live_id)
        db.execute(text("UPDATE live SET grabacion_estado = 'fallida', grabacion_error = :m WHERE id = :i"),
                   {"m": str(exc)[:300], "i": live_id})
        db.commit()
        return _live(db, live_id)
    db.execute(
        text("UPDATE live SET egress_id = :g, grabacion_clave = :c, grabacion_estado = :s WHERE id = :i"),
        {"g": egress_id, "c": clave, "s": "grabando" if egress_id else "fallida", "i": live_id},
    )
    if not egress_id:
        db.execute(text("UPDATE live SET grabacion_error = 'El almacenamiento de grabaciones no está configurado.' WHERE id = :i"),
                   {"i": live_id})
    db.commit()
    return _live(db, live_id)


def _terminar(db: Session, live_id: int, estado: str, usuario_id: int | None = None, motivo: str | None = None) -> str | None:
    fila = db.execute(
        text("SELECT sala, egress_id, grabacion_estado FROM live WHERE id = :i AND estado = 'en_vivo' FOR UPDATE"), {"i": live_id}
    ).first()
    if fila is None:
        return None
    db.execute(
        text(
            """UPDATE live SET estado = :e, fin = now(), cortado_por_id = :u, motivo_corte = :m,
                      grabacion_estado = CASE WHEN grabacion_estado = 'grabando' THEN 'procesando' ELSE grabacion_estado END
               WHERE id = :i"""
        ),
        {"e": estado, "u": usuario_id, "m": motivo, "i": live_id},
    )
    db.execute(text("UPDATE live_espectador SET salio_en = now() WHERE live_id = :i AND salio_en IS NULL"), {"i": live_id})
    return fila.sala, fila.egress_id


@router.post("/{live_id}/finalizar", response_model=LiveOut)
def finalizar(live_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)) -> LiveOut:
    live = _live(db, live_id)
    _puede_gestionar(db, usuario, live)
    terminado = _terminar(db, live_id, "finalizado")
    if terminado:
        sala, egress_id = terminado
        _bitacora(db, usuario, "FINALIZAR", live_id, f"Terminó el live «{live.titulo}»", live.empresa_id, request)
        db.commit()
        _avisar(sala, {"tipo": "fin", "motivo": None})
        lk.detener_grabacion(egress_id)
        lk.cerrar_sala(sala)
    return _live(db, live_id)


@router.put("/{live_id}/fijado", response_model=list[ProductoLiveOut])
def fijar(live_id: int, payload: FijarIn, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)) -> list[ProductoLiveOut]:
    live = _live(db, live_id)
    _puede_gestionar(db, usuario, live)
    db.execute(text("UPDATE live_producto SET fijado_en = NULL WHERE live_id = :l"), {"l": live_id})
    if payload.producto_id is not None:
        db.execute(text("UPDATE live_producto SET fijado_en = now() WHERE live_id = :l AND producto_id = :p"),
                   {"l": live_id, "p": payload.producto_id})
    db.commit()
    productos = _productos(db, live_id)
    _avisar(_sala(db, live_id), {"tipo": "productos", "productos": [p.model_dump() for p in productos]})
    return productos


@router.post("/{live_id}/productos", response_model=list[ProductoLiveOut])
def agregar_producto(live_id: int, payload: AgregarProductoIn, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(get_current_user)) -> list[ProductoLiveOut]:
    live = _live(db, live_id)
    _puede_gestionar(db, usuario, live)
    db.execute(
        text("""INSERT INTO live_producto (live_id, producto_id, orden)
                SELECT :l, id, (SELECT coalesce(max(orden), 0) + 1 FROM live_producto WHERE live_id = :l)
                FROM producto WHERE id = :p AND empresa_id = :e AND estado = 'activo' ON CONFLICT DO NOTHING"""),
        {"l": live_id, "p": payload.producto_id, "e": live.empresa_id},
    )
    db.commit()
    productos = _productos(db, live_id)
    _avisar(_sala(db, live_id), {"tipo": "productos", "productos": [p.model_dump() for p in productos]})
    return productos


@router.post("/{live_id}/comentarios/{comentario_id}/ocultar", status_code=status.HTTP_204_NO_CONTENT)
def ocultar(live_id: int, comentario_id: int, request: Request, db: Session = Depends(get_db),
            usuario: Usuario = Depends(get_current_user)) -> Response:
    live = _live(db, live_id)
    _puede_gestionar(db, usuario, live)
    n = db.execute(
        text("UPDATE live_comentario SET oculto = TRUE, oculto_por_id = :u WHERE id = :c AND live_id = :l"),
        {"u": usuario.id, "c": comentario_id, "l": live_id},
    ).rowcount
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comentario no encontrado.")
    _bitacora(db, usuario, "OCULTAR", live_id, f"Ocultó un comentario del live «{live.titulo}»", live.empresa_id, request)
    db.commit()
    _avisar(_sala(db, live_id), {"tipo": "ocultar", "id": comentario_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{live_id}/bloqueos", response_model=list[EspectadorOut])
def bloquear(live_id: int, payload: BloqueoIn, request: Request, db: Session = Depends(get_db),
             usuario: Usuario = Depends(get_current_user)) -> list[EspectadorOut]:
    live = _live(db, live_id)
    _puede_gestionar(db, usuario, live)
    nombre = db.execute(text("SELECT nombre FROM usuario WHERE id = :u"), {"u": payload.usuario_id}).scalar()
    if nombre is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")
    db.execute(
        text("""INSERT INTO live_bloqueo (live_id, usuario_id, tipo, por_id) VALUES (:l, :u, :t, :p)
                ON CONFLICT (live_id, usuario_id) DO UPDATE SET tipo = EXCLUDED.tipo, por_id = EXCLUDED.por_id, fecha = now()"""),
        {"l": live_id, "u": payload.usuario_id, "t": payload.tipo, "p": usuario.id},
    )
    expulsado = payload.tipo == "expulsado"
    _bitacora(db, usuario, "EXPULSAR" if expulsado else "SILENCIAR", live_id,
              f"{'Expulsó' if expulsado else 'Silenció'} a {nombre} del live «{live.titulo}»", live.empresa_id, request)
    db.commit()
    sala = _sala(db, live_id)
    _avisar(sala, {"tipo": "bloqueo", "usuario_id": payload.usuario_id, "bloqueo": payload.tipo})
    if payload.tipo == "expulsado":
        lk.expulsar(sala, f"u{payload.usuario_id}")
    return _espectadores(db, live_id)


@router.delete("/{live_id}/bloqueos/{usuario_id}", response_model=list[EspectadorOut])
def desbloquear(live_id: int, usuario_id: int, db: Session = Depends(get_db),
                usuario: Usuario = Depends(get_current_user)) -> list[EspectadorOut]:
    live = _live(db, live_id)
    _puede_gestionar(db, usuario, live)
    db.execute(text("DELETE FROM live_bloqueo WHERE live_id = :l AND usuario_id = :u"), {"l": live_id, "u": usuario_id})
    db.commit()
    _avisar(_sala(db, live_id), {"tipo": "bloqueo", "usuario_id": usuario_id, "bloqueo": None})
    return _espectadores(db, live_id)


@router.get("/{live_id}/grabacion")
def ver_grabacion(live_id: int, request: Request, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(get_current_user)) -> dict:
    live = _live(db, live_id)
    _puede_gestionar(db, usuario, live)
    clave = db.execute(text("SELECT grabacion_clave FROM live WHERE id = :i AND grabacion_estado = 'lista'"), {"i": live_id}).scalar()
    if not clave:
        raise HTTPException(status.HTTP_409_CONFLICT, "La grabación todavía no está lista.")
    return {"url": lk.enlace_grabacion(clave)}


@router.delete("/{live_id}/grabacion", response_model=LiveOut)
def borrar_grabacion(live_id: int, request: Request, db: Session = Depends(get_db),
                     usuario: Usuario = Depends(get_current_user)) -> LiveOut:
    live = _live(db, live_id)
    _puede_gestionar(db, usuario, live)
    clave = db.execute(text("SELECT grabacion_clave FROM live WHERE id = :i"), {"i": live_id}).scalar()
    if live.grabacion_estado in ("grabando", "procesando"):
        raise HTTPException(status.HTTP_409_CONFLICT, "La grabación todavía se está procesando.")
    if clave and live.grabacion_estado == "lista":
        lk.borrar_grabacion(clave)
    db.execute(text("UPDATE live SET grabacion_estado = 'borrada' WHERE id = :i"), {"i": live_id})
    _bitacora(db, usuario, "ELIMINAR", live_id, f"Borró la grabación del live «{live.titulo}»", live.empresa_id, request)
    db.commit()
    return _live(db, live_id)


# ============================================================ SuperAdministrador


@router.post("/{live_id}/cortar", response_model=LiveOut)
def cortar(live_id: int, payload: CortarIn, request: Request, db: Session = Depends(get_db),
           usuario: Usuario = Depends(require_superadmin)) -> LiveOut:
    """Corta un live que incumple los terminos y condiciones (queda grabado)."""
    live = _live(db, live_id)
    terminado = _terminar(db, live_id, "cortado", usuario.id, payload.motivo.strip())
    if not terminado:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese live ya terminó.")
    sala, egress_id = terminado
    _bitacora(db, usuario, "CORTAR", live_id, f"Cortó el live «{live.titulo}» de {live.tienda}: {payload.motivo.strip()}",
              live.empresa_id, request)
    # Aviso a la tienda: a su dueño, por correo.
    dueno = db.execute(text("SELECT propietario_id FROM empresa WHERE id = :e"), {"e": live.empresa_id}).scalar()
    if dueno:
        programar_correo(db, dueno, None, "Tu live fue cortado por Arlani Boutiques",
                         f"El live «{live.titulo}» de {live.tienda} se cortó por incumplir los términos y condiciones. "
                         f"Motivo: {payload.motivo.strip()}")
    db.commit()
    _avisar(sala, {"tipo": "fin", "motivo": "La plataforma terminó este live por incumplir los términos y condiciones."})
    lk.detener_grabacion(egress_id)
    lk.cerrar_sala(sala)
    return _live(db, live_id)


# ================================================================ espectadores


@router.get("/en-vivo", response_model=list[LiveOut])
def en_vivo(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)) -> list[LiveOut]:
    """Lives en curso de todas las tiendas (el boton LIVE de la portada)."""
    return _lives(db, "l.estado = 'en_vivo'", {})


def _sala(db: Session, live_id: int) -> str:
    return db.execute(text("SELECT sala FROM live WHERE id = :i"), {"i": live_id}).scalar()


@router.get("/{live_id}/sala", response_model=SalaOut)
def sala_live(live_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)) -> SalaOut:
    """Entrar a un live: el vendedor (personal de la tienda con el permiso)
    transmite; los demas miran."""
    live = _live(db, live_id)
    if live.estado != "en_vivo":
        raise HTTPException(status.HTTP_410_GONE, "Este live ya terminó.")
    vendedor = False
    if _es_de_la_tienda(usuario, live) and usuario.tipo != "superadministrador":
        try:
            require_permiso(PERMISO)(usuario)
            vendedor = True
        except HTTPException:
            vendedor = False
    bloqueo = db.execute(text("SELECT tipo FROM live_bloqueo WHERE live_id = :l AND usuario_id = :u"),
                         {"l": live_id, "u": usuario.id}).scalar()
    if bloqueo == "expulsado":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La tienda te sacó de este live.")
    if not vendedor:
        db.execute(
            text("""INSERT INTO live_espectador (live_id, usuario_id) VALUES (:l, :u)
                    ON CONFLICT (live_id, usuario_id) DO UPDATE SET salio_en = NULL, veces = live_espectador.veces + 1"""),
            {"l": live_id, "u": usuario.id},
        )
        db.commit()
    gestiona = vendedor or usuario.tipo == "superadministrador"
    return SalaOut(
        live=_live(db, live_id),
        url=settings.LIVEKIT_URL,
        token=lk.token(_sala(db, live_id), f"u{usuario.id}", usuario.nombre, vendedor,
                       {"usuario_id": usuario.id, "rol": "vendedor" if vendedor else "espectador"}),
        vendedor=vendedor,
        silenciado=bloqueo == "silenciado",
        productos=_productos(db, live_id),
        comentarios=_comentarios(db, live, con_ocultos=gestiona),
        espectadores=_espectadores(db, live_id) if gestiona else None,
    )


@router.get("/{live_id}/espectadores", response_model=list[EspectadorOut])
def espectadores(live_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)) -> list[EspectadorOut]:
    live = _live(db, live_id)
    _puede_gestionar(db, usuario, live)
    return _espectadores(db, live_id)


@router.post("/{live_id}/comentarios", response_model=ComentarioOut, status_code=status.HTTP_201_CREATED)
def comentar(live_id: int, payload: ComentarIn, db: Session = Depends(get_db),
             usuario: Usuario = Depends(get_current_user)) -> ComentarioOut:
    live = _live(db, live_id)
    if live.estado != "en_vivo":
        raise HTTPException(status.HTTP_410_GONE, "Este live ya terminó.")
    bloqueo = db.execute(text("SELECT tipo FROM live_bloqueo WHERE live_id = :l AND usuario_id = :u"),
                         {"l": live_id, "u": usuario.id}).scalar()
    if bloqueo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La tienda te silenció en este live.")
    # Un comentario cada 2 segundos por persona.
    if db.execute(text("SELECT 1 FROM live_comentario WHERE live_id = :l AND usuario_id = :u AND fecha > now() - interval '2 seconds'"),
                  {"l": live_id, "u": usuario.id}).first():
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Espera un momento antes de volver a comentar.")
    comentario_id = db.execute(
        text("INSERT INTO live_comentario (live_id, usuario_id, texto) VALUES (:l, :u, :t) RETURNING id"),
        {"l": live_id, "u": usuario.id, "t": payload.texto.strip()},
    ).scalar_one()
    db.commit()
    nuevo = next(c for c in _comentarios(db, live, con_ocultos=True, limite=5) if c.id == comentario_id)
    _avisar(_sala(db, live_id), {"tipo": "comentario", "comentario": nuevo.model_dump()})
    return nuevo


@router.post("/{live_id}/reacciones", status_code=status.HTTP_204_NO_CONTENT)
def reaccionar(live_id: int, payload: ReaccionIn, db: Session = Depends(get_db),
               usuario: Usuario = Depends(get_current_user)) -> Response:
    """Emojis que flotan en la pantalla (no se guardan)."""
    live = _live(db, live_id)
    if live.estado == "en_vivo":
        _avisar(_sala(db, live_id), {"tipo": "reaccion", "emoji": payload.emoji, "usuario_id": usuario.id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ===================================================================== webhook


@router.post("/webhook", include_in_schema=False)
async def webhook(request: Request) -> dict:
    """LiveKit avisa quien entra y sale, cuando se cierra la sala y como va la
    grabacion. Se verifica la firma (solo LiveKit puede llamarlo)."""
    cuerpo = (await request.body()).decode()
    try:
        evento = lk.recibir_webhook(cuerpo, request.headers.get("Authorization", ""))
    except Exception:  # noqa: BLE001
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Firma inválida.")
    db = SessionLocal()
    try:
        sala = evento.room.name if evento.HasField("room") else None
        live_id = db.execute(text("SELECT id FROM live WHERE sala = :s"), {"s": sala}).scalar() if sala else None
        identidad = evento.participant.identity if evento.HasField("participant") else ""
        try:
            meta = json.loads(evento.participant.metadata or "{}") if identidad else {}
        except ValueError:
            meta = {}
        if live_id and identidad.startswith("u") and meta.get("rol") == "espectador":
            usuario_id = int(identidad[1:])
            if evento.event == "participant_joined":
                db.execute(
                    text("""INSERT INTO live_espectador (live_id, usuario_id) VALUES (:l, :u)
                            ON CONFLICT (live_id, usuario_id) DO UPDATE SET salio_en = NULL"""),
                    {"l": live_id, "u": usuario_id},
                )
                db.execute(
                    text("""UPDATE live SET espectadores_max = GREATEST(espectadores_max,
                              (SELECT count(*) FROM live_espectador WHERE live_id = :l AND salio_en IS NULL)) WHERE id = :l"""),
                    {"l": live_id},
                )
            elif evento.event == "participant_left":
                db.execute(text("UPDATE live_espectador SET salio_en = now() WHERE live_id = :l AND usuario_id = :u"),
                           {"l": live_id, "u": usuario_id})
        if live_id and evento.event == "room_finished":
            # El vendedor se fue y no volvio: el live termina solo.
            terminado = _terminar(db, live_id, "finalizado")
            if terminado:
                lk.detener_grabacion(terminado[1])
        if evento.HasField("egress_info") and evento.event in ("egress_updated", "egress_ended"):
            _guardar_grabacion(db, evento.egress_info)
        db.commit()
    finally:
        db.close()
    return {"ok": True}
