"""CU18 Gestionar modelos de ML (SuperAdministrador).

- Clasificadores de intenciones (supervisados): "reportes" (lo que se pide
  por voz o texto en el CU17) y "chatbot" (lo que preguntan los clientes):
  uno general y uno por tienda, entrenado tambien con sus productos,
  categorias y sucursales (?empresa_id=).
  Pipeline: normalizacion, tokenizacion, stopwords, lematizacion, BoW/TF-IDF
  (o embeddings del modelo preentrenado) y modelo (Regresion logistica,
  Naive Bayes, KNN o Arbol de decision; se elige el mejor).
- Recomendador de prendas por tienda: hibrido de contenido y filtrado
  colaborativo KNN (app/ml/recomendador.py).
- Segmentacion de clientes por tienda (no supervisado): K-Means sobre RFM.
"""

import json
from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import require_superadmin
from app.core.audit import log_bitacora
from app.db.session import get_db
from app.ml.datos import dataset
from app.ml.entrenamiento import predecir, segmentar_clientes
from app.ml import embeddings
from app.ml.recomendador import parecidas
from app.ml.servicio import ModeloNoListo, _a_json, datos_tienda, guardar_entrenamiento, guardar_recomendador, modelo_activo, recomendador_activo
from app.models import Usuario

router = APIRouter()

TAREAS = {"reportes": "Reportes por voz o texto (CU17)", "chatbot": "Chatbot universal (catálogo de todas las tiendas)"}


class ProbarIn(BaseModel):
    texto: str = Field(min_length=1, max_length=300)


def _tarea(tarea: str, empresa_id: int | None = None) -> str:
    if tarea not in TAREAS or (empresa_id and tarea != "chatbot"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo no encontrado.")
    return tarea


def _modelo(db: Session, tarea: str, empresa_id: int | None, nombre: str) -> dict | None:
    filtro = "m.empresa_id = :e" if empresa_id else "m.empresa_id IS NULL"
    filas = db.execute(
        text(
            f"""SELECT m.id, m.version, m.algoritmo, m.representacion, m.n_ejemplos, m.metricas, m.comparacion, m.activo,
                       m.entrenado_en, u.nombre AS entrenado_por
                FROM modelo_ml m LEFT JOIN usuario u ON u.id = m.entrenado_por
                WHERE m.tarea = :t AND {filtro} ORDER BY m.version DESC LIMIT 10"""
        ),
        {"t": tarea, "e": empresa_id},
    ).mappings().all()
    activo = next((f for f in filas if f["activo"]), None)
    if activo is None:
        return None
    return {
        "tarea": tarea, "empresa_id": empresa_id, "nombre": nombre,
        "activo": {**dict(activo), "entrenado_en": activo["entrenado_en"].isoformat() + "Z"},
        "historial": [{k: (v.isoformat() + "Z" if isinstance(v, datetime) else v) for k, v in f.items()
                       if k not in ("metricas", "comparacion")} | {"f1": f["metricas"].get("f1"), "accuracy": f["metricas"].get("accuracy")}
                      for f in filas],
    }


@router.get("")
def listar(db: Session = Depends(get_db), _: Usuario = Depends(require_superadmin)) -> list[dict]:
    """Cada modelo con su version activa, metricas e historial (el chatbot,
    tambien el de cada tienda)."""
    salida = []
    for tarea, nombre in TAREAS.items():
        try:
            modelo_activo(db, tarea)  # la primera vez lo encarga en segundo plano
        except ModeloNoListo:
            continue
        salida.append(_modelo(db, tarea, None, nombre))
    for e in db.execute(text("SELECT id, nombre FROM empresa WHERE estado = 'activa' ORDER BY nombre")):
        m = _modelo(db, "chatbot", e.id, f"Chatbot de {e.nombre}")
        if m:
            salida.append(m)
    return salida


@router.get("/modelo-lenguaje")
def modelo_lenguaje(_: Usuario = Depends(require_superadmin)) -> dict:
    """El modelo de lenguaje preentrenado (descargado): si esta activado."""
    # modo: "remoto" (servicio aparte, p. ej. un Space de Hugging Face), "local" o "apagado".
    return {"habilitado": embeddings.habilitado(), "modo": embeddings.modo(), "disponible": embeddings.disponible(),
            "nombre": embeddings.MODELO, "dimensiones": 384}


# ---------- Recomendador de prendas (uno por tienda)


def _recomendador(db: Session, empresa_id: int) -> dict | None:
    filas = db.execute(
        text("""SELECT m.id, m.version, m.algoritmo, m.representacion, m.n_ejemplos, m.metricas, m.comparacion, m.activo,
                       m.entrenado_en, u.nombre AS entrenado_por
                FROM modelo_ml m LEFT JOIN usuario u ON u.id = m.entrenado_por
                WHERE m.tarea = 'recomendaciones' AND m.empresa_id = :e ORDER BY m.version DESC LIMIT 10"""),
        {"e": empresa_id},
    ).mappings().all()
    activo = next((f for f in filas if f["activo"]), None)
    if activo is None:
        return None
    fecha = lambda v: v.isoformat() + "Z" if isinstance(v, datetime) else v  # noqa: E731
    return {
        "activo": {k: fecha(v) for k, v in activo.items()},
        "historial": [{"version": f["version"], "algoritmo": f["algoritmo"], "acierto": f["metricas"].get("acierto"),
                       "mrr": f["metricas"].get("mrr"), "entrenado_en": fecha(f["entrenado_en"]), "activo": f["activo"]} for f in filas],
    }


@router.get("/recomendaciones/modelo")
def recomendador(empresa_id: int, db: Session = Depends(get_db), _: Usuario = Depends(require_superadmin)) -> dict:
    """El recomendador activo de la tienda (lo entrena la primera vez), con su
    evaluacion y las prendas para probarlo."""
    if _recomendador(db, empresa_id) is None:
        try:
            guardar_recomendador(db, empresa_id, None)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    productos = db.execute(
        text("SELECT id, nombre FROM producto WHERE empresa_id = :e AND estado = 'activo' ORDER BY nombre"), {"e": empresa_id}
    ).mappings().all()
    return {**_recomendador(db, empresa_id), "productos": [dict(p) for p in productos]}


@router.post("/recomendaciones/entrenar")
def entrenar_recomendador(
    empresa_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(require_superadmin),
) -> dict:
    try:
        r = guardar_recomendador(db, empresa_id, usuario.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    tienda = db.execute(text("SELECT nombre FROM empresa WHERE id = :e"), {"e": empresa_id}).scalar()
    log_bitacora(db, usuario, "ENTRENAR", "modelo_ml", r["id"], f"Recomendador de prendas de {tienda} reentrenado (versión {r['version']})", request)
    return r


@router.get("/recomendaciones/probar")
def probar_recomendador(
    empresa_id: int, producto_id: int, db: Session = Depends(get_db), _: Usuario = Depends(require_superadmin),
) -> list[dict]:
    """Lo que el modelo recomienda junto a una prenda ("Tambien te puede interesar")."""
    artefacto = recomendador_activo(db, empresa_id)
    if artefacto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La tienda todavía no tiene recomendador entrenado.")
    sugeridas = parecidas(artefacto, producto_id, 6)
    if not sugeridas:
        return []
    info = {f.id: f for f in db.execute(
        text("""SELECT p.id, p.nombre, p.precio, c.nombre AS categoria FROM producto p JOIN categoria c ON c.id = p.categoria_id
                WHERE p.id = ANY(:ids)"""),
        {"ids": [pid for pid, _ in sugeridas]},
    )}
    return [{"producto_id": pid, "nombre": info[pid].nombre, "categoria": info[pid].categoria, "precio": float(info[pid].precio),
             "similitud": s} for pid, s in sugeridas if pid in info]


@router.get("/{tarea}/datos")
def datos(
    tarea: str, empresa_id: int | None = Query(default=None), db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin),
) -> dict:
    """El conjunto de entrenamiento (sintetico): cuantos ejemplos por intencion
    y una muestra. De una tienda: con sus productos, categorias y sucursales."""
    _tarea(tarea, empresa_id)
    ds = dataset(tarea, datos_tienda(db, empresa_id), empresa_id or 0) if tarea == "chatbot" else dataset(tarea)
    conteo = Counter(e for _, e in ds)
    return {"total": len(ds), "por_intencion": [{"intencion": k, "ejemplos": v} for k, v in sorted(conteo.items())],
            "muestra": [{"texto": t, "intencion": e} for t, e in ds[:40]]}


@router.post("/{tarea}/entrenar")
def entrenar(
    tarea: str, request: Request, empresa_id: int | None = Query(default=None), db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> dict:
    r = guardar_entrenamiento(db, _tarea(tarea, empresa_id), usuario.id, empresa_id)
    de = f" de {db.execute(text('SELECT nombre FROM empresa WHERE id = :e'), {'e': empresa_id}).scalar()}" if empresa_id else ""
    log_bitacora(db, usuario, "ENTRENAR", "modelo_ml", r["id"], f"Modelo {TAREAS[tarea]}{de} reentrenado (versión {r['version']})", request)
    return r


@router.post("/{tarea}/probar")
def probar(
    tarea: str, payload: ProbarIn, empresa_id: int | None = Query(default=None), db: Session = Depends(get_db),
    _: Usuario = Depends(require_superadmin),
) -> dict:
    """Muestra cada paso del pipeline y la intencion que predice el modelo."""
    try:
        return _a_json(predecir(modelo_activo(db, _tarea(tarea, empresa_id), empresa_id), payload.texto))
    except ModeloNoListo:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El modelo se está entrenando. Intenta en unos minutos.")


@router.get("/segmentos")
def segmentos(empresa_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(require_superadmin)) -> dict:
    """K-Means de los clientes de una tienda por Recencia, Frecuencia y Monto."""
    filas = [dict(f) for f in db.execute(
        text(
            """SELECT u.id AS cliente_id, u.nombre AS cliente, max(v.fecha) AS ultima_compra, count(*) AS compras, sum(v.total) AS monto
               FROM venta v JOIN sucursal s ON s.id = v.sucursal_id JOIN usuario u ON u.id = v.cliente_id
               WHERE s.empresa_id = :e AND v.estado = 'pagada' AND u.email <> 'consumidor.final@arlaniboutiques.com'
               GROUP BY u.id, u.nombre"""
        ),
        {"e": empresa_id},
    ).mappings()]
    resultado = segmentar_clientes(filas, datetime.now(timezone.utc).replace(tzinfo=None))
    if "error" in resultado:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, resultado["error"])
    # Se guarda la corrida (una activa por tienda).
    db.execute(text("UPDATE modelo_ml SET activo = false WHERE tarea = 'segmentos' AND empresa_id = :e"), {"e": empresa_id})
    version = (db.execute(text("SELECT coalesce(max(version), 0) FROM modelo_ml WHERE tarea = 'segmentos' AND empresa_id = :e"),
                          {"e": empresa_id}).scalar() or 0) + 1
    metricas = {k: resultado[k] for k in ("k", "silueta", "siluetas", "segmentos", "variables")}
    db.execute(
        text("""INSERT INTO modelo_ml (tarea, empresa_id, version, algoritmo, representacion, n_ejemplos, metricas, entrenado_por)
                VALUES ('segmentos', :e, :v, 'K-Means', 'RFM estandarizado', :n, CAST(:m AS JSONB), :u)"""),
        {"e": empresa_id, "v": version, "n": len(filas), "m": json.dumps(_a_json(metricas)), "u": usuario.id},
    )
    db.commit()
    return _a_json({**resultado, "version": version, "clientes_analizados": len(filas)})
