"""Cuentas PayPal del cliente: permisos de cobro guardados al pagar en una tienda

Al pagar con PayPal, la orden pide guardar la cuenta ("vault con compra") y
PayPal devuelve un token de cobro que vale solo para la cuenta de PayPal que
cobro:
- "Pagar todo" (cuenta de Arlani): el token queda en
  cliente_metodo_pago.token_cifrado y sirve para comprar sin conexion en
  cualquier tienda (como al autorizar la cuenta a mano).
- Pago en una tienda (cuenta de esa tienda): el token queda aca y sirve para
  comprar sin conexion en esa tienda (se cobra directo en su cuenta).
Es del cliente: RLS sin politica para arlani_tenant (como direccion_cliente).

Revision ID: f7b9d1e3a456
Revises: e5a7c9d1f234
Create Date: 2026-10-31

"""
from alembic import op

revision = "f7b9d1e3a456"
down_revision = "e5a7c9d1f234"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE cliente_paypal_token_tienda (
    metodo_id      INTEGER NOT NULL REFERENCES cliente_metodo_pago(id) ON DELETE CASCADE,
    empresa_id     INTEGER NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    token_cifrado  TEXT NOT NULL,
    creado_en      TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (metodo_id, empresa_id)
);
ALTER TABLE cliente_paypal_token_tienda ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON cliente_paypal_token_tienda FROM arlani_tenant;
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS cliente_paypal_token_tienda;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
