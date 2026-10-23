"""Origen de ventas y reservas: online u offline

- venta.origen / reserva.origen: 'online' (se registro con conexion, en la
  tienda en linea o en el mostrador) u 'offline' (se registro sin conexion
  y llego al servidor al sincronizar, CU12).
- sincronizado_en: cuando llego al servidor una operacion offline.
Todo lo existente queda como 'online'. El SuperAdministrador ve las ventas
y reservas de cada tienda separadas en ONLINE y OFFLINE (CU05, CU06).

Revision ID: e0a2c4d6f879
Revises: d8f0b2c4e657
Create Date: 2026-10-23

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "e0a2c4d6f879"
down_revision = "d8f0b2c4e657"
branch_labels = None
depends_on = None


UPGRADE = r"""
ALTER TABLE venta
    ADD COLUMN origen VARCHAR(10) NOT NULL DEFAULT 'online' CHECK (origen IN ('online', 'offline')),
    ADD COLUMN sincronizado_en TIMESTAMP;
ALTER TABLE reserva
    ADD COLUMN origen VARCHAR(10) NOT NULL DEFAULT 'online' CHECK (origen IN ('online', 'offline')),
    ADD COLUMN sincronizado_en TIMESTAMP;
CREATE INDEX ix_venta_origen ON venta (origen) WHERE origen = 'offline';
CREATE INDEX ix_reserva_origen ON reserva (origen) WHERE origen = 'offline';
"""

DOWNGRADE = r"""
DROP INDEX IF EXISTS ix_reserva_origen;
DROP INDEX IF EXISTS ix_venta_origen;
ALTER TABLE reserva DROP COLUMN IF EXISTS sincronizado_en, DROP COLUMN IF EXISTS origen;
ALTER TABLE venta DROP COLUMN IF EXISTS sincronizado_en, DROP COLUMN IF EXISTS origen;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
