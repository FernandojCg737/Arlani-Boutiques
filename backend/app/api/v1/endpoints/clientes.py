import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import require_permiso, require_superadmin
from app.core.audit import log_bitacora, set_client_ip_for_trigger
from app.core.email import send_email
from app.core.security import generate_temp_password, hash_password
from app.db.session import get_db
from app.models import Cliente, Empresa, Usuario
from app.schemas.clientes import (
    ClienteAdminCreate,
    ClienteAdminOut,
    ClienteAdminUpdate,
    ClientesPorEmpresaOut,
    RelacionTiendaOut,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_cliente_or_404(db: Session, cliente_id: int) -> Cliente:
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if cliente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado.")
    return cliente


def _relacion(db: Session, empresa_id: int) -> dict[int, dict]:
    # Clientes que trabajaron con la empresa y cuanto (fn_clientes_de_empresa).
    filas = db.execute(text("SELECT * FROM fn_clientes_de_empresa(:e)"), {"e": empresa_id}).mappings().all()
    return {f["cliente_id"]: dict(f) for f in filas}


def _verificar_cliente_de_mi_tienda(db: Session, usuario: Usuario, cliente_id: int) -> None:
    # El personal de una tienda solo administra clientes que trabajaron con
    # ella; el SuperAdministrador, a todos.
    if usuario.empresa_id is not None and cliente_id not in _relacion(db, usuario.empresa_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado.")


@router.get("/por-empresa", response_model=list[ClientesPorEmpresaOut])
def clientes_por_empresa(
    db: Session = Depends(get_db), _usuario: Usuario = Depends(require_superadmin)
) -> list[ClientesPorEmpresaOut]:
    filas = db.execute(
        text("SELECT e.id AS empresa_id, (SELECT count(*) FROM fn_clientes_de_empresa(e.id))::int AS total FROM empresa e")
    ).mappings().all()
    return [ClientesPorEmpresaOut(**f) for f in filas]


@router.get("", response_model=list[ClienteAdminOut])
def list_clientes(
    buscar: str | None = Query(default=None),
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU03")),
) -> list[ClienteAdminOut]:
    """Clientes de la plataforma.

    - SuperAdministrador: todos (los clientes pasan por la plataforma para
      llegar a cualquier tienda); con empresa_id, solo los de esa tienda.
    - Personal de una tienda: solo los que trabajaron con SU empresa.
    """
    empresa = usuario.empresa_id if usuario.empresa_id is not None else empresa_id
    relacion = _relacion(db, empresa) if empresa is not None else None

    query = db.query(Cliente)
    if relacion is not None:
        query = query.filter(Cliente.id.in_(list(relacion) or [-1]))
    if buscar:
        like = f"%{buscar}%"
        query = query.filter(Cliente.nombre.ilike(like) | Cliente.email.ilike(like))

    resultado = []
    for c in query.order_by(Cliente.nombre).all():
        out = ClienteAdminOut.model_validate(c)
        if relacion is not None:
            out.relacion = RelacionTiendaOut(**{k: v for k, v in relacion[c.id].items() if k != "cliente_id"})
        resultado.append(out)
    return resultado


@router.post("", response_model=ClienteAdminOut, status_code=status.HTTP_201_CREATED)
def create_cliente(
    payload: ClienteAdminCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU03")),
) -> ClienteAdminOut:
    existing = db.query(Usuario).filter(Usuario.email == payload.email).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese correo.")

    password_temporal = generate_temp_password()

    set_client_ip_for_trigger(db, request)
    result = db.execute(
        text(
            "SELECT sp_crear_cliente(:nombre, :email, :password_hash, :telefono, :direccion, :metodo_registro)"
        ),
        {
            "nombre": payload.nombre,
            "email": payload.email,
            "password_hash": hash_password(password_temporal),
            "telefono": payload.telefono,
            "direccion": payload.direccion,
            "metodo_registro": "admin",
        },
    )
    cliente_id = result.scalar_one()
    db.commit()

    cliente = _get_cliente_or_404(db, cliente_id)

    # Quien lo da de alta: una tienda (su nombre) o la plataforma.
    marca = "Arlani Boutiques"
    if admin.empresa_id is not None:
        marca = db.query(Empresa.nombre).filter(Empresa.id == admin.empresa_id).scalar() or marca

    try:
        send_email(
            to=cliente.email,
            subject=f"Bienvenido a {marca}",
            html_body=(
                f"<p>Hola {cliente.nombre},</p>"
                f"<p>Se creo una cuenta para vos en <strong>{marca}</strong>. "
                "Con ella podes comprar en todas las boutiques de Arlani.</p>"
                "<p>Estos son tus datos de acceso:</p>"
                f"<p>Correo: {cliente.email}<br>Contrasena temporal: {password_temporal}</p>"
                "<p>Te recomendamos cambiar la contrasena desde tu perfil apenas inicies sesion.</p>"
            ),
        )
    except Exception:
        logger.exception("No se pudo enviar el correo de bienvenida a %s", cliente.email)

    log_bitacora(db, admin, "CREAR", "usuario", cliente.id, f"Alta de cliente (admin): {cliente.email}", request)
    return cliente


@router.put("/{cliente_id}", response_model=ClienteAdminOut)
def update_cliente(
    cliente_id: int,
    payload: ClienteAdminUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_permiso("CU03")),
) -> ClienteAdminOut:
    _get_cliente_or_404(db, cliente_id)
    _verificar_cliente_de_mi_tienda(db, admin, cliente_id)

    db.execute(
        text("SELECT sp_actualizar_cliente_admin(:id, :nombre, :telefono, :direccion, :estado)"),
        {
            "id": cliente_id,
            "nombre": payload.nombre,
            "telefono": payload.telefono,
            "direccion": payload.direccion,
            "estado": payload.estado,
        },
    )
    db.commit()

    cliente = _get_cliente_or_404(db, cliente_id)
    log_bitacora(db, admin, "ACTUALIZAR", "usuario", cliente.id, f"Edicion de cliente (admin): {cliente.email}", request)
    return cliente
