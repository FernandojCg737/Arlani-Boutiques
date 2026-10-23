"""Direcciones del cliente (con ubicacion GPS) y envio a domicilio

- direccion_cliente: el cliente guarda sus direcciones (alias, texto,
  referencia y ubicacion en el mapa). Son suyas: el personal de las tiendas
  no las ve (RLS sin politica para arlani_tenant).
- venta_envio: si el cliente elige envio a domicilio, la venta guarda una
  COPIA de la direccion y la ubicacion del momento de la compra (si luego
  edita su direccion, la compra no cambia). El personal de la tienda la ve
  solo en sus ventas (RLS por venta) y marca el envio: pendiente -> enviado
  -> entregado. Sin fila = recojo en sucursal.
- fn_ultima_ubicacion_clientes: la ubicacion de la ultima compra con envio
  de cada cliente en CUALQUIER tienda (para el SuperAdministrador, CU03).

Revision ID: c6e8a0b2d43f
Revises: b4d6f8a0c21e
Create Date: 2026-10-23

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "c6e8a0b2d43f"
down_revision = "b4d6f8a0c21e"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE direccion_cliente (
    id              SERIAL PRIMARY KEY,
    cliente_id      INTEGER NOT NULL REFERENCES cliente(id) ON DELETE CASCADE,
    alias           VARCHAR(40) NOT NULL,
    direccion       VARCHAR(250) NOT NULL,
    referencia      VARCHAR(250),
    ciudad          VARCHAR(80),
    latitud         NUMERIC(9,6) NOT NULL CHECK (latitud BETWEEN -90 AND 90),
    longitud        NUMERIC(9,6) NOT NULL CHECK (longitud BETWEEN -180 AND 180),
    predeterminada  BOOLEAN NOT NULL DEFAULT FALSE,
    creado_en       TIMESTAMP NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX ix_direccion_cliente ON direccion_cliente (cliente_id);
CREATE UNIQUE INDEX ux_direccion_predeterminada ON direccion_cliente (cliente_id) WHERE predeterminada;
ALTER TABLE direccion_cliente ENABLE ROW LEVEL SECURITY;

CREATE TABLE venta_envio (
    venta_id      INTEGER PRIMARY KEY REFERENCES venta(id) ON DELETE CASCADE,
    destinatario  VARCHAR(150) NOT NULL,
    telefono      VARCHAR(30),
    direccion     VARCHAR(250) NOT NULL,
    referencia    VARCHAR(250),
    ciudad        VARCHAR(80),
    latitud       NUMERIC(9,6) NOT NULL,
    longitud      NUMERIC(9,6) NOT NULL,
    estado        VARCHAR(20) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'enviado', 'entregado')),
    creado_en     TIMESTAMP NOT NULL DEFAULT now(),
    actualizado_en TIMESTAMP NOT NULL DEFAULT now()
);
ALTER TABLE venta_envio ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_venta_envio_empresa ON venta_envio FOR ALL TO arlani_tenant
    USING (venta_id IN (SELECT id FROM venta)) WITH CHECK (venta_id IN (SELECT id FROM venta));
GRANT SELECT, INSERT, UPDATE ON venta_envio TO arlani_tenant;

CREATE OR REPLACE FUNCTION fn_ultima_ubicacion_clientes(p_cliente_ids INTEGER[])
RETURNS TABLE (cliente_id INTEGER, venta_id INTEGER, fecha TIMESTAMP, tienda_nombre VARCHAR, direccion VARCHAR,
               referencia VARCHAR, ciudad VARCHAR, latitud NUMERIC, longitud NUMERIC) AS $$
    SELECT DISTINCT ON (v.cliente_id) v.cliente_id, v.id, v.fecha, e.nombre, ve.direccion, ve.referencia, ve.ciudad,
           ve.latitud, ve.longitud
    FROM venta_envio ve
    JOIN venta v ON v.id = ve.venta_id
    JOIN sucursal s ON s.id = v.sucursal_id
    JOIN empresa e ON e.id = s.empresa_id
    WHERE v.cliente_id = ANY(p_cliente_ids)
    ORDER BY v.cliente_id, v.fecha DESC;
$$ LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public;
-- Solo la usa el backend como dueno (SuperAdministrador); el personal de
-- una tienda (rol arlani_tenant) no puede ver ubicaciones de otras tiendas.
REVOKE EXECUTE ON FUNCTION fn_ultima_ubicacion_clientes(INTEGER[]) FROM PUBLIC, arlani_tenant;
REVOKE ALL ON direccion_cliente FROM arlani_tenant;
"""

DOWNGRADE = r"""
DROP FUNCTION IF EXISTS fn_ultima_ubicacion_clientes(INTEGER[]);
DROP TABLE IF EXISTS venta_envio;
DROP TABLE IF EXISTS direccion_cliente;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
