from decimal import Decimal

import requests
from fastapi import HTTPException, status

from app.core.config import settings

PAYPAL_BASE_URLS = {
    "sandbox": "https://api-m.sandbox.paypal.com",
    "live": "https://api-m.paypal.com",
}

# PayPal no soporta Bolivianos (BOB) como moneda -- para no meter conversion
# de tipo de cambio real en un proyecto academico, se cobra el mismo monto
# numerico del carrito pero en USD. Es una simplificacion conocida, no una
# conversion de moneda real.
PAYPAL_CURRENCY = "USD"


def _paypal_base_url() -> str:
    return PAYPAL_BASE_URLS.get(settings.PAYPAL_MODE, PAYPAL_BASE_URLS["sandbox"])


def _obtener_token_acceso() -> str:
    """Token OAuth2 de PayPal (client_credentials). Se pide uno nuevo en cada
    llamada por simplicidad -- el volumen de este proyecto no justifica
    cachearlo hasta que expire (~9 horas)."""
    if not settings.PAYPAL_CLIENT_ID or not settings.PAYPAL_CLIENT_SECRET:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "El pago con PayPal no esta configurado.")

    resp = requests.post(
        f"{_paypal_base_url()}/v1/oauth2/token",
        auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo conectar con PayPal.")
    return resp.json()["access_token"]


def crear_orden(
    total: Decimal,
    referencia: str,
    return_url: str | None = None,
    cancel_url: str | None = None,
) -> dict:
    """Crea una orden de pago en PayPal (intent=CAPTURE) por el total del
    carrito. Esto NO cobra nada todavia: el frontend (web o el WebView
    inline del movil, ver `paypal_embed.py`) usa el order_id devuelto para
    abrir el boton/checkout de PayPal, y el cargo real recien ocurre cuando
    el backend captura la orden (ver capturar_orden), despues de que el
    cliente la aprueba (con su cuenta PayPal o con tarjeta de credito via
    el checkout de invitado de PayPal).

    return_url/cancel_url son opcionales -- los usa unicamente el boton
    "PayPal" del WebView movil (ver paypal_embed.py), que en vez del popup
    del JS SDK navega directo al link "approve" que PayPal devuelve aca
    mismo (dentro del `links` de la respuesta)."""
    token = _obtener_token_acceso()
    body: dict = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": referencia,
                "amount": {"currency_code": PAYPAL_CURRENCY, "value": f"{total:.2f}"},
            }
        ],
    }
    if return_url and cancel_url:
        body["application_context"] = {"return_url": return_url, "cancel_url": cancel_url}
    resp = requests.post(
        f"{_paypal_base_url()}/v2/checkout/orders",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
        timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo crear la orden de pago en PayPal.")
    return resp.json()


def obtener_orden(order_id: str) -> dict:
    """Detalle de una orden (sin cobrar nada): se usa ANTES de capturar para
    confirmar que la orden es de este carrito y por el monto vigente -- si
    no, el cliente podria crear una orden barata, agregar mas cosas al
    carrito y recien despues aprobar/capturar."""
    token = _obtener_token_acceso()
    resp = requests.get(
        f"{_paypal_base_url()}/v2/checkout/orders/{order_id}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=15,
    )
    if resp.status_code == 404:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La orden de PayPal no existe.")
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo consultar la orden en PayPal.")
    return resp.json()


def reembolsar_captura(capture_id: str) -> bool:
    """Devuelve el cobro completo de una captura. Se usa como compensacion
    si PayPal ya cobro pero la venta no se pudo guardar. Best effort: si
    falla, queda en el log para resolverlo a mano."""
    try:
        token = _obtener_token_acceso()
        resp = requests.post(
            f"{_paypal_base_url()}/v2/payments/captures/{capture_id}/refund",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={},
            timeout=15,
        )
        return resp.ok
    except Exception:
        return False


def captura_de(resultado: dict) -> dict | None:
    """Primera captura de una orden capturada (id, amount, status)."""
    try:
        return resultado["purchase_units"][0]["payments"]["captures"][0]
    except (KeyError, IndexError, TypeError):
        return None


def capturar_orden(order_id: str) -> dict:
    """Confirma (cobra) una orden que el cliente ya aprobo en el checkout de
    PayPal. Si nunca la aprobo o la orden no existe, PayPal responde con
    error y no se cobra nada."""
    token = _obtener_token_acceso()
    resp = requests.post(
        f"{_paypal_base_url()}/v2/checkout/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo confirmar el pago con PayPal.")
    return resp.json()
