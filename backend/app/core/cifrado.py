"""Cifrado de credenciales sensibles (el Secret de PayPal de cada tienda).

Fernet (AES + HMAC). La clave sale de PAGOS_CLAVE_CIFRADO o, si no esta
configurada, se deriva de SECRET_KEY: lo cifrado solo se puede leer con la
misma clave del servidor. El Secret nunca vuelve al navegador.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    clave = settings.PAGOS_CLAVE_CIFRADO
    if not clave:
        clave = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()).decode()
    return Fernet(clave.encode())


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(cifrado: str) -> str | None:
    try:
        return _fernet().decrypt(cifrado.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def enmascarar(texto: str | None) -> str | None:
    """Para mostrar sin revelar: solo los ultimos 4 caracteres."""
    if not texto:
        return None
    return "••••" + texto[-4:]
