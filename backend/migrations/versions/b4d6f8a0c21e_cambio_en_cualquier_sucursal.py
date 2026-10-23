"""Cambio de prendas con el stock de TODA la tienda

La prenda nueva puede salir de cualquier sucursal activa de la tienda (no
solo de la sucursal de la compra). El cliente elige donde recogerla y ahi
mismo entrega la que devuelve: el cambio queda en esa sucursal
(cambio_prenda.sucursal_id), sale de su stock la prenda nueva y, si es
reingreso, entra ahi la devuelta. Lo atiende el personal de esa sucursal.

sp_solicitar_cambio recibe la sucursal de retiro (p_sucursal_id).

Revision ID: b4d6f8a0c21e
Revises: a2c4e6f8b019
Create Date: 2026-10-23

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "b4d6f8a0c21e"
down_revision = "a2c4e6f8b019"
branch_labels = None
depends_on = None


UPGRADE = r"""
DROP FUNCTION IF EXISTS sp_solicitar_cambio(INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, VARCHAR, TEXT);

CREATE OR REPLACE FUNCTION sp_solicitar_cambio(
    p_cliente_id    INTEGER,
    p_venta_id      INTEGER,
    p_item_linea_id INTEGER,
    p_cantidad      INTEGER,
    p_producto_id   INTEGER,
    p_talla_id      INTEGER,
    p_color_id      INTEGER,
    p_sucursal_id   INTEGER,
    p_motivo        VARCHAR,
    p_observaciones TEXT
) RETURNS INTEGER AS $$
DECLARE
    v_venta    venta%ROWTYPE;
    v_empresa  INTEGER;
    v_item     item_linea%ROWTYPE;
    v_pagado   NUMERIC(10,2);
    v_usadas   INTEGER;
    v_precio   NUMERIC(10,2);
    v_stock    INTEGER;
    v_id       INTEGER;
BEGIN
    SELECT * INTO v_venta FROM venta WHERE id = p_venta_id AND cliente_id = p_cliente_id;
    IF NOT FOUND OR v_venta.estado <> 'pagada' THEN
        RAISE EXCEPTION 'cambio_venta_invalida';
    END IF;
    -- Politica de cambios: 24 horas desde la compra.
    IF now() > v_venta.fecha + interval '24 hours' THEN
        RAISE EXCEPTION 'cambio_fuera_de_plazo';
    END IF;
    SELECT empresa_id INTO v_empresa FROM sucursal WHERE id = v_venta.sucursal_id;
    IF NOT fn_empresa_operativa(v_empresa) THEN
        RAISE EXCEPTION 'tienda_no_operativa';
    END IF;
    -- Se recoge en cualquier sucursal activa de la misma tienda.
    IF NOT EXISTS (SELECT 1 FROM sucursal WHERE id = p_sucursal_id AND empresa_id = v_empresa AND estado = 'activa') THEN
        RAISE EXCEPTION 'cambio_sucursal_invalida';
    END IF;

    -- La linea es de esta venta; precio que el cliente realmente pago.
    SELECT il.* INTO v_item FROM item_linea il WHERE il.id = p_item_linea_id;
    SELECT COALESCE(
        (SELECT precio_unitario FROM detalle_venta_digital WHERE id = p_item_linea_id AND venta_digital_id = p_venta_id),
        (SELECT precio_unitario FROM detalle_venta_presencial WHERE id = p_item_linea_id AND venta_presencial_id = p_venta_id)
    ) INTO v_pagado;
    IF v_pagado IS NULL THEN
        RAISE EXCEPTION 'cambio_venta_invalida';
    END IF;

    SELECT COALESCE(sum(cantidad), 0) INTO v_usadas FROM cambio_prenda
    WHERE item_linea_id = p_item_linea_id AND estado IN ('solicitado', 'por_pagar', 'verificando', 'completado');
    IF p_cantidad IS NULL OR p_cantidad < 1 OR p_cantidad > v_item.cantidad - v_usadas THEN
        RAISE EXCEPTION 'cambio_cantidad_invalida';
    END IF;

    -- La prenda nueva: de la misma tienda, distinta y con stock en la sucursal elegida.
    SELECT precio INTO v_precio FROM producto WHERE id = p_producto_id AND empresa_id = v_empresa AND estado = 'activo';
    IF v_precio IS NULL THEN
        RAISE EXCEPTION 'producto_no_encontrado';
    END IF;
    IF p_producto_id = v_item.producto_id AND p_talla_id = v_item.talla_id AND p_color_id = v_item.color_id THEN
        RAISE EXCEPTION 'cambio_misma_prenda';
    END IF;
    SELECT cantidad INTO v_stock FROM inventario
    WHERE producto_id = p_producto_id AND talla_id = p_talla_id AND color_id = p_color_id
      AND sucursal_id = p_sucursal_id;
    IF COALESCE(v_stock, 0) < p_cantidad THEN
        RAISE EXCEPTION 'stock_insuficiente';
    END IF;

    INSERT INTO cambio_prenda (venta_id, item_linea_id, cliente_id, sucursal_id, cantidad, producto_nuevo_id,
                               talla_nueva_id, color_nuevo_id, precio_pagado, precio_nuevo, diferencia, motivo,
                               observaciones)
    VALUES (p_venta_id, p_item_linea_id, p_cliente_id, p_sucursal_id, p_cantidad, p_producto_id, p_talla_id,
            p_color_id, v_pagado, v_precio, (v_precio - v_pagado) * p_cantidad, p_motivo, NULLIF(trim(p_observaciones), ''))
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$ LANGUAGE plpgsql;
"""

# Vuelve a la version anterior: la prenda nueva sale de la sucursal de la venta.
DOWNGRADE = (
    UPGRADE.replace(
        "    p_sucursal_id   INTEGER,\n", ""
    )
    .replace(
        "DROP FUNCTION IF EXISTS sp_solicitar_cambio(INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, VARCHAR, TEXT);",
        "DROP FUNCTION IF EXISTS sp_solicitar_cambio(INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, VARCHAR, TEXT);",
    )
    .replace(
        "    -- Se recoge en cualquier sucursal activa de la misma tienda.\n"
        "    IF NOT EXISTS (SELECT 1 FROM sucursal WHERE id = p_sucursal_id AND empresa_id = v_empresa AND estado = 'activa') THEN\n"
        "        RAISE EXCEPTION 'cambio_sucursal_invalida';\n"
        "    END IF;\n",
        "",
    )
    .replace("p_sucursal_id", "v_venta.sucursal_id")
)


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
