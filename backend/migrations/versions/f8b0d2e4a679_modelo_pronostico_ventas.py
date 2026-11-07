"""CU18: pronostico de ventas por sucursal (aprendizaje supervisado, regresion)

modelo_ml.tarea admite 'pronostico': una version activa por tienda, con sus
metricas (MAE, RMSE, R2), la comparacion de modelos y el pronostico de las
proximas 4 semanas (lo muestra el dashboard del CU07).

Revision ID: f8b0d2e4a679
Revises: e7a9c1d3f568
Create Date: 2026-11-07

"""
from alembic import op

revision = "f8b0d2e4a679"
down_revision = "e7a9c1d3f568"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE modelo_ml DROP CONSTRAINT IF EXISTS modelo_ml_tarea_check;
        ALTER TABLE modelo_ml ADD CONSTRAINT modelo_ml_tarea_check
            CHECK (tarea IN ('reportes', 'chatbot', 'segmentos', 'recomendaciones', 'reportes_saas', 'pronostico'));
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM modelo_ml WHERE tarea = 'pronostico';
        ALTER TABLE modelo_ml DROP CONSTRAINT IF EXISTS modelo_ml_tarea_check;
        ALTER TABLE modelo_ml ADD CONSTRAINT modelo_ml_tarea_check
            CHECK (tarea IN ('reportes', 'chatbot', 'segmentos', 'recomendaciones', 'reportes_saas'));
    """)
