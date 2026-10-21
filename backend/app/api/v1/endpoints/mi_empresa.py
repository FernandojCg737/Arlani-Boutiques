"""Lo que una tienda (tenant) ve de si misma en la plataforma.

- /mi-empresa/suscripcion: el Administrador de la tienda ve su plan, cuando
  vence, cuanto usa de el y los planes a los que puede cambiarse. La empresa
  sale siempre de la sesion, nunca de un parametro.
- /tiendas: las tiendas activas (carrusel de la portada).
- /tiendas/{subdominio}: datos publicos de una tienda para su enlace
  /tienda-<subdominio> (no hace falta dominio propio).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import require_administrador
from app.db.session import get_db
from app.models import Usuario
from app.schemas.mi_empresa import (
    HistorialSuscripcionOut,
    MiSuscripcionOut,
    PlanDisponibleOut,
    SucursalPublicaOut,
    TiendaPublicaOut,
    TiendaResumenOut,
)

router = APIRouter()
tiendas_router = APIRouter()


def _admin_de_tienda(admin: Usuario = Depends(require_administrador)) -> Usuario:
    # El SuperAdministrador no pertenece a ninguna tienda: ve las
    # suscripciones de todas en /plataforma/empresas.
    if admin.empresa_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Esta pantalla es del Administrador de cada tienda; desde la plataforma se ve en Empresas.",
        )
    return admin


@router.get("/suscripcion", response_model=MiSuscripcionOut)
def mi_suscripcion(db: Session = Depends(get_db), admin: Usuario = Depends(_admin_de_tienda)) -> MiSuscripcionOut:
    fila = db.execute(text("SELECT * FROM fn_mi_suscripcion(:e)"), {"e": admin.empresa_id}).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa no encontrada.")

    historial = db.execute(text("SELECT * FROM fn_historial_suscripciones(:e)"), {"e": admin.empresa_id}).mappings().all()
    planes = db.execute(
        text(
            "SELECT codigo, nombre, precio_mensual, max_sucursales, dias_prueba, ia_generativa "
            "FROM plan_suscripcion WHERE activo ORDER BY orden"
        )
    ).mappings().all()
    return MiSuscripcionOut(
        **fila,
        historial=[HistorialSuscripcionOut(**h) for h in historial],
        planes=[PlanDisponibleOut(**p) for p in planes],
    )


@tiendas_router.get("", response_model=list[TiendaResumenOut])
def tiendas_publicas(db: Session = Depends(get_db)) -> list[TiendaResumenOut]:
    filas = db.execute(text("SELECT * FROM fn_tiendas_publicas()")).mappings().all()
    return [TiendaResumenOut(**f) for f in filas]


@tiendas_router.get("/{subdominio}", response_model=TiendaPublicaOut)
def tienda_publica(subdominio: str, db: Session = Depends(get_db)) -> TiendaPublicaOut:
    fila = db.execute(text("SELECT * FROM fn_tienda_publica(:s)"), {"s": subdominio}).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esta tienda no existe.")

    sucursales = []
    if fila["estado"] == "activa":
        sucursales = db.execute(
            text(
                "SELECT s.nombre, s.direccion, c.nombre AS ciudad, s.horario_atencion, s.telefono "
                "FROM sucursal s JOIN ciudad c ON c.id = s.ciudad_id "
                "WHERE s.empresa_id = :e AND s.estado = 'activa' ORDER BY c.nombre, s.nombre"
            ),
            {"e": fila["id"]},
        ).mappings().all()
    return TiendaPublicaOut(**fila, sucursales=[SucursalPublicaOut(**s) for s in sucursales])
