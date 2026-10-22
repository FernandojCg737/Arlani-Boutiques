"""Lo que una tienda (tenant) ve de si misma en la plataforma.

- /mi-empresa/marca: nombre, logo y color de la tienda del usuario (su panel,
  sus reportes y comprobantes se ven con su marca).
- PUT /mi-empresa/marca: el Administrador cambia el logo o el color.
- /mi-empresa/suscripcion: el Administrador de la tienda ve su plan, cuando
  vence, cuanto usa de el y los planes a los que puede cambiarse. La empresa
  sale siempre de la sesion, nunca de un parametro.
- /tiendas: las tiendas activas (carrusel de la portada).
- /tiendas/{subdominio}: datos publicos de una tienda para su enlace
  /tienda-<subdominio> (no hace falta dominio propio).
"""

import base64

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_administrador
from app.core.audit import set_client_ip_for_trigger
from app.core.storage import upload_logo_empresa
from app.db.session import get_db
from app.models import Usuario
from app.schemas.mi_empresa import (
    HistorialSuscripcionOut,
    MarcaEmpresaIn,
    MarcaEmpresaOut,
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


@router.get("/marca", response_model=MarcaEmpresaOut)
def mi_marca(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)) -> MarcaEmpresaOut:
    if usuario.empresa_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tu cuenta no pertenece a una tienda.")
    fila = db.execute(
        text(
            "SELECT nombre, subdominio, ciudad, color_marca, logo_url, email_contacto FROM empresa WHERE id = :e"
        ),
        {"e": usuario.empresa_id},
    ).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa no encontrada.")
    return MarcaEmpresaOut(**fila)


@router.put("/marca", response_model=MarcaEmpresaOut)
def actualizar_marca(
    payload: MarcaEmpresaIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(_admin_de_tienda),
) -> MarcaEmpresaOut:
    cambios: dict[str, object] = {}
    if payload.color_marca:
        cambios["color_marca"] = payload.color_marca.lower()
    if payload.quitar_logo:
        cambios["logo_url"] = None
    elif payload.logo:
        try:
            contenido = base64.b64decode(payload.logo.partition(",")[2] or payload.logo)
        except ValueError as err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El logo no es una imagen válida.") from err
        cambios["logo_url"] = upload_logo_empresa(admin.empresa_id, contenido)

    if cambios:
        # trg_auditar_plataforma deja el cambio en la bitacora de la tienda.
        db.execute(text("SELECT set_config('arlani.usuario_id', :id, true)"), {"id": str(admin.id)})
        set_client_ip_for_trigger(db, request)
        asignaciones = ", ".join(f"{columna} = :{columna}" for columna in cambios)
        db.execute(text(f"UPDATE empresa SET {asignaciones} WHERE id = :e"), {**cambios, "e": admin.empresa_id})
        db.commit()
    return mi_marca(db, admin)


@router.get("/suscripcion", response_model=MiSuscripcionOut)
def mi_suscripcion(db: Session = Depends(get_db), admin: Usuario = Depends(_admin_de_tienda)) -> MiSuscripcionOut:
    fila = db.execute(text("SELECT * FROM fn_mi_suscripcion(:e)"), {"e": admin.empresa_id}).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa no encontrada.")

    historial = db.execute(text("SELECT * FROM fn_historial_suscripciones(:e)"), {"e": admin.empresa_id}).mappings().all()
    planes = db.execute(
        text(
            "SELECT codigo, nombre, precio_mensual, max_sucursales, dias_prueba, ia_generativa, operacion_offline "
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
