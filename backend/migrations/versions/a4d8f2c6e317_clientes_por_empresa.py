"""SaaS: clientes por empresa (CU03 del 1er parcial)

Los clientes son de la plataforma (una sola cuenta sirve para comprar en
cualquier boutique). Una tienda solo ve a los clientes que trabajaron con
ella; el SuperAdministrador ve a todos.

fn_clientes_de_empresa(p_empresa_id): un cliente "trabajo con la tienda"
si compro o reservo en una de sus sucursales, tiene prendas de sus
sucursales en el carrito, uso el probador con sus productos o lo registro el
personal de esa tienda. Devuelve tambien cuanto hizo, para mostrarlo.

Revision ID: a4d8f2c6e317
Revises: f2b7c4e1d905
Create Date: 2026-10-21

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "a4d8f2c6e317"
down_revision = "f2b7c4e1d905"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE OR REPLACE FUNCTION fn_clientes_de_empresa(p_empresa_id INTEGER)
RETURNS TABLE (
    cliente_id INTEGER, compras INTEGER, reservas INTEGER, en_carrito INTEGER,
    usos_probador INTEGER, ultima_interaccion TIMESTAMP
) AS $$
    WITH interacciones AS (
        SELECT v.cliente_id, 'compra' AS tipo, v.fecha
        FROM venta v JOIN sucursal s ON s.id = v.sucursal_id
        WHERE s.empresa_id = p_empresa_id
        UNION ALL
        SELECT r.cliente_id, 'reserva', r.fecha_creacion
        FROM reserva r JOIN sucursal s ON s.id = r.sucursal_id
        WHERE s.empresa_id = p_empresa_id
        UNION ALL
        SELECT c.cliente_id, 'carrito', c.fecha_actualizacion
        FROM carrito c
        WHERE EXISTS (SELECT 1 FROM detalle_carrito dc JOIN sucursal s ON s.id = dc.sucursal_id
                      WHERE dc.carrito_id = c.id AND s.empresa_id = p_empresa_id)
        UNION ALL
        SELECT u.usuario_id, 'probador', u.fecha
        FROM uso_ar_prenda u JOIN cliente cl ON cl.id = u.usuario_id
        WHERE fn_empresa_de_producto(u.producto_id) = p_empresa_id
        UNION ALL
        -- Registrado por el personal de la tienda (el alta queda en la
        -- bitacora asociada a la empresa de quien lo creo).
        SELECT b.entidad_id, 'alta', b.fecha
        FROM bitacora b JOIN cliente cl ON cl.id = b.entidad_id
        WHERE b.entidad_afectada = 'usuario' AND b.accion = 'CREAR' AND b.empresa_id = p_empresa_id
    )
    SELECT i.cliente_id,
           count(*) FILTER (WHERE i.tipo = 'compra')::int,
           count(*) FILTER (WHERE i.tipo = 'reserva')::int,
           count(*) FILTER (WHERE i.tipo = 'carrito')::int,
           count(*) FILTER (WHERE i.tipo = 'probador')::int,
           max(i.fecha)
    FROM interacciones i
    WHERE i.cliente_id IS NOT NULL
    GROUP BY i.cliente_id;
$$ LANGUAGE sql STABLE;
"""

DOWNGRADE = "DROP FUNCTION IF EXISTS fn_clientes_de_empresa(INTEGER);"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
