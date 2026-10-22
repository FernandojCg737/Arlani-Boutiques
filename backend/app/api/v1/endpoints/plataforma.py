"""Panel del SuperAdministrador de Arlani Boutiques.

CU09 Gestionar empresas (tenants) y CU10 Gestionar y verificar planes,
suscripciones y limites. Las escrituras llaman a funciones/PA de Postgres
(sp_crear_empresa, sp_cambiar_plan_empresa, ...); los triggers calculan
montos/vencimientos, validan limites y registran la bitacora (CU08).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.deps import require_superadmin
from app.core.audit import set_client_ip_for_trigger
from app.core.errores_db import http_desde_pg
from app.db.session import get_db
from app.models import Usuario
from app.schemas.plataforma import (
    ActividadOut,
    DistribucionPlanOut,
    EmpresaCreate,
    EmpresaEstadoIn,
    EmpresaOut,
    EmpresaPlanIn,
    EmpresaUpdate,
    IngresoMesOut,
    LimiteSucursalesOut,
    PlanOut,
    PlanUpdate,
    ResumenPlataformaOut,
)

router = APIRouter()


def _contexto_auditoria(db: Session, usuario: Usuario, request: Request) -> None:
    # Los triggers de auditoria leen quien hizo el cambio de estas variables
    # de sesion (SET LOCAL: valen solo para esta transaccion).
    db.execute(text("SELECT set_config('arlani.usuario_id', :id, true)"), {"id": str(usuario.id)})
    set_client_ip_for_trigger(db, request)


def _ejecutar(db: Session, sql: str, params: dict) -> object:
    """Corre una funcion/PA y traduce sus RAISE EXCEPTION a errores HTTP."""
    try:
        resultado = db.execute(text(sql), params).scalar()
        db.commit()
        return resultado
    except DBAPIError as err:
        db.rollback()
        http = http_desde_pg(err)
        if http is None:
            raise
        raise http from err


def _empresa_o_404(db: Session, empresa_id: int) -> EmpresaOut:
    fila = db.execute(text("SELECT * FROM fn_listar_empresas() WHERE id = :id"), {"id": empresa_id}).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa no encontrada.")
    return EmpresaOut(**fila)


# ----------------------------------------------------------------- panel


@router.get("/resumen", response_model=ResumenPlataformaOut)
def resumen(db: Session = Depends(get_db), _: Usuario = Depends(require_superadmin)) -> ResumenPlataformaOut:
    fila = db.execute(text("SELECT * FROM fn_resumen_plataforma()")).mappings().one()
    return ResumenPlataformaOut(**fila)


@router.get("/ingresos", response_model=list[IngresoMesOut])
def ingresos(
    meses: int = 6, db: Session = Depends(get_db), _: Usuario = Depends(require_superadmin)
) -> list[IngresoMesOut]:
    meses = max(2, min(meses, 24))
    filas = db.execute(text("SELECT * FROM fn_ingresos_mensuales(:m)"), {"m": meses}).mappings().all()
    return [IngresoMesOut(**f) for f in filas]


@router.get("/distribucion-planes", response_model=list[DistribucionPlanOut])
def distribucion_planes(
    db: Session = Depends(get_db), _: Usuario = Depends(require_superadmin)
) -> list[DistribucionPlanOut]:
    filas = db.execute(text("SELECT * FROM fn_distribucion_planes()")).mappings().all()
    return [DistribucionPlanOut(**f) for f in filas]


@router.get("/actividad", response_model=list[ActividadOut])
def actividad(
    limite: int = 12, db: Session = Depends(get_db), _: Usuario = Depends(require_superadmin)
) -> list[ActividadOut]:
    # Ultimos movimientos de toda la plataforma (bitacora, CU08).
    filas = db.execute(
        text(
            "SELECT b.id, b.accion, b.entidad_afectada, b.entidad_id, b.detalle, b.fecha, "
            "u.nombre AS usuario_nombre "
            "FROM bitacora b JOIN usuario u ON u.id = b.usuario_id "
            "ORDER BY b.fecha DESC, b.id DESC LIMIT :limite"
        ),
        {"limite": max(1, min(limite, 50))},
    ).mappings().all()
    return [ActividadOut(**f) for f in filas]


# --------------------------------------------------------- empresas (CU09)


@router.get("/empresas", response_model=list[EmpresaOut])
def listar_empresas(db: Session = Depends(get_db), _: Usuario = Depends(require_superadmin)) -> list[EmpresaOut]:
    filas = db.execute(text("SELECT * FROM fn_listar_empresas()")).mappings().all()
    return [EmpresaOut(**f) for f in filas]


@router.post("/empresas", response_model=EmpresaOut, status_code=status.HTTP_201_CREATED)
def crear_empresa(
    payload: EmpresaCreate,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> EmpresaOut:
    _contexto_auditoria(db, usuario, request)
    empresa_id = _ejecutar(
        db,
        "SELECT sp_crear_empresa(:nombre, :subdominio, :ciudad, :color, :email, :plan, :periodo, NULL)",
        {
            "nombre": payload.nombre,
            "subdominio": payload.subdominio,
            "ciudad": payload.ciudad,
            "color": payload.color_marca,
            "email": payload.email_contacto,
            "plan": payload.plan_codigo,
            "periodo": payload.periodo,
        },
    )
    return _empresa_o_404(db, int(empresa_id))


@router.put("/empresas/{empresa_id}", response_model=EmpresaOut)
def actualizar_empresa(
    empresa_id: int,
    payload: EmpresaUpdate,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> EmpresaOut:
    _contexto_auditoria(db, usuario, request)
    _ejecutar(
        db,
        "SELECT sp_actualizar_empresa(:id, :nombre, :ciudad, :color, :email)",
        {
            "id": empresa_id,
            "nombre": payload.nombre,
            "ciudad": payload.ciudad,
            "color": payload.color_marca,
            "email": payload.email_contacto,
        },
    )
    return _empresa_o_404(db, empresa_id)


@router.patch("/empresas/{empresa_id}/estado", response_model=EmpresaOut)
def cambiar_estado_empresa(
    empresa_id: int,
    payload: EmpresaEstadoIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> EmpresaOut:
    _contexto_auditoria(db, usuario, request)
    _ejecutar(db, "SELECT sp_cambiar_estado_empresa(:id, :estado)", {"id": empresa_id, "estado": payload.estado})
    return _empresa_o_404(db, empresa_id)


@router.patch("/empresas/{empresa_id}/plan", response_model=EmpresaOut)
def cambiar_plan_empresa(
    empresa_id: int,
    payload: EmpresaPlanIn,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> EmpresaOut:
    _contexto_auditoria(db, usuario, request)
    _ejecutar(
        db,
        "SELECT sp_cambiar_plan_empresa(:id, :plan, :periodo)",
        {"id": empresa_id, "plan": payload.plan_codigo, "periodo": payload.periodo},
    )
    return _empresa_o_404(db, empresa_id)


@router.delete("/empresas/{empresa_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_empresa(
    empresa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> None:
    _contexto_auditoria(db, usuario, request)
    _ejecutar(db, "SELECT sp_eliminar_empresa(:id)", {"id": empresa_id})


@router.get("/empresas/{empresa_id}/limite", response_model=LimiteSucursalesOut)
def limite_sucursales(
    empresa_id: int, db: Session = Depends(get_db), _: Usuario = Depends(require_superadmin)
) -> LimiteSucursalesOut:
    fila = db.execute(
        text("SELECT * FROM fn_verificar_limite_sucursales(:id)"), {"id": empresa_id}
    ).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La empresa no tiene una suscripción vigente.")
    return LimiteSucursalesOut(**fila)


# ------------------------------------------------------------ planes (CU10)


@router.get("/planes", response_model=list[PlanOut])
def listar_planes(db: Session = Depends(get_db), _: Usuario = Depends(require_superadmin)) -> list[PlanOut]:
    filas = db.execute(
        text(
            "SELECT p.id, p.codigo, p.nombre, p.precio_mensual, p.max_sucursales, p.dias_prueba, p.ia_generativa, p.operacion_offline, "
            "(SELECT count(*) FROM suscripcion su WHERE su.plan_id = p.id AND su.estado = 'activa') AS empresas "
            "FROM plan_suscripcion p WHERE p.activo ORDER BY p.orden"
        )
    ).mappings().all()
    return [PlanOut(**f) for f in filas]


@router.put("/planes/{codigo}", response_model=PlanOut)
def actualizar_plan(
    codigo: str,
    payload: PlanUpdate,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> PlanOut:
    _contexto_auditoria(db, usuario, request)
    _ejecutar(
        db,
        "SELECT sp_actualizar_plan(:codigo, :precio, :max, :ia)",
        {
            "codigo": codigo,
            "precio": payload.precio_mensual,
            "max": payload.max_sucursales,
            "ia": payload.ia_generativa,
        },
    )
    return next(p for p in listar_planes(db, usuario) if p.codigo == codigo)
