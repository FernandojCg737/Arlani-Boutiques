"""Modelos activos (CU18) para el resto del sistema: el CU17 (reportes por
voz o texto) y el chatbot de cada tienda. Si todavia no hay un modelo
entrenado, se entrena y se guarda; despues se usa el guardado (en memoria
mientras no cambie de version).

El chatbot tiene un modelo general y uno por tienda, entrenado ademas con
los productos, categorias y sucursales de esa tienda."""

import json
import logging
import threading
import warnings

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ml.datos import dataset
from app.ml.entrenamiento import cargar, entrenar_clasificador, serializar

warnings.filterwarnings("ignore", module="sklearn")
warnings.filterwarnings("ignore", category=Warning, message=".*iprint.*")

_cache: dict[tuple[str, int | None], tuple[int, object]] = {}
_lock = threading.Lock()
_entrenando: set[int] = set()


def _a_json(valor):
    return json.loads(json.dumps(valor, default=float))


def datos_tienda(db: Session, empresa_id: int | None) -> dict[str, list[str]]:
    """Productos, categorias y sucursales activos de la tienda, en minusculas.
    Sin empresa_id, los de todas las tiendas visibles y sus nombres (el chat
    universal del catalogo)."""
    de = "= :e" if empresa_id else "IN (SELECT id FROM empresa WHERE estado = 'activa' AND fn_empresa_operativa(id))"

    def lista(sql: str) -> list[str]:
        return [f[0].lower() for f in db.execute(text(sql), {"e": empresa_id}) if f[0]]

    datos = {
        "producto": lista(f"SELECT DISTINCT nombre FROM producto WHERE empresa_id {de} AND estado = 'activo'"),
        "categoria": lista(f"""SELECT DISTINCT c.nombre FROM categoria c JOIN producto p ON p.categoria_id = c.id
                               WHERE p.empresa_id {de} AND p.estado = 'activo'"""),
        "sucursal": lista(f"SELECT nombre FROM sucursal WHERE empresa_id {de} AND estado = 'activa'"),
    }
    if not empresa_id:
        datos["tienda"] = lista(f"SELECT nombre FROM empresa WHERE id {de}")
    return datos


def guardar_entrenamiento(db: Session, tarea: str, usuario_id: int | None, empresa_id: int | None = None) -> dict:
    datos = dataset(tarea, datos_tienda(db, empresa_id), empresa_id or 0) if tarea == "chatbot" else None
    r = entrenar_clasificador(tarea, datos)
    filtro = "empresa_id = :e" if empresa_id else "empresa_id IS NULL"
    p = {"t": tarea, "e": empresa_id}
    version = (db.execute(text(f"SELECT coalesce(max(version), 0) FROM modelo_ml WHERE tarea = :t AND {filtro}"), p).scalar() or 0) + 1
    db.execute(text(f"UPDATE modelo_ml SET activo = false WHERE tarea = :t AND {filtro}"), p)
    fila = db.execute(
        text(
            """INSERT INTO modelo_ml (tarea, empresa_id, version, algoritmo, representacion, n_ejemplos, metricas, comparacion, artefacto, entrenado_por)
               VALUES (:t, :e, :v, :a, :r, :n, CAST(:m AS JSONB), CAST(:c AS JSONB), :art, :u) RETURNING id"""
        ),
        {**p, "v": version, "a": r["algoritmo"], "r": r["representacion"], "n": r["n_ejemplos"],
         "m": json.dumps(_a_json(r["metricas"])), "c": json.dumps(_a_json(r["comparacion"])),
         "art": serializar(r["pipeline"]), "u": usuario_id},
    ).scalar()
    db.commit()
    with _lock:
        _cache[(tarea, empresa_id)] = (fila, r["pipeline"])
    return {"id": fila, "version": version}


def _entrenar_tienda_en_segundo_plano(empresa_id: int) -> None:
    """Una tienda sin modelo propio usa el general mientras se entrena el suyo."""
    from app.db.session import SessionLocal

    with _lock:
        if empresa_id in _entrenando:
            return
        _entrenando.add(empresa_id)

    def entrenar() -> None:
        try:
            with SessionLocal() as db:
                guardar_entrenamiento(db, "chatbot", None, empresa_id)
        except Exception:  # noqa: BLE001 - se reintenta en el proximo mensaje
            logging.getLogger(__name__).exception("No se pudo entrenar el chatbot de la tienda %s", empresa_id)
        finally:
            with _lock:
                _entrenando.discard(empresa_id)

    threading.Thread(target=entrenar, daemon=True).start()


def modelo_activo(db: Session, tarea: str, empresa_id: int | None = None):
    """El clasificador activo de la tarea (reportes o chatbot); con empresa_id,
    el de esa tienda (o el general si todavia no tiene uno)."""
    # Por funcion: el personal de una tienda (rol restringido) no ve la tabla.
    fila = db.execute(
        text("SELECT id, empresa_id, artefacto FROM fn_modelo_ml_activo(:t, :e)"), {"t": tarea, "e": empresa_id}
    ).first()
    if fila is None:
        guardar_entrenamiento(db, tarea, None)
        return _cache[(tarea, None)][1]
    if empresa_id and fila.empresa_id is None and tarea == "chatbot":
        _entrenar_tienda_en_segundo_plano(empresa_id)
    clave = (tarea, fila.empresa_id)
    with _lock:
        if clave in _cache and _cache[clave][0] == fila.id:
            return _cache[clave][1]
    pipeline = cargar(bytes(fila.artefacto))
    with _lock:
        _cache[clave] = (fila.id, pipeline)
    return pipeline


def guardar_recomendador(db: Session, empresa_id: int, usuario_id: int | None) -> dict:
    """Entrena el recomendador de la tienda, lo deja activo y borra sus
    "Tambien te puede interesar" guardados (se rearman con el modelo nuevo)."""
    from app.ml.recomendador import entrenar

    r = entrenar(db, empresa_id)
    p = {"e": empresa_id}
    version = (db.execute(text("SELECT coalesce(max(version), 0) FROM modelo_ml WHERE tarea = 'recomendaciones' AND empresa_id = :e"),
                          p).scalar() or 0) + 1
    db.execute(text("UPDATE modelo_ml SET activo = false WHERE tarea = 'recomendaciones' AND empresa_id = :e"), p)
    fila = db.execute(
        text(
            """INSERT INTO modelo_ml (tarea, empresa_id, version, algoritmo, representacion, n_ejemplos, metricas, comparacion, artefacto, entrenado_por)
               VALUES ('recomendaciones', :e, :v, :a, :r, :n, CAST(:m AS JSONB), CAST(:c AS JSONB), :art, :u) RETURNING id"""
        ),
        {**p, "v": version, "a": r["algoritmo"], "r": r["representacion"], "n": r["n_ejemplos"],
         "m": json.dumps(_a_json(r["metricas"])), "c": json.dumps(_a_json(r["comparacion"])),
         "art": serializar(r["artefacto"]), "u": usuario_id},
    ).scalar()
    db.execute(text("DELETE FROM producto_relacionado WHERE producto_id IN (SELECT id FROM producto WHERE empresa_id = :e)"), p)
    db.commit()
    with _lock:
        _cache[("recomendaciones", empresa_id)] = (fila, r["artefacto"])
    return {"id": fila, "version": version}


def recomendador_activo(db: Session, empresa_id: int) -> dict | None:
    """El recomendador de la tienda, o None si todavia no tiene (se entrena en
    segundo plano y mientras tanto se usan las reglas)."""
    fila = db.execute(
        text("SELECT id, empresa_id, artefacto FROM fn_modelo_ml_activo('recomendaciones', :e)"), {"e": empresa_id}
    ).first()
    if fila is None or fila.empresa_id != empresa_id:
        _en_segundo_plano(("recomendaciones", empresa_id), lambda d: guardar_recomendador(d, empresa_id, None))
        return None
    clave = ("recomendaciones", empresa_id)
    with _lock:
        if clave in _cache and _cache[clave][0] == fila.id:
            return _cache[clave][1]
    artefacto = cargar(bytes(fila.artefacto))
    with _lock:
        _cache[clave] = (fila.id, artefacto)
    return artefacto


def _en_segundo_plano(clave, trabajo) -> None:
    from app.db.session import SessionLocal

    with _lock:
        if clave in _entrenando:
            return
        _entrenando.add(clave)

    def correr() -> None:
        try:
            with SessionLocal() as db:
                trabajo(db)
        except Exception:  # noqa: BLE001 - se reintenta en el proximo uso
            logging.getLogger(__name__).exception("No se pudo entrenar %s", clave)
        finally:
            with _lock:
                _entrenando.discard(clave)

    threading.Thread(target=correr, daemon=True).start()


def preparar_modelos() -> None:
    """Al arrancar el backend: si falta algun modelo, se entrena (asi nadie
    espera el primer entrenamiento en medio de una consulta). Tambien el
    chatbot de cada tienda activa que todavia no tenga el suyo."""
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        for tarea in ("reportes", "chatbot"):
            modelo_activo(db, tarea)
        sin_modelo = db.execute(
            text("""SELECT e.id FROM empresa e WHERE e.estado = 'activa' AND NOT EXISTS (
                        SELECT 1 FROM modelo_ml m WHERE m.tarea = 'chatbot' AND m.empresa_id = e.id AND m.activo)""")
        ).scalars().all()
        for empresa_id in sin_modelo:
            guardar_entrenamiento(db, "chatbot", None, empresa_id)
        # Y el recomendador de prendas de cada tienda con al menos 3 prendas.
        sin_recomendador = db.execute(
            text("""SELECT e.id FROM empresa e WHERE e.estado = 'activa'
                    AND (SELECT count(*) FROM producto p WHERE p.empresa_id = e.id AND p.estado = 'activo') >= 3
                    AND NOT EXISTS (SELECT 1 FROM modelo_ml m WHERE m.tarea = 'recomendaciones' AND m.empresa_id = e.id AND m.activo)""")
        ).scalars().all()
        for empresa_id in sin_recomendador:
            guardar_recomendador(db, empresa_id, None)
