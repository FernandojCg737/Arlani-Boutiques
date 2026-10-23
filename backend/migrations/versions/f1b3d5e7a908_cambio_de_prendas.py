"""CU Cambio de prendas (politica de cambios de cada tienda)

- cambio_prenda: el cliente pide cambiar una prenda comprada por otra de la
  misma tienda, dentro de las 48 horas de su compra. La prenda nueva sale de
  la sucursal de la venta (debe tener stock). El precio se compara con lo que
  el cliente PAGO (precio_unitario de la venta, aunque estuviera en oferta)
  contra el precio actual de la prenda nueva:
    diferencia = (precio_nuevo - precio_pagado) * cantidad
    * > 0: el cliente paga la diferencia con los metodos de la tienda
      (PayPal se confirma solo; con comprobante lo aprueba el personal).
    * < 0: se le devuelve la diferencia (PayPal si pago con PayPal; si no,
      en tienda).
  Estados: solicitado -> (personal) rechazado | por_pagar | completado;
  por_pagar -> verificando (comprobante) -> completado; el cliente puede
  cancelar mientras no se complete.
- reposicion_prenda: que pasa con la prenda devuelta: reingreso (vuelve al
  stock de la sucursal), merma (dañada, se da de baja) o proveedor (se le
  devuelve al proveedor).
- Al completarse: sale del stock la prenda nueva y, si es reingreso, entra
  la devuelta (movimiento_inventario). Si la venta la cobro Arlani ("Pagar
  todo") y se devuelve diferencia por PayPal, la tienda la debe (cuenta).

Revision ID: f1b3d5e7a908
Revises: e9a1c3d5f786
Create Date: 2026-10-23

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "f1b3d5e7a908"
down_revision = "e9a1c3d5f786"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE cambio_prenda (
    id                SERIAL PRIMARY KEY,
    venta_id          INTEGER NOT NULL REFERENCES venta(id) ON DELETE CASCADE,
    item_linea_id     INTEGER NOT NULL REFERENCES item_linea(id) ON DELETE CASCADE,
    cliente_id        INTEGER NOT NULL REFERENCES cliente(id),
    sucursal_id       INTEGER NOT NULL REFERENCES sucursal(id),
    cantidad          INTEGER NOT NULL CHECK (cantidad > 0),
    producto_nuevo_id INTEGER NOT NULL REFERENCES producto(id),
    talla_nueva_id    INTEGER NOT NULL REFERENCES talla(id),
    color_nuevo_id    INTEGER NOT NULL REFERENCES color(id),
    precio_pagado     NUMERIC(10,2) NOT NULL,
    precio_nuevo      NUMERIC(10,2) NOT NULL,
    diferencia        NUMERIC(10,2) NOT NULL,
    motivo            VARCHAR(20) NOT NULL CHECK (motivo IN ('talla', 'color', 'modelo', 'defecto', 'otro')),
    observaciones     TEXT,
    estado            VARCHAR(20) NOT NULL DEFAULT 'solicitado'
                      CHECK (estado IN ('solicitado', 'por_pagar', 'verificando', 'completado', 'rechazado', 'cancelado')),
    destino           VARCHAR(20) CHECK (destino IN ('reingreso', 'merma', 'proveedor')),
    motivo_rechazo    TEXT,
    metodo_pago_id    INTEGER REFERENCES metodo_pago_empresa(id) ON DELETE SET NULL,
    comprobante_url   VARCHAR(500),
    paypal_order_id   VARCHAR(64),
    captura_id        VARCHAR(64),
    reembolso_metodo  VARCHAR(20) CHECK (reembolso_metodo IN ('paypal', 'en_tienda')),
    empleado_id       INTEGER REFERENCES empleado(id),
    fecha_solicitud   TIMESTAMP NOT NULL DEFAULT now(),
    fecha_resolucion  TIMESTAMP,
    fecha_completado  TIMESTAMP
);
-- Un solo cambio abierto por linea de venta.
CREATE UNIQUE INDEX ux_cambio_abierto ON cambio_prenda (item_linea_id)
    WHERE estado IN ('solicitado', 'por_pagar', 'verificando');
CREATE INDEX ix_cambio_sucursal ON cambio_prenda (sucursal_id, fecha_solicitud DESC);
CREATE INDEX ix_cambio_cliente ON cambio_prenda (cliente_id, fecha_solicitud DESC);

CREATE TABLE reposicion_prenda (
    id            SERIAL PRIMARY KEY,
    cambio_id     INTEGER REFERENCES cambio_prenda(id) ON DELETE CASCADE,
    devolucion_id INTEGER REFERENCES devolucion(id) ON DELETE CASCADE,
    sucursal_id   INTEGER NOT NULL REFERENCES sucursal(id),
    producto_id   INTEGER NOT NULL REFERENCES producto(id),
    talla_id      INTEGER NOT NULL REFERENCES talla(id),
    color_id      INTEGER NOT NULL REFERENCES color(id),
    cantidad      INTEGER NOT NULL CHECK (cantidad > 0),
    destino       VARCHAR(20) NOT NULL CHECK (destino IN ('reingreso', 'merma', 'proveedor')),
    proveedor_id  INTEGER REFERENCES proveedor(id),
    observacion   TEXT,
    empleado_id   INTEGER REFERENCES empleado(id),
    fecha         TIMESTAMP NOT NULL DEFAULT now(),
    CHECK (cambio_id IS NOT NULL OR devolucion_id IS NOT NULL)
);
CREATE INDEX ix_reposicion_sucursal ON reposicion_prenda (sucursal_id, fecha DESC);

ALTER TABLE cambio_prenda ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_cambio_prenda_empresa ON cambio_prenda FOR ALL TO arlani_tenant
    USING (sucursal_id IN (SELECT id FROM sucursal WHERE empresa_id = fn_empresa_actual()))
    WITH CHECK (sucursal_id IN (SELECT id FROM sucursal WHERE empresa_id = fn_empresa_actual()));
ALTER TABLE reposicion_prenda ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_reposicion_prenda_empresa ON reposicion_prenda FOR ALL TO arlani_tenant
    USING (sucursal_id IN (SELECT id FROM sucursal WHERE empresa_id = fn_empresa_actual()))
    WITH CHECK (sucursal_id IN (SELECT id FROM sucursal WHERE empresa_id = fn_empresa_actual()));
GRANT SELECT, INSERT, UPDATE ON cambio_prenda, reposicion_prenda TO arlani_tenant;
GRANT USAGE, SELECT, UPDATE ON SEQUENCE cambio_prenda_id_seq, reposicion_prenda_id_seq TO arlani_tenant;

ALTER TABLE cuenta_tienda_movimiento ADD COLUMN cambio_id INTEGER REFERENCES cambio_prenda(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX ux_cuenta_reembolso_cambio ON cuenta_tienda_movimiento (cambio_id) WHERE tipo = 'reembolso';

-- ------------------------------------------------------------- solicitar
CREATE OR REPLACE FUNCTION sp_solicitar_cambio(
    p_cliente_id    INTEGER,
    p_venta_id      INTEGER,
    p_item_linea_id INTEGER,
    p_cantidad      INTEGER,
    p_producto_id   INTEGER,
    p_talla_id      INTEGER,
    p_color_id      INTEGER,
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
    -- Politica de cambios: 48 horas desde la compra.
    IF now() > v_venta.fecha + interval '48 hours' THEN
        RAISE EXCEPTION 'cambio_fuera_de_plazo';
    END IF;
    SELECT empresa_id INTO v_empresa FROM sucursal WHERE id = v_venta.sucursal_id;
    IF NOT fn_empresa_operativa(v_empresa) THEN
        RAISE EXCEPTION 'tienda_no_operativa';
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

    -- La prenda nueva: de la misma tienda, distinta y con stock en la sucursal.
    SELECT precio INTO v_precio FROM producto WHERE id = p_producto_id AND empresa_id = v_empresa AND estado = 'activo';
    IF v_precio IS NULL THEN
        RAISE EXCEPTION 'producto_no_encontrado';
    END IF;
    IF p_producto_id = v_item.producto_id AND p_talla_id = v_item.talla_id AND p_color_id = v_item.color_id THEN
        RAISE EXCEPTION 'cambio_misma_prenda';
    END IF;
    SELECT cantidad INTO v_stock FROM inventario
    WHERE producto_id = p_producto_id AND talla_id = p_talla_id AND color_id = p_color_id
      AND sucursal_id = v_venta.sucursal_id;
    IF COALESCE(v_stock, 0) < p_cantidad THEN
        RAISE EXCEPTION 'stock_insuficiente';
    END IF;

    INSERT INTO cambio_prenda (venta_id, item_linea_id, cliente_id, sucursal_id, cantidad, producto_nuevo_id,
                               talla_nueva_id, color_nuevo_id, precio_pagado, precio_nuevo, diferencia, motivo,
                               observaciones)
    VALUES (p_venta_id, p_item_linea_id, p_cliente_id, v_venta.sucursal_id, p_cantidad, p_producto_id, p_talla_id,
            p_color_id, v_pagado, v_precio, (v_precio - v_pagado) * p_cantidad, p_motivo, NULLIF(trim(p_observaciones), ''))
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------------------------- completar
-- Mueve el stock: sale la prenda nueva y la devuelta va a su destino.
CREATE OR REPLACE FUNCTION sp_completar_cambio(p_cambio_id INTEGER, p_empleado_id INTEGER) RETURNS VOID AS $$
DECLARE
    v_c      cambio_prenda%ROWTYPE;
    v_item   item_linea%ROWTYPE;
    v_inv    INTEGER;
    v_stock  INTEGER;
    v_liq    INTEGER;
    v_empresa INTEGER;
BEGIN
    SELECT * INTO v_c FROM cambio_prenda WHERE id = p_cambio_id FOR UPDATE;
    SELECT * INTO v_item FROM item_linea WHERE id = v_c.item_linea_id;

    SELECT id, cantidad INTO v_inv, v_stock FROM inventario
    WHERE producto_id = v_c.producto_nuevo_id AND talla_id = v_c.talla_nueva_id AND color_id = v_c.color_nuevo_id
      AND sucursal_id = v_c.sucursal_id
    FOR UPDATE;
    IF v_inv IS NULL OR v_stock < v_c.cantidad THEN
        RAISE EXCEPTION 'stock_insuficiente';
    END IF;
    UPDATE inventario SET cantidad = cantidad - v_c.cantidad WHERE id = v_inv;
    INSERT INTO movimiento_inventario (inventario_id, empleado_id, tipo, cantidad, fecha, documento_referencia)
    VALUES (v_inv, p_empleado_id, 'salida', v_c.cantidad, now(),
            'Cambio de prenda #' || v_c.id || ' (venta #' || v_c.venta_id || ')');

    INSERT INTO reposicion_prenda (cambio_id, sucursal_id, producto_id, talla_id, color_id, cantidad, destino,
                                   proveedor_id, empleado_id, observacion)
    SELECT v_c.id, v_c.sucursal_id, v_item.producto_id, v_item.talla_id, v_item.color_id, v_c.cantidad,
           COALESCE(v_c.destino, 'reingreso'),
           CASE WHEN v_c.destino = 'proveedor' THEN p.proveedor_id END, p_empleado_id,
           'Prenda devuelta en el cambio #' || v_c.id
    FROM producto p WHERE p.id = v_item.producto_id;

    IF COALESCE(v_c.destino, 'reingreso') = 'reingreso' THEN
        SELECT id INTO v_inv FROM inventario
        WHERE producto_id = v_item.producto_id AND talla_id = v_item.talla_id AND color_id = v_item.color_id
          AND sucursal_id = v_c.sucursal_id
        FOR UPDATE;
        IF v_inv IS NULL THEN
            INSERT INTO inventario (producto_id, talla_id, color_id, sucursal_id, cantidad, estado)
            VALUES (v_item.producto_id, v_item.talla_id, v_item.color_id, v_c.sucursal_id, 0, 'disponible')
            RETURNING id INTO v_inv;
        END IF;
        UPDATE inventario SET cantidad = cantidad + v_c.cantidad WHERE id = v_inv;
        INSERT INTO movimiento_inventario (inventario_id, empleado_id, tipo, cantidad, fecha, documento_referencia)
        VALUES (v_inv, p_empleado_id, 'entrada', v_c.cantidad, now(),
                'Reingreso por cambio de prenda #' || v_c.id);
    END IF;

    -- Diferencia devuelta por PayPal de una venta cobrada por Arlani: la debe la tienda.
    IF v_c.diferencia < 0 AND v_c.reembolso_metodo = 'paypal' THEN
        SELECT p.liquidacion_id INTO v_liq FROM pago p WHERE p.venta_id = v_c.venta_id;
        IF v_liq IS NOT NULL THEN
            SELECT empresa_id INTO v_empresa FROM sucursal WHERE id = v_c.sucursal_id;
            INSERT INTO cuenta_tienda_movimiento (empresa_id, tipo, venta_id, monto_bob, descripcion, liquidacion_id, cambio_id)
            VALUES (v_empresa, 'reembolso', v_c.venta_id, -v_c.diferencia,
                    'Diferencia devuelta del cambio #' || v_c.id || ' pagada por Arlani', v_liq, v_c.id)
            ON CONFLICT (cambio_id) WHERE tipo = 'reembolso' DO NOTHING;
        END IF;
    END IF;

    UPDATE cambio_prenda
       SET estado = 'completado', fecha_completado = now(), empleado_id = COALESCE(p_empleado_id, empleado_id),
           motivo_rechazo = NULL
     WHERE id = v_c.id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- -------------------------------------------------------------- aprobar
CREATE OR REPLACE FUNCTION sp_aprobar_cambio(
    p_cambio_id        INTEGER,
    p_empleado_id      INTEGER,
    p_destino          VARCHAR,
    p_observacion      TEXT,
    p_reembolso_metodo VARCHAR
) RETURNS VARCHAR AS $$
DECLARE
    v_c     cambio_prenda%ROWTYPE;
    v_stock INTEGER;
BEGIN
    SELECT * INTO v_c FROM cambio_prenda WHERE id = p_cambio_id FOR UPDATE;
    IF NOT FOUND OR v_c.estado <> 'solicitado' THEN
        RAISE EXCEPTION 'cambio_no_pendiente';
    END IF;
    IF p_destino NOT IN ('reingreso', 'merma', 'proveedor') THEN
        RAISE EXCEPTION 'destino_invalido';
    END IF;
    SELECT cantidad INTO v_stock FROM inventario
    WHERE producto_id = v_c.producto_nuevo_id AND talla_id = v_c.talla_nueva_id AND color_id = v_c.color_nuevo_id
      AND sucursal_id = v_c.sucursal_id;
    IF COALESCE(v_stock, 0) < v_c.cantidad THEN
        RAISE EXCEPTION 'stock_insuficiente';
    END IF;

    UPDATE cambio_prenda
       SET destino = p_destino, empleado_id = p_empleado_id, fecha_resolucion = now(),
           observaciones = CASE WHEN NULLIF(trim(p_observacion), '') IS NULL THEN observaciones
                                ELSE concat_ws(E'\n', observaciones, 'Tienda: ' || trim(p_observacion)) END,
           reembolso_metodo = CASE WHEN diferencia < 0 THEN p_reembolso_metodo END
     WHERE id = p_cambio_id;

    IF v_c.diferencia > 0 THEN
        UPDATE cambio_prenda SET estado = 'por_pagar' WHERE id = p_cambio_id;
        RETURN 'por_pagar';
    END IF;
    PERFORM sp_completar_cambio(p_cambio_id, p_empleado_id);
    RETURN 'completado';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sp_rechazar_cambio(p_cambio_id INTEGER, p_empleado_id INTEGER, p_motivo TEXT) RETURNS VOID AS $$
BEGIN
    IF p_motivo IS NULL OR length(trim(p_motivo)) < 3 THEN
        RAISE EXCEPTION 'motivo_rechazo_requerido';
    END IF;
    UPDATE cambio_prenda
       SET estado = 'rechazado', motivo_rechazo = trim(p_motivo), empleado_id = p_empleado_id, fecha_resolucion = now()
     WHERE id = p_cambio_id AND estado IN ('solicitado', 'por_pagar', 'verificando');
    IF NOT FOUND THEN
        RAISE EXCEPTION 'cambio_no_pendiente';
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sp_cancelar_cambio(p_cambio_id INTEGER, p_cliente_id INTEGER) RETURNS VOID AS $$
BEGIN
    UPDATE cambio_prenda SET estado = 'cancelado'
     WHERE id = p_cambio_id AND cliente_id = p_cliente_id AND estado IN ('solicitado', 'por_pagar');
    IF NOT FOUND THEN
        RAISE EXCEPTION 'cambio_no_pendiente';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------- pagar la diferencia (cliente)
CREATE OR REPLACE FUNCTION sp_pagar_diferencia_cambio(
    p_cambio_id       INTEGER,
    p_cliente_id      INTEGER,
    p_metodo_pago_id  INTEGER,
    p_comprobante_url VARCHAR,
    p_order_id        VARCHAR,
    p_captura_id      VARCHAR
) RETURNS VARCHAR AS $$
DECLARE
    v_c       cambio_prenda%ROWTYPE;
    v_metodo  metodo_pago_empresa%ROWTYPE;
BEGIN
    SELECT * INTO v_c FROM cambio_prenda WHERE id = p_cambio_id AND cliente_id = p_cliente_id FOR UPDATE;
    IF NOT FOUND OR v_c.estado <> 'por_pagar' THEN
        RAISE EXCEPTION 'cambio_sin_pago_pendiente';
    END IF;
    SELECT * INTO v_metodo FROM metodo_pago_empresa WHERE id = p_metodo_pago_id;
    IF NOT FOUND OR NOT v_metodo.activo
       OR v_metodo.empresa_id <> (SELECT empresa_id FROM sucursal WHERE id = v_c.sucursal_id) THEN
        RAISE EXCEPTION 'metodo_pago_invalido';
    END IF;

    UPDATE cambio_prenda
       SET metodo_pago_id = v_metodo.id, comprobante_url = p_comprobante_url, paypal_order_id = p_order_id,
           captura_id = p_captura_id, motivo_rechazo = NULL
     WHERE id = p_cambio_id;
    IF v_metodo.tipo = 'paypal' THEN
        IF p_captura_id IS NULL THEN
            RAISE EXCEPTION 'pago_requerido';
        END IF;
        PERFORM sp_completar_cambio(p_cambio_id, NULL);
        RETURN 'completado';
    END IF;
    IF p_comprobante_url IS NULL THEN
        RAISE EXCEPTION 'comprobante_requerido';
    END IF;
    UPDATE cambio_prenda SET estado = 'verificando' WHERE id = p_cambio_id;
    RETURN 'verificando';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sp_revisar_pago_cambio(
    p_cambio_id   INTEGER,
    p_empleado_id INTEGER,
    p_aprobar     BOOLEAN,
    p_motivo      TEXT
) RETURNS VOID AS $$
BEGIN
    PERFORM 1 FROM cambio_prenda WHERE id = p_cambio_id AND estado = 'verificando' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'pago_no_verificable';
    END IF;
    IF p_aprobar THEN
        PERFORM sp_completar_cambio(p_cambio_id, p_empleado_id);
        RETURN;
    END IF;
    IF p_motivo IS NULL OR length(trim(p_motivo)) < 3 THEN
        RAISE EXCEPTION 'motivo_rechazo_requerido';
    END IF;
    -- El comprobante no vale: el cliente puede volver a pagar.
    UPDATE cambio_prenda
       SET estado = 'por_pagar', motivo_rechazo = trim(p_motivo), comprobante_url = NULL, empleado_id = p_empleado_id
     WHERE id = p_cambio_id;
END;
$$ LANGUAGE plpgsql;
"""


DOWNGRADE = r"""
DROP FUNCTION IF EXISTS sp_revisar_pago_cambio(INTEGER, INTEGER, BOOLEAN, TEXT);
DROP FUNCTION IF EXISTS sp_pagar_diferencia_cambio(INTEGER, INTEGER, INTEGER, VARCHAR, VARCHAR, VARCHAR);
DROP FUNCTION IF EXISTS sp_cancelar_cambio(INTEGER, INTEGER);
DROP FUNCTION IF EXISTS sp_rechazar_cambio(INTEGER, INTEGER, TEXT);
DROP FUNCTION IF EXISTS sp_aprobar_cambio(INTEGER, INTEGER, VARCHAR, TEXT, VARCHAR);
DROP FUNCTION IF EXISTS sp_completar_cambio(INTEGER, INTEGER);
DROP FUNCTION IF EXISTS sp_solicitar_cambio(INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, INTEGER, VARCHAR, TEXT);
DELETE FROM cuenta_tienda_movimiento WHERE cambio_id IS NOT NULL;
DROP INDEX IF EXISTS ux_cuenta_reembolso_cambio;
ALTER TABLE cuenta_tienda_movimiento DROP COLUMN IF EXISTS cambio_id;
DROP TABLE IF EXISTS reposicion_prenda;
DROP TABLE IF EXISTS cambio_prenda;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
