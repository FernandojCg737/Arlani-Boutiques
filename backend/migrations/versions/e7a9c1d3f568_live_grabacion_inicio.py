"""CU22: hora en que empezo la grabacion de cada live

Con ella, al ver la grabacion, cada comentario se ubica en su minuto del video
(repeticion con chat).

Revision ID: e7a9c1d3f568
Revises: d6f8b0c2e457
Create Date: 2026-11-06
"""
from alembic import op

revision = "e7a9c1d3f568"
down_revision = "d6f8b0c2e457"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE live ADD COLUMN grabacion_inicio TIMESTAMP")


def downgrade() -> None:
    op.execute("ALTER TABLE live DROP COLUMN grabacion_inicio")
