"""Venta presencial a un cliente sin cuenta y datos de factura

- venta.factura_nombre / venta.factura_nit: a nombre de quien y con que NIT
  o CI sale la factura (lo dicta el cliente en el mostrador). Sirve tambien
  para un cliente con cuenta que pide factura a otro nombre o NIT.
- Cliente generico "Consumidor final": las ventas de mostrador a personas
  sin cuenta quedan a su nombre (la venta guarda el nombre y el NIT reales).
  Esta inactivo y su clave es aleatoria: nadie puede iniciar sesion con el.
- fn_consumidor_final(): su id.

Revision ID: f2b4d6e8a091
Revises: e0a2c4d6f879
Create Date: 2026-10-23

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "f2b4d6e8a091"
down_revision = "e0a2c4d6f879"
branch_labels = None
depends_on = None

EMAIL = "consumidor.final@arlaniboutiques.com"
# Hash de una clave aleatoria que nadie conoce (la cuenta ademas esta inactiva).
HASH = "$2b$12$vYgCRM5W1C52R4XsuOTdhu2no83jO9cmNwy5OJEZ344D3wlbk8t.S"

UPGRADE = f"""
ALTER TABLE venta
    ADD COLUMN factura_nombre VARCHAR(150),
    ADD COLUMN factura_nit VARCHAR(20);

DO $$
DECLARE
    v_id INTEGER;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM usuario WHERE email = '{EMAIL}') THEN
        v_id := sp_crear_cliente('Consumidor final', '{EMAIL}', '{HASH}', NULL, NULL, 'email');
        UPDATE usuario SET estado = 'inactivo' WHERE id = v_id;
    END IF;
END $$;

CREATE OR REPLACE FUNCTION fn_consumidor_final() RETURNS INTEGER AS $$
    SELECT id FROM usuario WHERE email = '{EMAIL}';
$$ LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public;
"""

DOWNGRADE = f"""
DROP FUNCTION IF EXISTS fn_consumidor_final();
-- Solo se borra si ninguna venta lo usa (con su registro de alta en la bitacora).
DO $$
DECLARE
    v_id INTEGER := (SELECT id FROM usuario WHERE email = '{EMAIL}');
BEGIN
    IF v_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM venta WHERE cliente_id = v_id) THEN
        DELETE FROM bitacora WHERE usuario_id = v_id OR (entidad_afectada IN ('usuario', 'cliente') AND entidad_id = v_id);
        DELETE FROM cliente WHERE id = v_id;
        DELETE FROM usuario WHERE id = v_id;
    END IF;
END $$;
ALTER TABLE venta DROP COLUMN IF EXISTS factura_nit, DROP COLUMN IF EXISTS factura_nombre;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
