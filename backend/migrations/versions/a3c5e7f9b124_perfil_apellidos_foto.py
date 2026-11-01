"""Actualizar perfil (CU15): apellidos y foto del usuario

`nombre` sigue guardando el nombre completo (lo usan comprobantes, reservas,
bitacora...); `apellidos` guarda aparte la parte de apellidos para poder
editar nombres y apellidos por separado. `foto_url` es la foto de perfil
(Supabase Storage).

Revision ID: a3c5e7f9b124
Revises: f7b9d1e3a456
Create Date: 2026-11-01

"""
from alembic import op

revision = "a3c5e7f9b124"
down_revision = "f7b9d1e3a456"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS apellidos VARCHAR(100);")
    op.execute("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS foto_url VARCHAR(500);")


def downgrade() -> None:
    op.execute("ALTER TABLE usuario DROP COLUMN IF EXISTS foto_url;")
    op.execute("ALTER TABLE usuario DROP COLUMN IF EXISTS apellidos;")
