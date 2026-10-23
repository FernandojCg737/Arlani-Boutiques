"""Envio a cada tienda de lo suyo cuando el cliente usa "Pagar todo".

Arlani cobra el carrito completo en SU cuenta de PayPal y, apenas se
confirma, le envia a cada tienda su parte menos la comision (PayPal
Payouts). Si el envio falla, la liquidacion queda 'fallida' y el
SuperAdministrador la reintenta: la venta del cliente ya quedo registrada.
"""

import logging
import uuid
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.paypal import EnvioPayout, enviar_payouts

logger = logging.getLogger(__name__)


def enviar_liquidaciones(db: Session, ids: list[int]) -> None:
    """Envia por PayPal las liquidaciones pendientes o fallidas de `ids` y
    deja su estado (enviada o fallida). Hace commit."""
    filas = db.execute(
        text(
            "SELECT l.id, l.paypal_email, l.neto_usd, l.paypal_order_id, e.nombre "
            "FROM liquidacion_tienda l JOIN empresa e ON e.id = l.empresa_id "
            "WHERE l.id = ANY(:ids) AND l.estado IN ('pendiente', 'fallida')"
        ),
        {"ids": ids},
    ).mappings().all()
    # Una tienda con neto 0 (todo fue comision) no recibe envio.
    sin_monto = [f["id"] for f in filas if Decimal(f["neto_usd"]) <= 0]
    envios = [f for f in filas if Decimal(f["neto_usd"]) > 0]
    for lid in sin_monto:
        db.execute(text("SELECT sp_marcar_liquidacion(:id, 'enviada', NULL, NULL)"), {"id": lid})
    if envios:
        lote, error = enviar_payouts(
            f"ARLANI-{uuid.uuid4().hex[:20]}",
            [
                EnvioPayout(
                    referencia=f"LIQ-{f['id']}",
                    email=f["paypal_email"],
                    monto_usd=Decimal(f["neto_usd"]),
                    nota=f"Ventas de {f['nombre']} en Arlani Boutiques (pago {f['paypal_order_id']}).",
                )
                for f in envios
            ],
        )
        for f in envios:
            db.execute(
                text("SELECT sp_marcar_liquidacion(:id, :estado, :lote, :error)"),
                {"id": f["id"], "estado": "fallida" if error else "enviada", "lote": lote, "error": error},
            )
        if error:
            logger.warning("Liquidaciones %s sin enviar: %s", [f["id"] for f in envios], error)
    db.commit()
