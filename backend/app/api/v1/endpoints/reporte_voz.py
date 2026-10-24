"""CU17 Solicitar y exportar reporte generativo (texto o voz).

El usuario pide un reporte hablando (el navegador pasa la voz a texto) o
escribiendo. El modelo del CU18 reconoce que reporte es; las reglas de
app/ml/consulta.py sacan los filtros; el motor dinamico arma el reporte con
los datos reales de SU tienda (RLS). Responde la tabla, el grafico sugerido y
un resumen en palabras. Solo planes con IA generativa (Profesional).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import require_permiso, require_superadmin, sucursal_restringida
from app.api.v1.endpoints.reportes_comun import _empresa_scope, _tabla
from app.core.audit import log_bitacora
from app.core.email import nombre_marca
from app.core.reporte_dinamico import FUENTES_PLATAFORMA, FUENTES_TIENDA, ejecutar
from app.db.session import get_db
from app.ml.consulta import NOMBRES, NOMBRES_SAAS, SUGERENCIAS, SUGERENCIAS_SAAS, interpretar, interpretar_saas, narrar
from app.ml.entrenamiento import predecir
from app.ml.servicio import ModeloNoListo, _a_json, modelo_activo
from app.models import Usuario

router = APIRouter()


class PedidoIn(BaseModel):
    texto: str = Field(min_length=2, max_length=300)
    por_voz: bool = False


def _plan(db: Session, empresa: int) -> tuple[bool, str | None]:
    fila = db.execute(
        text("""SELECT p.ia_generativa, p.nombre FROM suscripcion s JOIN plan_suscripcion p ON p.id = s.plan_id
                WHERE s.empresa_id = :e AND s.estado = 'activa'"""),
        {"e": empresa},
    ).first()
    return (bool(fila and fila.ia_generativa), fila.nombre if fila else None)


def _empresa(db: Session, usuario: Usuario) -> int:
    empresa = _empresa_scope(db, usuario)
    if empresa is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Elige primero la tienda.")
    return empresa


@router.get("/estado")
def estado(db: Session = Depends(get_db), usuario: Usuario = Depends(require_permiso("2P-CU17"))) -> dict:
    disponible, plan = _plan(db, _empresa(db, usuario))
    return {"disponible": disponible, "plan": plan, "sugerencias": SUGERENCIAS}


@router.post("")
def generar(
    payload: PedidoIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("2P-CU17")),
) -> dict:
    empresa = _empresa(db, usuario)
    disponible, plan = _plan(db, empresa)
    if not disponible:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Los reportes con IA son del plan Profesional (la tienda tiene el plan {plan or 'actual'}).")

    try:
        pred = _a_json(predecir(modelo_activo(db, "reportes"), payload.texto))
    except ModeloNoListo:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El modelo de IA se está preparando. Intenta en unos minutos.")
    if pred["intencion"] in ("no_entendido", "no_soportado"):
        return {
            "entendido": False,
            "mensaje": "No entendí qué reporte necesitas. Prueba con algo como estos ejemplos."
            if pred["intencion"] == "no_entendido" else "Eso no es un reporte que pueda armar. Prueba con algo como estos ejemplos.",
            "interpretacion": pred, "sugerencias": SUGERENCIAS,
        }

    restringida = sucursal_restringida(usuario)
    sql = "SELECT id, nombre FROM sucursal WHERE empresa_id = :e AND estado = 'activa'"
    sucursales = [(f.id, f.nombre) for f in db.execute(text(sql), {"e": empresa})]
    hoy = db.execute(text("SELECT (now() AT TIME ZONE 'America/La_Paz')::date")).scalar() or date.today()
    c = interpretar(payload.texto, pred["intencion"], hoy, sucursales)
    sucursal = restringida or c.sucursal_id
    r = ejecutar(
        db, FUENTES_TIENDA, c.fuente, c.agrupar, c.metricas, c.desde, c.hasta, sucursal_id=sucursal,
        marca=nombre_marca(db, empresa), limite=c.limite, ascendente=c.ascendente,
    )
    r.titulo = NOMBRES[pred["intencion"]]
    r.subtitulo = " · ".join([f"“{payload.texto.strip()}”"] + c.filtros)
    tabla = _tabla(r).model_dump(mode="json")
    narrativa = narrar(pred["intencion"], tabla)
    log_bitacora(db, usuario, "CONSULTAR", "reporte_ia", None,
                 f"Reporte por {'voz' if payload.por_voz else 'texto'}: {payload.texto.strip()[:120]} -> {pred['intencion']}", request)
    return {
        "entendido": True,
        "interpretacion": {**pred, "reporte": NOMBRES[pred["intencion"]], "filtros": c.filtros,
                           "fuente": c.fuente, "agrupar": c.agrupar, "metricas": c.metricas},
        "tabla": tabla, "grafico": c.grafico, "narrativa": narrativa,
    }


# ---------- CU17 del SaaS: reportes de toda la plataforma (SuperAdministrador)


@router.get("/saas/estado")
def estado_saas(_: Usuario = Depends(require_superadmin)) -> dict:
    return {"disponible": True, "plan": None, "sugerencias": SUGERENCIAS_SAAS}


@router.post("/saas")
def generar_saas(
    payload: PedidoIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> dict:
    """Igual que el de la tienda, con su propio modelo (tarea reportes_saas)
    y los datos de toda la plataforma: suscripciones, comisiones, ventas por
    tienda, tiendas y planes."""
    try:
        pred = _a_json(predecir(modelo_activo(db, "reportes_saas"), payload.texto))
    except ModeloNoListo:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El modelo de IA se está preparando. Intenta en unos minutos.")
    if pred["intencion"] in ("no_entendido", "no_soportado"):
        return {
            "entendido": False,
            "mensaje": "No entendí qué reporte de la plataforma necesitas. Prueba con algo como estos ejemplos."
            if pred["intencion"] == "no_entendido" else "Eso no es un reporte que pueda armar. Prueba con algo como estos ejemplos.",
            "interpretacion": pred, "sugerencias": SUGERENCIAS_SAAS,
        }
    empresas = [(f.id, f.nombre) for f in db.execute(text("SELECT id, nombre FROM empresa ORDER BY length(nombre) DESC"))]
    hoy = db.execute(text("SELECT (now() AT TIME ZONE 'America/La_Paz')::date")).scalar() or date.today()
    c, empresa_id = interpretar_saas(payload.texto, pred["intencion"], hoy, empresas)
    r = ejecutar(db, FUENTES_PLATAFORMA, c.fuente, c.agrupar, c.metricas, c.desde, c.hasta, empresa_id=empresa_id)
    r.titulo = NOMBRES_SAAS[pred["intencion"]]
    r.subtitulo = " · ".join([f"“{payload.texto.strip()}”"] + c.filtros)
    tabla = _tabla(r).model_dump(mode="json")
    log_bitacora(db, usuario, "CONSULTAR", "reporte_ia", None,
                 f"Reporte SaaS por {'voz' if payload.por_voz else 'texto'}: {payload.texto.strip()[:120]} -> {pred['intencion']}", request)
    return {
        "entendido": True,
        "interpretacion": {**pred, "reporte": NOMBRES_SAAS[pred["intencion"]], "filtros": c.filtros,
                           "fuente": c.fuente, "agrupar": c.agrupar, "metricas": c.metricas},
        "tabla": tabla, "grafico": c.grafico, "narrativa": narrar(pred["intencion"], tabla),
    }
