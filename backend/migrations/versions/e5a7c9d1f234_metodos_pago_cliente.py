"""Metodos de pago del cliente: sus cuentas PayPal

- cliente_metodo_pago reemplaza a cliente_paypal_guardado (un solo PayPal):
  el cliente puede tener varias cuentas PayPal.
    origen 'automatico'  se registro sola al pagar con ella en Arlani.
    origen 'manual'      la agrego el cliente en Metodos de pago.
    estado 'registrada'  conocida (se pago con ella) pero sin autorizar.
    estado 'pendiente'   el cliente esta autorizandola en PayPal.
    estado 'autorizada'  PayPal dio el token de cobro (Vault, cifrado): se
                         puede cobrar sola una compra sin conexion.
  Es del cliente: RLS sin politica para arlani_tenant (como direccion_cliente).
- Los PayPal ya guardados pasan como cuentas autorizadas.

Revision ID: e5a7c9d1f234
Revises: d3f5a7b9c012
Create Date: 2026-10-31

"""
from alembic import op

revision = "e5a7c9d1f234"
down_revision = "d3f5a7b9c012"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE cliente_metodo_pago (
    id               SERIAL PRIMARY KEY,
    cliente_id       INTEGER NOT NULL REFERENCES cliente(id) ON DELETE CASCADE,
    tipo             VARCHAR(20) NOT NULL DEFAULT 'paypal' CHECK (tipo IN ('paypal')),
    cuenta           VARCHAR(150),
    paypal_payer_id  VARCHAR(30),
    origen           VARCHAR(12) NOT NULL DEFAULT 'automatico' CHECK (origen IN ('automatico', 'manual')),
    estado           VARCHAR(12) NOT NULL DEFAULT 'registrada' CHECK (estado IN ('registrada', 'pendiente', 'autorizada')),
    setup_token      VARCHAR(64),
    token_cifrado    TEXT,
    veces_usado      INTEGER NOT NULL DEFAULT 0,
    ultimo_uso       TIMESTAMP,
    creado_en        TIMESTAMP NOT NULL DEFAULT now(),
    actualizado_en   TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX ix_cliente_metodo_pago ON cliente_metodo_pago (cliente_id);
-- Una fila por cuenta (el correo de PayPal) de cada cliente.
CREATE UNIQUE INDEX ux_cliente_metodo_cuenta ON cliente_metodo_pago (cliente_id, tipo, lower(cuenta))
    WHERE cuenta IS NOT NULL;
ALTER TABLE cliente_metodo_pago ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON cliente_metodo_pago FROM arlani_tenant;

INSERT INTO cliente_metodo_pago (cliente_id, tipo, cuenta, origen, estado, token_cifrado, creado_en, actualizado_en)
SELECT cliente_id, 'paypal', correo, 'manual', 'autorizada', token_cifrado, creado_en, actualizado_en
FROM cliente_paypal_guardado WHERE estado = 'activo' AND token_cifrado IS NOT NULL;

DROP TABLE cliente_paypal_guardado;
"""

DOWNGRADE = r"""
CREATE TABLE cliente_paypal_guardado (
    cliente_id      INTEGER PRIMARY KEY REFERENCES cliente(id) ON DELETE CASCADE,
    estado          VARCHAR(10) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'activo')),
    setup_token     VARCHAR(64),
    token_cifrado   TEXT,
    correo          VARCHAR(150),
    creado_en       TIMESTAMP NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMP NOT NULL DEFAULT now()
);
ALTER TABLE cliente_paypal_guardado ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON cliente_paypal_guardado FROM arlani_tenant;
INSERT INTO cliente_paypal_guardado (cliente_id, estado, token_cifrado, correo, creado_en, actualizado_en)
SELECT DISTINCT ON (cliente_id) cliente_id, 'activo', token_cifrado, cuenta, creado_en, actualizado_en
FROM cliente_metodo_pago WHERE estado = 'autorizada' ORDER BY cliente_id, actualizado_en DESC;
DROP TABLE IF EXISTS cliente_metodo_pago;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
