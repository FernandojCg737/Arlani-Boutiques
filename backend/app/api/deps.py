from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import Usuario
from app.services.usuarios import codigos_permiso

bearer_scheme = HTTPBearer(auto_error=False)

# El SuperAdministrador (dueno de la plataforma) hereda todo el acceso del
# Administrador de una tienda, y ademas gestiona empresas y planes.
ADMIN_TIPOS = {"administrador", "superadministrador"}
STAFF_TIPOS = {*ADMIN_TIPOS, "encargado_sucursal", "cajero"}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado.")

    try:
        payload = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token invalido o expirado.")

    if payload.get("scope") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token invalido.")

    usuario = db.query(Usuario).filter(Usuario.id == int(payload.get("sub", 0))).first()
    if usuario is None or usuario.estado != "activo":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cuenta no disponible.")

    if not usuario.session_id or usuario.session_id != payload.get("sid"):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Tu sesion se cerro porque iniciaste sesion en otro dispositivo.",
        )

    return usuario


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Usuario | None:
    """Igual que get_current_user, pero para endpoints publicos que se
    comportan distinto si hay sesion (ej. registrar que vista de producto)
    sin exigir login: cualquier token ausente/invalido/vencido devuelve
    None en vez de 401."""
    if credentials is None:
        return None
    try:
        return get_current_user(credentials, db)
    except HTTPException:
        return None


def require_staff(usuario: Usuario = Depends(get_current_user)) -> Usuario:
    if usuario.tipo not in STAFF_TIPOS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Acceso restringido al personal de la tienda.")
    return usuario


def require_permiso_cliente(*codigos: str) -> Callable[[Usuario], Usuario]:
    # Equivalente a require_permiso pero para funcionalidades del lado del
    # cliente (CU09/CU18/CU19): no pasa por require_staff, porque quien
    # llama es justamente un Cliente, no personal de la tienda. Lee el
    # mismo mecanismo rol -> permisos (rol "Cliente", seedeado en
    # 5a1d9f6c3e28 y asignado automaticamente por sp_crear_cliente), asi
    # que apagar/prender un CU aca desde el panel (CU02, pestana Cliente)
    # bloquea o habilita la funcionalidad de verdad, no solo la UI.
    def _dependency(usuario: Usuario = Depends(get_current_user)) -> Usuario:
        if usuario.tipo in ADMIN_TIPOS:
            return usuario
        if not codigos_permiso(usuario) & set(codigos):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta funcionalidad no esta habilitada por el momento.")
        return usuario

    return _dependency


def cliente_sin_permiso(usuario: Usuario | None, *codigos: str) -> bool:
    """True si `usuario` es un cliente logueado al que le falta alguno de
    estos permisos en su rol (CU02, pestana Cliente). Para endpoints
    publicos (catalogo, relacionados) que un visitante anonimo puede seguir
    usando igual que antes: solo restringe a quien SI tiene sesion."""
    if usuario is None or usuario.tipo in ADMIN_TIPOS:
        return False
    return not (codigos_permiso(usuario) & set(codigos))


def require_administrador(usuario: Usuario = Depends(require_staff)) -> Usuario:
    if usuario.tipo not in ADMIN_TIPOS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accion restringida al Administrador.")
    return usuario


def sucursal_restringida(usuario: Usuario) -> int | None:
    """Sucursal a la que queda limitado un empleado, o None si puede operar
    sobre todas. El Administrador ve todo; Encargado y Cajero solo su propia
    sucursal (asi un cajero de la sucursal A no aprueba, edita ni borra
    ventas/devoluciones/reservas de la sucursal B)."""
    if usuario.tipo in ADMIN_TIPOS:
        return None
    return getattr(usuario, "sucursal_id", None)


def verificar_acceso_sucursal(usuario: Usuario, sucursal_id: int | None) -> None:
    restringida = sucursal_restringida(usuario)
    if restringida is not None and restringida != sucursal_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puedes operar sobre tu propia sucursal.")


def require_encargado_o_admin(usuario: Usuario) -> None:
    """Acciones destructivas (borrar ventas/devoluciones) quedan fuera del
    alcance del Cajero aunque su rol tenga el permiso del CU."""
    if usuario.tipo not in (*ADMIN_TIPOS, "encargado_sucursal"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Solo el Administrador o el Encargado de Sucursal pueden eliminar registros."
        )


def require_permiso(*codigos: str) -> Callable[[Usuario], Usuario]:
    # Administrador es superusuario por diseno: no depende de la tabla
    # rol_permiso, para que nunca pueda quedar sin acceso al panel por un
    # cambio accidental en la matriz de permisos (CU02).
    # Acepta varios codigos (ej. CU05 o CU12) para endpoints compartidos por
    # mas de un caso de uso; basta con tener uno de ellos.
    def _dependency(usuario: Usuario = Depends(require_staff)) -> Usuario:
        if usuario.tipo in ADMIN_TIPOS:
            return usuario

        # Matriz de permisos de la empresa del usuario (CU02 por empresa).
        if not codigos_permiso(usuario) & set(codigos):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Tu rol no tiene permiso para acceder a {' o '.join(codigos)}."
            )
        return usuario

    return _dependency


def require_superadmin(usuario: Usuario = Depends(get_current_user)) -> Usuario:
    """CU09/CU10: solo el SuperAdministrador gestiona empresas y planes."""
    if usuario.tipo != "superadministrador":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accion restringida al SuperAdministrador de la plataforma.")
    return usuario
