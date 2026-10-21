"""SaaS: lista publica de tiendas activas (carrusel de la portada)

- fn_tiendas_publicas(): las empresas activas, en el orden en que se sumaron
  a la plataforma, con lo necesario para mostrarlas (nombre, enlace, color,
  logo). La portada las lee para que cada tienda nueva aparezca sola.
- La tienda original (fn_empresa_por_defecto) ya tenia su logo en el
  frontend: se guarda en empresa.logo_url para que salga de la base como las
  demas. No se crea ninguna empresa.

Revision ID: d5b8e2f4a961
Revises: c8f3a5d1e742
Create Date: 2026-10-21

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "d5b8e2f4a961"
down_revision = "c8f3a5d1e742"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE OR REPLACE FUNCTION fn_tiendas_publicas()
RETURNS TABLE (
    id INTEGER, nombre VARCHAR, subdominio VARCHAR, ciudad VARCHAR,
    color_marca VARCHAR, logo_url VARCHAR
) AS $$
    SELECT e.id, e.nombre, e.subdominio, e.ciudad, e.color_marca, e.logo_url
    FROM empresa e
    WHERE e.estado = 'activa'
    ORDER BY e.fecha_creacion, e.id;
$$ LANGUAGE sql STABLE;

UPDATE empresa SET logo_url = '/img/logo.png'
WHERE id = fn_empresa_por_defecto() AND logo_url IS NULL;
"""

DOWNGRADE = r"""
UPDATE empresa SET logo_url = NULL
WHERE id = fn_empresa_por_defecto() AND logo_url = '/img/logo.png';
DROP FUNCTION IF EXISTS fn_tiendas_publicas();
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
