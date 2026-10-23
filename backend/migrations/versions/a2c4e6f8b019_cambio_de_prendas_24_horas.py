"""Politica de cambio de prendas: 24 horas desde la compra (antes 48)

Solo cambia el plazo que valida sp_solicitar_cambio.

Revision ID: a2c4e6f8b019
Revises: f1b3d5e7a908
Create Date: 2026-10-23

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "a2c4e6f8b019"
down_revision = "f1b3d5e7a908"
branch_labels = None
depends_on = None


def _plazo(de: str, a: str) -> str:
    # Reescribe la funcion tal como esta, cambiando solo el intervalo.
    return f"""
DO $$
DECLARE
    v_def TEXT;
BEGIN
    SELECT pg_get_functiondef('sp_solicitar_cambio'::regproc) INTO v_def;
    v_def := replace(v_def, 'interval ''{de} hours''', 'interval ''{a} hours''');
    v_def := replace(v_def, 'Politica de cambios: {de} horas', 'Politica de cambios: {a} horas');
    EXECUTE v_def;
END $$;
"""


def upgrade() -> None:
    op.execute(_plazo("48", "24"))


def downgrade() -> None:
    op.execute(_plazo("24", "48"))
