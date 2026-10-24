"""CU18 Gestionar modelos de ML: modelos entrenados

modelo_ml: cada entrenamiento de un modelo (clasificador de intenciones de
reportes por voz/texto del CU17, clasificador del chatbot, recomendador de prendas, o segmentacion de
clientes con K-Means de una tienda). Guarda el algoritmo y la representacion
elegidos, las metricas de evaluacion, la comparacion entre modelos y el
modelo serializado (para usarlo sin reentrenar). Uno activo por tarea y por
tienda: el chatbot de cada tienda se entrena con sus productos y sucursales.

chatbot_mensaje.intencion / confianza: lo que el modelo entendio de cada
mensaje del cliente (el administrador lo ve en la conversacion).

Revision ID: f4b6d8e0a123
Revises: e2a4c6d8f901
Create Date: 2026-10-24

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "f4b6d8e0a123"
down_revision = "e2a4c6d8f901"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE modelo_ml (
    id              SERIAL PRIMARY KEY,
    tarea           VARCHAR(20) NOT NULL CHECK (tarea IN ('reportes', 'chatbot', 'segmentos', 'recomendaciones')),
    empresa_id      INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    version         INTEGER NOT NULL,
    algoritmo       VARCHAR(60) NOT NULL,
    representacion  VARCHAR(30),
    n_ejemplos      INTEGER NOT NULL DEFAULT 0,
    metricas        JSONB NOT NULL DEFAULT '{}'::jsonb,
    comparacion     JSONB NOT NULL DEFAULT '[]'::jsonb,
    artefacto       BYTEA,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    entrenado_por   INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    entrenado_en    TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX ix_modelo_ml_tarea ON modelo_ml (tarea, empresa_id, entrenado_en DESC);
CREATE UNIQUE INDEX ux_modelo_ml_activo ON modelo_ml (tarea, coalesce(empresa_id, 0)) WHERE activo;
-- Solo lo usa el backend (SuperAdministrador); el personal de una tienda no.
ALTER TABLE modelo_ml ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON modelo_ml FROM arlani_tenant;

-- El modelo activo de una tarea, para usarlo desde cualquier rol (el personal
-- de una tienda pide reportes por voz) sin poder ver ni tocar la tabla. Con
-- p_empresa: el de esa tienda si ya tiene uno, si no el general.
CREATE OR REPLACE FUNCTION fn_modelo_ml_activo(p_tarea VARCHAR, p_empresa INTEGER DEFAULT NULL)
RETURNS TABLE (id INTEGER, empresa_id INTEGER, artefacto BYTEA) AS $$
    SELECT m.id, m.empresa_id, m.artefacto FROM modelo_ml m
    WHERE m.tarea = p_tarea AND m.activo AND (m.empresa_id IS NULL OR m.empresa_id = p_empresa)
    ORDER BY m.empresa_id IS NULL
    LIMIT 1;
$$ LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public;

ALTER TABLE chatbot_mensaje
    ADD COLUMN intencion VARCHAR(30),
    ADD COLUMN confianza NUMERIC(4, 3);

-- El chat del catalogo universal (todas las tiendas) no es de ninguna
-- empresa: empresa_id NULL. El personal de una tienda no lo ve (RLS).
ALTER TABLE chatbot ALTER COLUMN empresa_id DROP NOT NULL;
"""

DOWNGRADE = r"""
DELETE FROM chatbot_mensaje WHERE chatbot_id IN (SELECT id FROM chatbot WHERE empresa_id IS NULL);
DELETE FROM chatbot WHERE empresa_id IS NULL;
ALTER TABLE chatbot ALTER COLUMN empresa_id SET NOT NULL;
ALTER TABLE chatbot_mensaje DROP COLUMN IF EXISTS intencion, DROP COLUMN IF EXISTS confianza;
DROP FUNCTION IF EXISTS fn_modelo_ml_activo(VARCHAR, INTEGER);
DROP FUNCTION IF EXISTS fn_modelo_ml_activo(VARCHAR);
DROP TABLE IF EXISTS modelo_ml;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
