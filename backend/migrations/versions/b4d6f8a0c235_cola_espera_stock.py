"""Compras sin conexion en cola de espera de stock

Una compra sin conexion que al sincronizar no tiene stock suficiente ya no se
cierra: queda 'en_espera' en la cola de esas prendas (por orden de llegada).
Cuando vuelve a haber stock de TODAS sus prendas se completa sola (PayPal
guardado o contra entrega); si subio el precio pasa a 'por_pagar' para que el
cliente lo confirme. A los 7 dias sin stock se cancela sola.

Revision ID: b4d6f8a0c235
Revises: a3c5e7f9b124
Create Date: 2026-11-01

"""
from alembic import op

revision = "b4d6f8a0c235"
down_revision = "a3c5e7f9b124"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE operacion_offline DROP CONSTRAINT operacion_offline_estado_check;
ALTER TABLE operacion_offline ADD CONSTRAINT operacion_offline_estado_check
    CHECK (estado IN ('confirmada', 'conflicto', 'rechazada', 'resuelta', 'anulada',
                      'por_pagar', 'sin_stock', 'pagada', 'cancelada',
                      'por_cobrar', 'pago_parcial', 'no_pagada', 'en_espera'));
-- La cola se recorre por orden de llegada.
CREATE INDEX IF NOT EXISTS ix_operacion_offline_en_espera
    ON operacion_offline (registrada_en) WHERE estado = 'en_espera';
"""

DOWNGRADE = r"""
DROP INDEX IF EXISTS ix_operacion_offline_en_espera;
UPDATE operacion_offline SET estado = 'sin_stock' WHERE estado = 'en_espera';
ALTER TABLE operacion_offline DROP CONSTRAINT operacion_offline_estado_check;
ALTER TABLE operacion_offline ADD CONSTRAINT operacion_offline_estado_check
    CHECK (estado IN ('confirmada', 'conflicto', 'rechazada', 'resuelta', 'anulada',
                      'por_pagar', 'sin_stock', 'pagada', 'cancelada',
                      'por_cobrar', 'pago_parcial', 'no_pagada'));
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
