"""CU17 del SaaS: clasificador de reportes de la plataforma por voz o texto

modelo_ml.tarea admite 'reportes_saas' (lo que pide el SuperAdministrador:
suscripciones, comisiones, ventas por tienda, tiendas y planes).

Revision ID: b9d1f3a5c789
Revises: a7c9e1b3d567
Create Date: 2026-10-24

"""
from alembic import op

revision = "b9d1f3a5c789"
down_revision = "a7c9e1b3d567"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE modelo_ml DROP CONSTRAINT IF EXISTS modelo_ml_tarea_check;
        ALTER TABLE modelo_ml ADD CONSTRAINT modelo_ml_tarea_check
            CHECK (tarea IN ('reportes', 'chatbot', 'segmentos', 'recomendaciones', 'reportes_saas'));
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM modelo_ml WHERE tarea = 'reportes_saas';
        ALTER TABLE modelo_ml DROP CONSTRAINT IF EXISTS modelo_ml_tarea_check;
        ALTER TABLE modelo_ml ADD CONSTRAINT modelo_ml_tarea_check
            CHECK (tarea IN ('reportes', 'chatbot', 'segmentos', 'recomendaciones'));
    """)
