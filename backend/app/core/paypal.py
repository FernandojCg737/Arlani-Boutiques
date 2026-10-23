from dataclasses import dataclass
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


@dataclass(frozen=True)
class CuentaPaypal:
    """Credenciales de una cuenta de PayPal. Sin cuenta (None) se usa la de
    la plataforma Arlani (suscripciones, "Pagar todo"); con la de una tienda,
    su venta se cobra en SU cuenta."""

    client_id: str
    secret: str
    modo: str = "sandbox"


def _cuenta(cuenta: CuentaPaypal | None) -> CuentaPaypal:
    if cuenta is not None:
        return cuenta
    if not settings.PAYPAL_CLIENT_ID or not settings.PAYPAL_CLIENT_SECRET:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "El pago con PayPal no esta configurado.")
    return CuentaPaypal(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET, settings.PAYPAL_MODE)


def _base_url(cuenta: CuentaPaypal) -> str:
    return PAYPAL_BASE_URLS.get(cuenta.modo, PAYPAL_BASE_URLS["sandbox"])


def _obtener_token_acceso(cuenta: CuentaPaypal) -> str:
    """Token OAuth2 de PayPal (client_credentials). Se pide uno nuevo en cada
    llamada por simplicidad -- el volumen de este proyecto no justifica
    cachearlo hasta que expire (~9 horas)."""
    resp = requests.post(
        f"{_base_url(cuenta)}/v1/oauth2/token",
        auth=(cuenta.client_id, cuenta.secret),
        data={"grant_type": "client_credentials"},
        timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo conectar con PayPal.")
    return resp.json()["access_token"]


def _cabeceras(cuenta: CuentaPaypal) -> dict:
    return {"Authorization": f"Bearer {_obtener_token_acceso(cuenta)}", "Content-Type": "application/json"}


def verificar_credenciales(cuenta: CuentaPaypal) -> bool:
    """True si PayPal acepta el Client ID y el Secret (al registrar el
    metodo de pago de una tienda)."""
    try:
        resp = requests.post(
            f"{_base_url(cuenta)}/v1/oauth2/token",
            auth=(cuenta.client_id, cuenta.secret),
            data={"grant_type": "client_credentials"},
            timeout=15,
        )
        return resp.ok
    except Exception:
        return False


def crear_orden(
    total: Decimal,
    referencia: str,
    return_url: str | None = None,
    cancel_url: str | None = None,
    cuenta: CuentaPaypal | None = None,
) -> dict:
    """Crea una orden de pago en PayPal (intent=CAPTURE). Esto NO cobra nada
    todavia: el frontend (web o el WebView inline del movil, ver
    `paypal_embed.py`) usa el order_id devuelto para abrir el boton/checkout
    de PayPal, y el cargo real recien ocurre cuando el backend captura la
    orden (ver capturar_orden), despues de que el cliente la aprueba.

    return_url/cancel_url son opcionales -- los usa unicamente el boton
    "PayPal" del WebView movil (ver paypal_embed.py), que en vez del popup
    del JS SDK navega directo al link "approve" que PayPal devuelve aca."""
    c = _cuenta(cuenta)
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
    resp = requests.post(f"{_base_url(c)}/v2/checkout/orders", headers=_cabeceras(c), json=body, timeout=15)
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo crear la orden de pago en PayPal.")
    return resp.json()


def obtener_orden(order_id: str, cuenta: CuentaPaypal | None = None) -> dict:
    """Detalle de una orden (sin cobrar nada): se usa ANTES de capturar para
    confirmar que la orden es de este carrito y por el monto vigente."""
    c = _cuenta(cuenta)
    resp = requests.get(f"{_base_url(c)}/v2/checkout/orders/{order_id}", headers=_cabeceras(c), timeout=15)
    if resp.status_code == 404:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La orden de PayPal no existe.")
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo consultar la orden en PayPal.")
    return resp.json()


def reembolsar_captura(capture_id: str, cuenta: CuentaPaypal | None = None, monto: Decimal | None = None) -> bool:
    """Devuelve el cobro de una captura: completo, o solo `monto` (reembolso
    parcial, ej. la diferencia de un cambio de prenda). Best effort: si
    falla, queda en el log para resolverlo a mano."""
    try:
        c = _cuenta(cuenta)
        body = {"amount": {"currency_code": PAYPAL_CURRENCY, "value": f"{monto:.2f}"}} if monto is not None else {}
        resp = requests.post(
            f"{_base_url(c)}/v2/payments/captures/{capture_id}/refund", headers=_cabeceras(c), json=body, timeout=15
        )
        return resp.ok
    except Exception:
        return False


@dataclass(frozen=True)
class EnvioPayout:
    """Un envio de dinero de Arlani a una tienda (lo suyo de un "Pagar todo")."""

    referencia: str
    email: str
    monto_usd: Decimal
    nota: str


def enviar_payouts(lote: str, envios: list[EnvioPayout]) -> tuple[str | None, str | None]:
    """Envia dinero desde la cuenta de Arlani a cada tienda (PayPal Payouts).
    PayPal lo procesa en segundo plano; devuelve (payout_batch_id, error)."""
    try:
        c = _cuenta(None)
        body = {
            "sender_batch_header": {
                "sender_batch_id": lote,
                "email_subject": "Recibiste el pago de una venta en Arlani Boutiques",
                "email_message": "Arlani Boutiques te envió lo de tus ventas, menos la comisión de tu plan.",
            },
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "receiver": e.email,
                    "amount": {"currency": PAYPAL_CURRENCY, "value": f"{e.monto_usd:.2f}"},
                    "note": e.nota,
                    "sender_item_id": e.referencia,
                }
                for e in envios
            ],
        }
        resp = requests.post(f"{_base_url(c)}/v1/payments/payouts", headers=_cabeceras(c), json=body, timeout=20)
        if not resp.ok:
            try:
                detalle = resp.json().get("message") or resp.text
            except ValueError:
                detalle = resp.text
            return None, f"PayPal rechazó el envío ({resp.status_code}): {detalle}"[:300]
        return resp.json()["batch_header"]["payout_batch_id"], None
    except HTTPException as exc:
        return None, str(exc.detail)
    except Exception as exc:  # red caida, timeout, etc.
        return None, f"No se pudo conectar con PayPal: {exc}"[:300]


def captura_de(resultado: dict) -> dict | None:
    """Primera captura de una orden capturada (id, amount, status)."""
    try:
        return resultado["purchase_units"][0]["payments"]["captures"][0]
    except (KeyError, IndexError, TypeError):
        return None


def capturar_orden(order_id: str, cuenta: CuentaPaypal | None = None) -> dict:
    """Confirma (cobra) una orden que el cliente ya aprobo en el checkout de
    PayPal. Si nunca la aprobo o la orden no existe, PayPal responde con
    error y no se cobra nada."""
    c = _cuenta(cuenta)
    resp = requests.post(f"{_base_url(c)}/v2/checkout/orders/{order_id}/capture", headers=_cabeceras(c), timeout=15)
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo confirmar el pago con PayPal.")
    return resp.json()
