"""CU21: los backups pueden tener origen 'importado' (ZIP subido por el usuario).

Revision ID: a1c3e5f7b902
Revises: f8b0d2e4a679
Create Date: 2026-11-08
"""

from alembic import op

revision = "a1c3e5f7b902"
down_revision = "f8b0d2e4a679"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE backup DROP CONSTRAINT IF EXISTS backup_origen_check")
    op.execute(
        "ALTER TABLE backup ADD CONSTRAINT backup_origen_check "
        "CHECK (origen IN ('manual', 'programado', 'antes_de_restaurar', 'importado'))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM backup WHERE origen = 'importado'")
    op.execute("ALTER TABLE backup DROP CONSTRAINT IF EXISTS backup_origen_check")
    op.execute(
        "ALTER TABLE backup ADD CONSTRAINT backup_origen_check "
        "CHECK (origen IN ('manual', 'programado', 'antes_de_restaurar'))"
    )
