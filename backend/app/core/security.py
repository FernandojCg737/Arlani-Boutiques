import re
import secrets
import string
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(subject: str, session_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "sid": session_id, "scope": "access", "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_reset_token(subject: str, jti: str, minutes: int = 10) -> str:
    # jti se guarda tambien en usuario.reset_token_jti: el token solo vale
    # mientras coincidan, y se limpia al usarlo -- asi sirve una sola vez.
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": subject, "scope": "password_reset", "jti": jti, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_ar_job_token(job_id: str, usuario_id: int, minutes: int = 30) -> str:
    """CU09 modo VIRTUAL: envuelve el job_id real de Decart en un token
    firmado que es lo que ve el cliente. Asi el estado solo lo consulta su
    duenio, y el resultado (que se pide desde un <img src>, sin header de
    Authorization) solo lo descarga quien recibio este token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": str(usuario_id), "scope": "ar_job", "job": job_id, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_ar_job_token(token: str) -> tuple[str, int] | None:
    """(job_id, usuario_id) si el token es valido y vigente; None si no."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    if payload.get("scope") != "ar_job" or not payload.get("job"):
        return None
    try:
        return payload["job"], int(payload.get("sub", 0))
    except (TypeError, ValueError):
        return None


def validate_password_strength(password: str) -> str:
    if len(password) < 8:
        raise ValueError("La contrasena debe tener al menos 8 caracteres.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("La contrasena debe incluir al menos una mayuscula.")
    if not re.search(r"[a-z]", password):
        raise ValueError("La contrasena debe incluir al menos una minuscula.")
    if not re.search(r"\d", password):
        raise ValueError("La contrasena debe incluir al menos un numero.")
    if not re.search(r"[^\w\s]", password):
        raise ValueError("La contrasena debe incluir al menos un caracter especial.")
    return password


def generate_temp_password() -> str:
    # Garantiza que cumpla validate_password_strength sin depender del azar.
    obligatorios = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%&*"),
    ]
    resto = [secrets.choice(string.ascii_letters + string.digits) for _ in range(6)]
    caracteres = obligatorios + resto
    secrets.SystemRandom().shuffle(caracteres)
    return "".join(caracteres)
