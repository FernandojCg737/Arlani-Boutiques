"""Devoluciones: motivo del rechazo

Al rechazar una devolucion el encargado escribe por que, y el cliente lo ve en
su notificacion y en el correo (igual que ya pasa con los cambios de prenda,
que tienen cambio_prenda.motivo_rechazo).

Revision ID: c1e3a5b7d901
Revises: b9d1f3a5c789
Create Date: 2026-10-30

"""
from alembic import op

revision = "c1e3a5b7d901"
down_revision = "b9d1f3a5c789"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE devolucion ADD COLUMN IF NOT EXISTS motivo_rechazo TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE devolucion DROP COLUMN IF EXISTS motivo_rechazo")
