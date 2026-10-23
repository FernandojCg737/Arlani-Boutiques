"""CU11: registro de descargas para trabajar sin conexion

descarga_offline: cada vez que el personal descarga el paquete de su
sucursal o un cliente descarga el catalogo (una fila por tienda incluida).
Con esto el SuperAdministrador sigue, por tienda, quien tiene datos en su
dispositivo y de cuando son (CU11), junto a sus sincronizaciones (CU12).

Revision ID: c8e0a2b4d567
Revises: b6d8f0a2c345
Create Date: 2026-10-23

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "c8e0a2b4d567"
down_revision = "b6d8f0a2c345"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE descarga_offline (
    id          SERIAL PRIMARY KEY,
    empresa_id  INTEGER NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    sucursal_id INTEGER REFERENCES sucursal(id) ON DELETE SET NULL,
    usuario_id  INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    tipo        VARCHAR(10) NOT NULL CHECK (tipo IN ('personal', 'cliente')),
    productos   INTEGER NOT NULL DEFAULT 0,
    clientes    INTEGER NOT NULL DEFAULT 0,
    fecha       TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX ix_descarga_offline_empresa ON descarga_offline (empresa_id, fecha DESC);
ALTER TABLE descarga_offline ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_descarga_offline_empresa ON descarga_offline FOR ALL TO arlani_tenant
    USING (empresa_id = fn_empresa_actual()) WITH CHECK (empresa_id = fn_empresa_actual());
"""

DOWNGRADE = r"""
DROP TABLE IF EXISTS descarga_offline;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
