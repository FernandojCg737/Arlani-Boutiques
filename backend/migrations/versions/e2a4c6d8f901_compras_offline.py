"""Compras sin conexion del cliente (P4 offline)

El cliente arma su compra sin internet (operacion_offline tipo 'pedido').
Al sincronizar no se cobra nada: queda 'por_pagar' (o 'sin_stock' si ya no
hay prendas) y la app le pide pagarla con prioridad, revisando de nuevo
precio y stock. Dos formas:
- en linea: paga con los metodos de la tienda (PayPal, QR...) al volver la
  conexion; recien ahi se registra la venta (origen 'offline').
- contra entrega: la tienda lo habilita como metodo de pago; la venta queda
  pendiente, el stock apartado, y el personal la marca cobrada al entregar
  (o la anula y el stock vuelve).

- venta_digital.carrito_id puede ser NULL (la compra no salio del carrito).
- metodo_pago_empresa: tipo 'contra_entrega'.
- operacion_offline: tipo 'pedido'; estados por_pagar, sin_stock, pagada,
  cancelada.
- sp_crear_venta_contra_entrega, sp_cobrar_contra_entrega, sp_anular_contra_entrega.

Revision ID: e2a4c6d8f901
Revises: c8e0a2b4d567
Create Date: 2026-10-23

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "e2a4c6d8f901"
down_revision = "c8e0a2b4d567"
branch_labels = None
depends_on = None


UPGRADE = r"""
ALTER TABLE venta_digital ALTER COLUMN carrito_id DROP NOT NULL;

ALTER TABLE metodo_pago_empresa DROP CONSTRAINT metodo_pago_empresa_tipo_check;
ALTER TABLE metodo_pago_empresa ADD CONSTRAINT metodo_pago_empresa_tipo_check
    CHECK (tipo IN ('paypal', 'qr', 'transferencia', 'otro', 'contra_entrega'));

ALTER TABLE operacion_offline DROP CONSTRAINT operacion_offline_tipo_check;
ALTER TABLE operacion_offline ADD CONSTRAINT operacion_offline_tipo_check
    CHECK (tipo IN ('venta', 'reserva', 'pedido'));
ALTER TABLE operacion_offline DROP CONSTRAINT operacion_offline_estado_check;
ALTER TABLE operacion_offline ADD CONSTRAINT operacion_offline_estado_check
    CHECK (estado IN ('confirmada', 'conflicto', 'rechazada', 'resuelta', 'anulada',
                      'por_pagar', 'sin_stock', 'pagada', 'cancelada'));

-- Compra sin conexion con pago contra entrega: se registra al confirmarla,
-- aparta el stock y queda pendiente hasta que el personal la cobre.
CREATE OR REPLACE FUNCTION sp_crear_venta_contra_entrega(
    p_cliente_id     INTEGER,
    p_sucursal_id    INTEGER,
    p_items          JSONB,
    p_metodo_pago_id INTEGER
) RETURNS INTEGER AS $$
DECLARE
    v_metodo        metodo_pago_empresa%ROWTYPE;
    v_empresa       INTEGER;
    v_venta_id      INTEGER;
    v_item          JSONB;
    v_precio        NUMERIC(10,2);
    v_total         NUMERIC(10,2) := 0;
    v_inventario_id INTEGER;
    v_stock         INTEGER;
    v_detalle_id    INTEGER;
BEGIN
    SELECT empresa_id INTO v_empresa FROM sucursal WHERE id = p_sucursal_id;
    SELECT * INTO v_metodo FROM metodo_pago_empresa WHERE id = p_metodo_pago_id;
    IF NOT FOUND OR v_metodo.empresa_id <> v_empresa OR NOT v_metodo.activo OR v_metodo.tipo <> 'contra_entrega' THEN
        RAISE EXCEPTION 'metodo_pago_invalido';
    END IF;
    IF NOT fn_empresa_operativa(v_empresa) THEN
        RAISE EXCEPTION 'tienda_no_operativa';
    END IF;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items) LOOP
        SELECT precio INTO v_precio FROM producto
        WHERE id = (v_item->>'producto_id')::INTEGER AND empresa_id = v_empresa;
        IF v_precio IS NULL THEN
            RAISE EXCEPTION 'producto_no_encontrado';
        END IF;
        SELECT id, cantidad INTO v_inventario_id, v_stock FROM inventario
        WHERE producto_id = (v_item->>'producto_id')::INTEGER AND talla_id = (v_item->>'talla_id')::INTEGER
          AND color_id = (v_item->>'color_id')::INTEGER AND sucursal_id = p_sucursal_id
        FOR UPDATE;
        IF v_inventario_id IS NULL OR v_stock < (v_item->>'cantidad')::INTEGER THEN
            RAISE EXCEPTION 'stock_insuficiente';
        END IF;
        v_total := v_total + v_precio * (v_item->>'cantidad')::INTEGER;
    END LOOP;

    INSERT INTO venta (cliente_id, sucursal_id, fecha, total, estado, tipo, origen, sincronizado_en)
    VALUES (p_cliente_id, p_sucursal_id, now(), v_total, 'pendiente', 'venta_digital', 'offline', now())
    RETURNING id INTO v_venta_id;
    INSERT INTO venta_digital (id, carrito_id) VALUES (v_venta_id, NULL);

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items) LOOP
        SELECT precio INTO v_precio FROM producto WHERE id = (v_item->>'producto_id')::INTEGER;
        INSERT INTO item_linea (producto_id, talla_id, color_id, cantidad, tipo)
        VALUES ((v_item->>'producto_id')::INTEGER, (v_item->>'talla_id')::INTEGER,
                (v_item->>'color_id')::INTEGER, (v_item->>'cantidad')::INTEGER, 'detalle_venta_digital')
        RETURNING id INTO v_detalle_id;
        INSERT INTO detalle_venta_digital (id, venta_digital_id, precio_unitario)
        VALUES (v_detalle_id, v_venta_id, v_precio);

        UPDATE inventario SET cantidad = cantidad - (v_item->>'cantidad')::INTEGER
        WHERE producto_id = (v_item->>'producto_id')::INTEGER AND talla_id = (v_item->>'talla_id')::INTEGER
          AND color_id = (v_item->>'color_id')::INTEGER AND sucursal_id = p_sucursal_id
        RETURNING id INTO v_inventario_id;
        INSERT INTO movimiento_inventario (inventario_id, empleado_id, tipo, cantidad, fecha, documento_referencia)
        VALUES (v_inventario_id, NULL, 'salida', (v_item->>'cantidad')::INTEGER, now(),
                'Venta contra entrega #' || v_venta_id);
    END LOOP;

    INSERT INTO pago (venta_id, monto, metodo, estado, fecha, metodo_pago_id)
    VALUES (v_venta_id, v_total, 'contra_entrega', 'pendiente', now(), v_metodo.id);

    RETURN v_venta_id;
END;
$$ LANGUAGE plpgsql;

-- El personal cobro al entregar.
CREATE OR REPLACE FUNCTION sp_cobrar_contra_entrega(p_venta_id INTEGER, p_empleado_id INTEGER)
RETURNS VOID AS $$
BEGIN
    UPDATE pago SET estado = 'completado', revisado_por_id = p_empleado_id, fecha = now()
    WHERE venta_id = p_venta_id AND metodo = 'contra_entrega' AND estado = 'pendiente';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'contra_entrega_no_pendiente';
    END IF;
    UPDATE venta SET estado = 'pagada' WHERE id = p_venta_id;
END;
$$ LANGUAGE plpgsql;

-- No se entrego o no pago: la venta se anula y el stock vuelve.
CREATE OR REPLACE FUNCTION sp_anular_contra_entrega(p_venta_id INTEGER, p_empleado_id INTEGER, p_motivo TEXT)
RETURNS VOID AS $$
DECLARE
    v_sucursal INTEGER;
    v_linea    RECORD;
    v_inventario_id INTEGER;
BEGIN
    UPDATE pago SET estado = 'rechazado', revisado_por_id = p_empleado_id, motivo_rechazo = p_motivo
    WHERE venta_id = p_venta_id AND metodo = 'contra_entrega' AND estado = 'pendiente';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'contra_entrega_no_pendiente';
    END IF;
    SELECT sucursal_id INTO v_sucursal FROM venta WHERE id = p_venta_id;
    FOR v_linea IN
        SELECT il.producto_id, il.talla_id, il.color_id, il.cantidad
        FROM detalle_venta_digital d JOIN item_linea il ON il.id = d.id WHERE d.venta_digital_id = p_venta_id
    LOOP
        UPDATE inventario SET cantidad = cantidad + v_linea.cantidad
        WHERE producto_id = v_linea.producto_id AND talla_id = v_linea.talla_id
          AND color_id = v_linea.color_id AND sucursal_id = v_sucursal
        RETURNING id INTO v_inventario_id;
        INSERT INTO movimiento_inventario (inventario_id, empleado_id, tipo, cantidad, fecha, documento_referencia)
        VALUES (v_inventario_id, p_empleado_id, 'entrada', v_linea.cantidad, now(),
                'Anulación contra entrega #' || p_venta_id);
    END LOOP;
    UPDATE venta SET estado = 'cancelada' WHERE id = p_venta_id;
END;
$$ LANGUAGE plpgsql;
"""

DOWNGRADE = r"""
DROP FUNCTION IF EXISTS sp_anular_contra_entrega(INTEGER, INTEGER, TEXT);
DROP FUNCTION IF EXISTS sp_cobrar_contra_entrega(INTEGER, INTEGER);
DROP FUNCTION IF EXISTS sp_crear_venta_contra_entrega(INTEGER, INTEGER, JSONB, INTEGER);
DELETE FROM operacion_offline WHERE tipo = 'pedido';
ALTER TABLE operacion_offline DROP CONSTRAINT operacion_offline_estado_check;
ALTER TABLE operacion_offline ADD CONSTRAINT operacion_offline_estado_check
    CHECK (estado IN ('confirmada', 'conflicto', 'rechazada', 'resuelta', 'anulada'));
ALTER TABLE operacion_offline DROP CONSTRAINT operacion_offline_tipo_check;
ALTER TABLE operacion_offline ADD CONSTRAINT operacion_offline_tipo_check CHECK (tipo IN ('venta', 'reserva'));
DELETE FROM metodo_pago_empresa WHERE tipo = 'contra_entrega';
ALTER TABLE metodo_pago_empresa DROP CONSTRAINT metodo_pago_empresa_tipo_check;
ALTER TABLE metodo_pago_empresa ADD CONSTRAINT metodo_pago_empresa_tipo_check
    CHECK (tipo IN ('paypal', 'qr', 'transferencia', 'otro'));
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
