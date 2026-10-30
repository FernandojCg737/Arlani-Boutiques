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


def _obtener_token_acceso(cuenta: CuentaPaypal, nuevo: bool = False) -> str:
    """Token OAuth2 de PayPal (client_credentials). Se pide uno en cada
    llamada por simplicidad -- el volumen de este proyecto no justifica
    cachearlo hasta que expire (~9 horas). PayPal igual devuelve el mismo
    mientras no vence; `nuevo` lo obliga a emitir otro (p. ej. despues de
    activar una funcion en la app, cuyo permiso el token viejo no trae)."""
    datos = {"grant_type": "client_credentials"}
    if nuevo:
        datos["ignoreCache"] = "true"
    resp = requests.post(
        f"{_base_url(cuenta)}/v1/oauth2/token",
        auth=(cuenta.client_id, cuenta.secret),
        data=datos,
        timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo conectar con PayPal.")
    return resp.json()["access_token"]


def _cabeceras(cuenta: CuentaPaypal, nuevo: bool = False) -> dict:
    return {"Authorization": f"Bearer {_obtener_token_acceso(cuenta, nuevo)}", "Content-Type": "application/json"}


def _vault(metodo: str, cuenta: CuentaPaypal, ruta: str, **kwargs) -> requests.Response:
    """Llamada a Vault; si PayPal dice "sin permisos" se reintenta una vez con
    un token recien emitido (el anterior puede ser de antes de activar Vault)."""
    resp = requests.request(metodo, f"{_base_url(cuenta)}{ruta}", headers=_cabeceras(cuenta), **kwargs)
    if resp.status_code == 403:
        resp = requests.request(metodo, f"{_base_url(cuenta)}{ruta}", headers=_cabeceras(cuenta, nuevo=True), **kwargs)
    return resp


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


# ---------------------------------------------------- PayPal guardado (Vault)
# El cliente vincula su PayPal una vez en la cuenta de Arlani (Vault v3): queda
# un token de cobro que solo sirve a Arlani. Con el, las compras que hizo sin
# conexion se cobran solas al sincronizar, sin que el cliente apruebe de nuevo.
# En sandbox la app de PayPal necesita la opcion "Vaulting" habilitada.


def _detalle_error(resp: requests.Response) -> str:
    try:
        datos = resp.json()
        detalles = datos.get("details") or []
        if detalles:
            return detalles[0].get("description") or detalles[0].get("issue") or datos.get("message", "")
        return datos.get("message") or resp.text[:200]
    except ValueError:
        return resp.text[:200]


def crear_setup_token(return_url: str, cancel_url: str) -> dict:
    """Primer paso de vincular: PayPal devuelve el enlace "approve" donde el
    cliente inicia sesion y autoriza a Arlani a cobrarle despues."""
    c = _cuenta(None)
    body = {
        "payment_source": {
            "paypal": {
                "description": "Compras sin conexión en Arlani Boutiques",
                "usage_pattern": "IMMEDIATE",
                "usage_type": "MERCHANT",
                "customer_type": "CONSUMER",
                "permit_multiple_payment_tokens": False,
                "experience_context": {
                    "brand_name": "Arlani Boutiques",
                    "locale": "es-ES",
                    "shipping_preference": "NO_SHIPPING",
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                },
            }
        }
    }
    resp = _vault("POST", c, "/v3/vault/setup-tokens", json=body, timeout=20)
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"PayPal no permitió vincular la cuenta: {_detalle_error(resp)}")
    return resp.json()


def crear_payment_token(setup_token_id: str) -> dict:
    """Segundo paso: con el setup token ya aprobado, PayPal crea el token de
    cobro permanente (id) y dice el correo de la cuenta vinculada."""
    c = _cuenta(None)
    body = {"payment_source": {"token": {"id": setup_token_id, "type": "SETUP_TOKEN"}}}
    resp = _vault("POST", c, "/v3/vault/payment-tokens", json=body, timeout=20)
    if not resp.ok:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "PayPal todavía no confirma la vinculación. Aprueba en PayPal y vuelve a intentarlo.",
        )
    return resp.json()


def borrar_payment_token(token_id: str) -> bool:
    """Desvincula el PayPal del cliente en PayPal (best effort)."""
    try:
        c = _cuenta(None)
        resp = _vault("DELETE", c, f"/v3/vault/payment-tokens/{token_id}", timeout=15)
        return resp.ok or resp.status_code == 404
    except Exception:
        return False


class CobroRechazado(Exception):
    """PayPal no cobro con el PayPal guardado (sin fondos, desvinculado...)."""


def cobrar_con_token(token_id: str, total: Decimal, referencia: str, idempotencia: str) -> dict:
    """Cobra `total` (US$) con el PayPal guardado, en la cuenta de Arlani, sin
    que el cliente intervenga. La orden se crea y se captura en el mismo paso.
    `idempotencia` (PayPal-Request-Id) evita cobrar dos veces lo mismo si el
    pedido se reintenta."""
    c = _cuenta(None)
    body = {
        "intent": "CAPTURE",
        "purchase_units": [
            {"reference_id": referencia, "amount": {"currency_code": PAYPAL_CURRENCY, "value": f"{total:.2f}"}}
        ],
        "payment_source": {"paypal": {"vault_id": token_id}},
    }
    cabeceras = {**_cabeceras(c), "PayPal-Request-Id": idempotencia, "Prefer": "return=representation"}
    resp = requests.post(f"{_base_url(c)}/v2/checkout/orders", headers=cabeceras, json=body, timeout=30)
    if not resp.ok:
        raise CobroRechazado(_detalle_error(resp) or "PayPal rechazó el cobro.")
    orden = resp.json()
    # Si PayPal la dejo aprobada pero sin capturar, se captura ahora.
    if orden.get("status") == "APPROVED":
        orden = capturar_orden(orden["id"])
    if orden.get("status") != "COMPLETED" or captura_de(orden) is None:
        raise CobroRechazado("PayPal no completó el cobro.")
    return orden
