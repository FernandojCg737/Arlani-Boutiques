"""Limite de solicitudes (ventana deslizante) en memoria del proceso.

Alcanza para este despliegue (una sola instancia de uvicorn en Render): si
algun dia se escala a varias instancias, cada una llevaria su propia cuenta
y habria que mover esto a algo compartido (ej. Redis).

Se usa para frenar fuerza bruta (login, codigo de recuperacion) y abuso de
endpoints que cuestan dinero (chatbot -> Gemini). La clave conviene que sea
la cuenta objetivo (email) o el usuario logueado, no solo la IP: la IP que
llega detras del proxy viene de X-Forwarded-For y el cliente la puede
falsear."""

import threading
import time
from collections import deque

from fastapi import HTTPException, status

_lock = threading.Lock()
_registros: dict[tuple[str, str], deque[float]] = {}
_MAX_CLAVES = 10_000


def _purgar(ahora: float, segundos_max: float) -> None:
    vencidas = [k for k, cola in _registros.items() if not cola or ahora - cola[-1] > segundos_max]
    for k in vencidas:
        del _registros[k]


def verificar_limite(alcance: str, clave: str, maximo: int, segundos: int) -> None:
    """Registra un intento para (alcance, clave) y lanza 429 si en los
    ultimos `segundos` ya hubo `maximo` intentos."""
    ahora = time.monotonic()
    with _lock:
        cola = _registros.setdefault((alcance, clave.lower()), deque())
        while cola and ahora - cola[0] > segundos:
            cola.popleft()
        if len(cola) >= maximo:
            espera = max(1, int(segundos - (ahora - cola[0])) + 1)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Demasiados intentos. Proba de nuevo en {espera} segundos.",
                headers={"Retry-After": str(espera)},
            )
        cola.append(ahora)
        if len(_registros) > _MAX_CLAVES:
            _purgar(ahora, 3600)


def reiniciar_limites() -> None:
    """Solo para tests."""
    with _lock:
        _registros.clear()
