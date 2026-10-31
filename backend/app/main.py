from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from psycopg2.errors import InsufficientPrivilege
from sqlalchemy.exc import DBAPIError
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.v1.router import api_router
from app.core.ar_embed import render_ar_embed_html
from app.core.config import settings
from app.core.paypal_embed import render_paypal_embed_html, render_paypal_retorno_html

# En produccion no se publica la documentacion interactiva (/docs, /redoc,
# /openapi.json): expone el mapa completo de la API a cualquiera.
_docs = {} if not settings.es_produccion else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title=settings.PROJECT_NAME, **_docs)

# Render (como la mayoria de PaaS) termina el https en su proxy y nos
# reenvia por http puro adentro -- sin esto, `request.base_url` (usado para
# armar el return_url/cancel_url que le mandamos a PayPal) reportaria
# "http://" en vez de "https://".
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # El panel lee X-Suscripcion para llevar a "Mi suscripcion" si la tienda vencio;
    # la web y la app guardan el X-Token-Renovado (sesion que se renueva sola).
    expose_headers=["X-Suscripcion", "X-Token-Renovado"],
)


@app.middleware("http")
async def entregar_token_renovado(request: Request, call_next):
    """Si la peticion renovo la sesion (deps._renovar_sesion), el token nuevo
    viaja en la respuesta y el cliente lo usa desde la proxima."""
    respuesta = await call_next(request)
    token = getattr(request.state, "token_renovado", None)
    if token:
        respuesta.headers["X-Token-Renovado"] = token
    return respuesta

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.on_event("startup")
def preparar_modelos_ml() -> None:
    # CU18: si falta algun modelo (primer despliegue), se entrena en segundo
    # plano para no demorar el arranque.
    import logging
    import threading

    from app.ml.servicio import preparar_modelos

    def entrenar() -> None:
        try:
            preparar_modelos()
        except Exception:  # noqa: BLE001 - se reintenta al primer uso
            logging.getLogger(__name__).exception("No se pudieron preparar los modelos de ML")

    threading.Thread(target=entrenar, daemon=True).start()


@app.exception_handler(DBAPIError)
async def datos_de_otra_tienda(request: Request, exc: DBAPIError) -> JSONResponse:
    # Row Level Security (migracion a8d3f1c6e924): el personal de una tienda
    # quiso tocar datos de otra empresa. Cualquier otro error de base sigue
    # siendo un 500.
    if isinstance(exc.orig, InsufficientPrivilege) and "row-level security" in str(exc.orig):
        return JSONResponse(
            status_code=403, content={"detail": "No tienes acceso a ese dato: pertenece a otra tienda."}
        )
    raise exc


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@app.get("/ar-embed/{producto_id}", response_class=HTMLResponse, include_in_schema=False)
def ar_embed(producto_id: int) -> str:
    """Pagina standalone del probador CU09 (motor Decart), pensada para
    cargarse dentro de un WebView de la app movil Flutter: @decartai/sdk es
    un paquete JS sin equivalente Dart, asi que en vez de reimplementar el
    protocolo WebRTC de Decart a mano en Dart, la app movil reutiliza esta
    misma logica (identica a la del componente Angular ar-tryon) sirviendola
    desde el backend.

    Se sirve HTML (no JSON) porque getUserMedia solo esta disponible en un
    "contexto seguro": https, o el literal "localhost". Una pagina cargada
    como asset local (file://) en el WebView NO califica y el navegador ni
    siquiera expone la API — por eso esta pagina vive en el backend (que en
    produccion es https) en vez de empaquetarse dentro de la app."""
    return render_ar_embed_html(producto_id)


# Sin esto, el WebView de la app movil (a diferencia de un navegador normal,
# que revalida mas seguido) puede quedarse sirviendo una version vieja de
# estas paginas desde su cache HTTP interna despues de un deploy nuevo --
# como la URL no cambia entre sesiones (mismo JWT mientras dure el login),
# nada la fuerza a pedir una version fresca. Se aplica a las 3 paginas del
# flujo de PayPal del WebView movil.
_SIN_CACHE = {"Cache-Control": "no-store"}


@app.get("/paypal-embed", response_class=HTMLResponse, include_in_schema=False)
def paypal_embed(response: Response) -> str:
    """Pagina standalone que renderiza los botones reales del JS SDK de
    PayPal, pensada para cargarse INLINE (no a pantalla completa) dentro
    del checkout movil -- misma experiencia que la web en vez del flujo de
    redireccion con link "approve". Ver `paypal_embed.py`."""
    response.headers.update(_SIN_CACHE)
    return render_paypal_embed_html()


@app.get("/paypal-embed/retorno", response_class=HTMLResponse, include_in_schema=False)
def paypal_embed_retorno(response: Response) -> str:
    """PayPal redirige aca (return_url) cuando el cliente aprueba el pago
    en su checkout real -- ver el boton "PayPal" en `paypal_embed.py`. Esta
    pagina no hace nada mas que avisarle a Flutter por el mismo canal
    PaypalResultChannel que ya escucha, con el order_id (viene en `token`)."""
    response.headers.update(_SIN_CACHE)
    return render_paypal_retorno_html(aprobado=True)


@app.get("/paypal-embed/cancelado", response_class=HTMLResponse, include_in_schema=False)
def paypal_embed_cancelado(response: Response) -> str:
    """PayPal redirige aca (cancel_url) si el cliente cancela su checkout
    real en vez de aprobarlo."""
    response.headers.update(_SIN_CACHE)
    return render_paypal_retorno_html(aprobado=False)
