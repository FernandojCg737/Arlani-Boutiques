"""SaaS: "Mi suscripcion" del tenant y enlace publico de cada tienda

- fn_mi_suscripcion(p_empresa_id): la empresa con su suscripcion vigente,
  los dias que faltan para el vencimiento y cuanto usa de su plan
  (sucursales, personal, clientes). La lee el Administrador de la tienda.
- fn_historial_suscripciones(p_empresa_id): planes que tuvo la empresa.
- fn_tienda_publica(p_subdominio): datos publicos de una tienda para su
  enlace /tienda/<subdominio> (sin dominio propio: funciona en Render).
  tiene_catalogo indica si ya tiene productos: el catalogo todavia no es
  multiempresa, asi que por ahora solo la empresa por defecto lo tiene.

Revision ID: b6e1d4f9a250
Revises: a4d8f2c6e317
Create Date: 2026-10-21

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "b6e1d4f9a250"
down_revision = "a4d8f2c6e317"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE OR REPLACE FUNCTION fn_mi_suscripcion(p_empresa_id INTEGER)
RETURNS TABLE (
    empresa_id INTEGER, empresa_nombre VARCHAR, subdominio VARCHAR, color_marca VARCHAR,
    empresa_estado VARCHAR, plan_codigo VARCHAR, plan_nombre VARCHAR, precio_mensual NUMERIC,
    ia_generativa BOOLEAN, periodo VARCHAR, monto NUMERIC, fecha_inicio DATE, fecha_fin DATE,
    dias_restantes INTEGER, sucursales_usadas INTEGER, max_sucursales INTEGER,
    personal INTEGER, clientes INTEGER
) AS $$
    SELECT
        e.id, e.nombre, e.subdominio, e.color_marca, e.estado,
        p.codigo, p.nombre, p.precio_mensual, p.ia_generativa,
        su.periodo, su.monto, su.fecha_inicio, su.fecha_fin,
        CASE WHEN su.fecha_fin IS NULL THEN NULL
             ELSE (su.fecha_fin - (now() AT TIME ZONE 'America/La_Paz')::date) END,
        (SELECT count(*)::int FROM sucursal s WHERE s.empresa_id = e.id AND s.estado = 'activa'),
        p.max_sucursales,
        (SELECT count(*)::int FROM usuario u WHERE u.empresa_id = e.id),
        (SELECT count(*)::int FROM fn_clientes_de_empresa(e.id))
    FROM empresa e
    LEFT JOIN suscripcion su ON su.empresa_id = e.id AND su.estado = 'activa'
    LEFT JOIN plan_suscripcion p ON p.id = su.plan_id
    WHERE e.id = p_empresa_id;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION fn_historial_suscripciones(p_empresa_id INTEGER)
RETURNS TABLE (
    id INTEGER, plan_nombre VARCHAR, periodo VARCHAR, monto NUMERIC,
    fecha_inicio DATE, fecha_fin DATE, estado VARCHAR
) AS $$
    SELECT su.id, p.nombre, su.periodo, su.monto, su.fecha_inicio, su.fecha_fin, su.estado
    FROM suscripcion su JOIN plan_suscripcion p ON p.id = su.plan_id
    WHERE su.empresa_id = p_empresa_id
    ORDER BY su.fecha_registro DESC, su.id DESC;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION fn_tienda_publica(p_subdominio VARCHAR)
RETURNS TABLE (
    id INTEGER, nombre VARCHAR, subdominio VARCHAR, ciudad VARCHAR, color_marca VARCHAR,
    logo_url VARCHAR, estado VARCHAR, tiene_catalogo BOOLEAN
) AS $$
    SELECT e.id, e.nombre, e.subdominio, e.ciudad, e.color_marca, e.logo_url, e.estado,
           e.id = fn_empresa_por_defecto()
    FROM empresa e
    WHERE e.subdominio = lower(trim(p_subdominio));
$$ LANGUAGE sql STABLE;
"""

DOWNGRADE = r"""
DROP FUNCTION IF EXISTS fn_tienda_publica(VARCHAR);
DROP FUNCTION IF EXISTS fn_historial_suscripciones(INTEGER);
DROP FUNCTION IF EXISTS fn_mi_suscripcion(INTEGER);
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
