from sqlalchemy import text
from sqlalchemy.orm import object_session

from app.models import Usuario
from app.schemas.auth import UsuarioOut


def codigos_permiso(usuario: Usuario) -> set[str]:
    """Permisos efectivos (codigos de CU) del usuario.

    El personal de una tienda usa la matriz de SU empresa
    (empresa_rol_permiso); clientes y SuperAdministrador, la matriz global de
    su rol. La regla vive en Postgres: fn_permisos_usuario.
    """
    if usuario.rol_id is None:
        return set()
    db = object_session(usuario)
    if db is None:
        return {p.nombre for p in usuario.rol.permisos} if usuario.rol else set()
    filas = db.execute(text("SELECT fn_permisos_usuario(:id)"), {"id": usuario.id}).scalars().all()
    return set(filas)


def to_usuario_out(usuario: Usuario) -> UsuarioOut:
    return UsuarioOut(
        id=usuario.id,
        nombre=usuario.nombre,
        email=usuario.email,
        telefono=getattr(usuario, "telefono", None),
        direccion=getattr(usuario, "direccion", None),
        tipo=usuario.tipo,
        rol=usuario.rol.nombre if usuario.rol else None,
        permisos=sorted(codigos_permiso(usuario)),
        sucursal_id=getattr(usuario, "sucursal_id", None),
    )
