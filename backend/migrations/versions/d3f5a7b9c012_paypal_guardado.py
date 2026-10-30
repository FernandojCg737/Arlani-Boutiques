"""PayPal guardado del cliente: compras sin conexion que se cobran solas

- cliente_paypal_guardado: el cliente vincula su PayPal una vez (PayPal Vault,
  en la cuenta de Arlani). Se guarda solo el token de cobro que da PayPal,
  cifrado; nunca datos de la cuenta. Es del cliente: el personal de las
  tiendas no lo ve (RLS sin politica para arlani_tenant), igual que
  direccion_cliente.
- operacion_offline: una compra sin conexion pagada con el PayPal guardado
  llega como 'por_cobrar' ("Pago enviado") y al sincronizar termina en:
    pagada        se cobro todo ("Pago finalizado con exito")
    pago_parcial  se cobro lo que tenia stock y precio vigente; lo demas no
    no_pagada     no se cobro nada (sin stock, PayPal rechazo el cobro...)
  El detalle de lo que no se cobro (y por que) queda en `conflicto`.

Revision ID: d3f5a7b9c012
Revises: c1e3a5b7d901
Create Date: 2026-10-30

"""
from alembic import op

revision = "d3f5a7b9c012"
down_revision = "c1e3a5b7d901"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE cliente_paypal_guardado (
    cliente_id      INTEGER PRIMARY KEY REFERENCES cliente(id) ON DELETE CASCADE,
    -- 'pendiente': el cliente todavia no aprobo en PayPal; 'activo': listo para cobrar.
    estado          VARCHAR(10) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'activo')),
    setup_token     VARCHAR(64),
    token_cifrado   TEXT,
    correo          VARCHAR(150),
    creado_en       TIMESTAMP NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMP NOT NULL DEFAULT now()
);
ALTER TABLE cliente_paypal_guardado ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON cliente_paypal_guardado FROM arlani_tenant;

ALTER TABLE operacion_offline DROP CONSTRAINT operacion_offline_estado_check;
ALTER TABLE operacion_offline ADD CONSTRAINT operacion_offline_estado_check
    CHECK (estado IN ('confirmada', 'conflicto', 'rechazada', 'resuelta', 'anulada',
                      'por_pagar', 'sin_stock', 'pagada', 'cancelada',
                      'por_cobrar', 'pago_parcial', 'no_pagada'));
"""

DOWNGRADE = r"""
UPDATE operacion_offline SET estado = 'cancelada' WHERE estado IN ('por_cobrar', 'pago_parcial', 'no_pagada');
ALTER TABLE operacion_offline DROP CONSTRAINT operacion_offline_estado_check;
ALTER TABLE operacion_offline ADD CONSTRAINT operacion_offline_estado_check
    CHECK (estado IN ('confirmada', 'conflicto', 'rechazada', 'resuelta', 'anulada',
                      'por_pagar', 'sin_stock', 'pagada', 'cancelada'));
DROP TABLE IF EXISTS cliente_paypal_guardado;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
