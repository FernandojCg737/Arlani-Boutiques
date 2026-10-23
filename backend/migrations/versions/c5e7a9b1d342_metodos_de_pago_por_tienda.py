"""SaaS: metodos de pago y datos de facturacion de cada tienda

- metodo_pago_empresa: cada tienda registra como cobra.
    * paypal: con SUS credenciales (Client ID y Secret cifrado); el cobro se
      confirma solo.
    * qr, transferencia y otro: el cliente sube su comprobante y la venta
      queda "verificando" hasta que el Administrador, Encargado o Cajero la
      apruebe o la rechace (con motivo).
  Una sola cuenta de PayPal por tienda. RLS: cada tienda ve solo los suyos.
- empresa: razon social, NIT, direccion y telefono para sus facturas.
- pago: con que metodo de la tienda se pago y, si se rechazo, por que.
- sp_crear_venta_tienda: venta digital de UNA tienda con uno de sus metodos.
  Solo saca del carrito las lineas compradas (el resto de tiendas sigue en
  el carrito); cuando no queda nada, el carrito pasa a 'convertido'.
- sp_aprobar_pago_comprobante / sp_rechazar_pago_comprobante: como las de
  QR, para cualquier metodo con comprobante.

Revision ID: c5e7a9b1d342
Revises: b3d5f7a9c120
Create Date: 2026-10-22

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "c5e7a9b1d342"
down_revision = "b3d5f7a9c120"
branch_labels = None
depends_on = None


UPGRADE = r"""
-- ------------------------------------------------- datos de facturacion
ALTER TABLE empresa
    ADD COLUMN razon_social VARCHAR(150),
    ADD COLUMN nit VARCHAR(20),
    ADD COLUMN direccion_fiscal VARCHAR(200),
    ADD COLUMN telefono VARCHAR(30);

-- ------------------------------------------------------- metodos de pago
CREATE TABLE metodo_pago_empresa (
    id                    SERIAL PRIMARY KEY,
    empresa_id            INTEGER NOT NULL DEFAULT fn_empresa_para_alta() REFERENCES empresa(id) ON DELETE CASCADE,
    tipo                  VARCHAR(20) NOT NULL CHECK (tipo IN ('paypal', 'qr', 'transferencia', 'otro')),
    nombre                VARCHAR(80) NOT NULL,
    instrucciones         TEXT,
    activo                BOOLEAN NOT NULL DEFAULT TRUE,
    orden                 INTEGER NOT NULL DEFAULT 0,
    -- PayPal de la tienda (el Secret va cifrado; nunca se devuelve).
    paypal_client_id      VARCHAR(200),
    paypal_secret_cifrado TEXT,
    paypal_modo           VARCHAR(10) CHECK (paypal_modo IN ('sandbox', 'live')),
    paypal_email          VARCHAR(150),
    -- QR / transferencia
    qr_url                VARCHAR(500),
    banco                 VARCHAR(80),
    numero_cuenta         VARCHAR(40),
    tipo_cuenta           VARCHAR(20),
    titular               VARCHAR(120),
    documento_titular     VARCHAR(30),
    creado_en             TIMESTAMP NOT NULL DEFAULT now(),
    actualizado_en        TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT ck_metodo_paypal_completo CHECK (
        tipo <> 'paypal' OR (paypal_client_id IS NOT NULL AND paypal_secret_cifrado IS NOT NULL AND paypal_modo IS NOT NULL)
    ),
    CONSTRAINT ck_metodo_qr_con_imagen CHECK (tipo <> 'qr' OR qr_url IS NOT NULL),
    CONSTRAINT ck_metodo_transferencia_completa CHECK (
        tipo <> 'transferencia' OR (banco IS NOT NULL AND numero_cuenta IS NOT NULL AND titular IS NOT NULL)
    )
);
CREATE UNIQUE INDEX ux_metodo_pago_un_paypal ON metodo_pago_empresa (empresa_id) WHERE tipo = 'paypal';
CREATE INDEX ix_metodo_pago_empresa ON metodo_pago_empresa (empresa_id, activo, orden);

ALTER TABLE metodo_pago_empresa ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_metodo_pago_empresa_empresa ON metodo_pago_empresa FOR ALL TO arlani_tenant
    USING (empresa_id = fn_empresa_actual()) WITH CHECK (empresa_id = fn_empresa_actual());
GRANT SELECT, INSERT, UPDATE, DELETE ON metodo_pago_empresa TO arlani_tenant;
GRANT USAGE, SELECT, UPDATE ON SEQUENCE metodo_pago_empresa_id_seq TO arlani_tenant;

-- ---------------------------------------------------------------- pago
ALTER TABLE pago
    ADD COLUMN metodo_pago_id INTEGER REFERENCES metodo_pago_empresa(id) ON DELETE SET NULL,
    ADD COLUMN motivo_rechazo TEXT;

-- --------------------------------------------- venta de UNA tienda
CREATE OR REPLACE FUNCTION sp_crear_venta_tienda(
    p_cliente_id INTEGER, p_sucursal_id INTEGER, p_carrito_id INTEGER, p_items JSONB,
    p_detalle_ids INTEGER[], p_metodo_pago_id INTEGER, p_referencia_externa VARCHAR,
    p_comprobante_url VARCHAR
) RETURNS INTEGER AS $$
DECLARE
    v_metodo        metodo_pago_empresa%ROWTYPE;
    v_empresa       INTEGER;
    v_pagada        BOOLEAN;
    v_venta_id      INTEGER;
    v_pago_id       INTEGER;
    v_item          JSONB;
    v_precio        NUMERIC(10,2);
    v_total         NUMERIC(10,2) := 0;
    v_inventario_id INTEGER;
    v_stock         INTEGER;
    v_detalle_id    INTEGER;
BEGIN
    SELECT empresa_id INTO v_empresa FROM sucursal WHERE id = p_sucursal_id;
    SELECT * INTO v_metodo FROM metodo_pago_empresa WHERE id = p_metodo_pago_id;
    IF NOT FOUND OR v_metodo.empresa_id <> v_empresa OR NOT v_metodo.activo THEN
        RAISE EXCEPTION 'metodo_pago_invalido';
    END IF;
    IF NOT fn_empresa_operativa(v_empresa) THEN
        RAISE EXCEPTION 'tienda_no_operativa';
    END IF;
    v_pagada := v_metodo.tipo = 'paypal';
    IF v_pagada AND p_referencia_externa IS NULL THEN
        RAISE EXCEPTION 'pago_requerido';
    END IF;
    IF NOT v_pagada AND p_comprobante_url IS NULL THEN
        RAISE EXCEPTION 'comprobante_requerido';
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

    -- Con PayPal el cobro ya se confirmo: pagada y se descuenta el stock.
    -- Con comprobante queda pendiente; el stock se descuenta al aprobarla.
    INSERT INTO venta (cliente_id, sucursal_id, fecha, total, estado, tipo)
    VALUES (p_cliente_id, p_sucursal_id, now(), v_total,
            CASE WHEN v_pagada THEN 'pagada' ELSE 'pendiente' END, 'venta_digital')
    RETURNING id INTO v_venta_id;
    INSERT INTO venta_digital (id, carrito_id) VALUES (v_venta_id, p_carrito_id);

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items) LOOP
        SELECT precio INTO v_precio FROM producto WHERE id = (v_item->>'producto_id')::INTEGER;
        INSERT INTO item_linea (producto_id, talla_id, color_id, cantidad, tipo)
        VALUES ((v_item->>'producto_id')::INTEGER, (v_item->>'talla_id')::INTEGER,
                (v_item->>'color_id')::INTEGER, (v_item->>'cantidad')::INTEGER, 'detalle_venta_digital')
        RETURNING id INTO v_detalle_id;
        INSERT INTO detalle_venta_digital (id, venta_digital_id, precio_unitario)
        VALUES (v_detalle_id, v_venta_id, v_precio);

        IF v_pagada THEN
            UPDATE inventario SET cantidad = cantidad - (v_item->>'cantidad')::INTEGER
            WHERE producto_id = (v_item->>'producto_id')::INTEGER AND talla_id = (v_item->>'talla_id')::INTEGER
              AND color_id = (v_item->>'color_id')::INTEGER AND sucursal_id = p_sucursal_id
            RETURNING id INTO v_inventario_id;
            INSERT INTO movimiento_inventario (inventario_id, empleado_id, tipo, cantidad, fecha, documento_referencia)
            VALUES (v_inventario_id, NULL, 'salida', (v_item->>'cantidad')::INTEGER, now(),
                    'Venta digital #' || v_venta_id || ' (PayPal ' || p_referencia_externa || ')');
        END IF;
    END LOOP;

    INSERT INTO pago (venta_id, monto, metodo, estado, fecha, comprobante_url, metodo_pago_id)
    VALUES (v_venta_id, v_total, v_metodo.tipo, CASE WHEN v_pagada THEN 'completado' ELSE 'verificando' END,
            now(), p_comprobante_url, v_metodo.id)
    RETURNING id INTO v_pago_id;
    IF v_pagada THEN
        INSERT INTO transaccion (pago_id, pasarela, referencia_externa, estado, fecha)
        VALUES (v_pago_id, 'paypal', p_referencia_externa, 'completado', now());
    END IF;

    -- Solo salen del carrito las lineas compradas; lo de otras tiendas queda.
    DELETE FROM detalle_carrito WHERE carrito_id = p_carrito_id AND id = ANY(p_detalle_ids);
    DELETE FROM item_linea il WHERE il.id = ANY(p_detalle_ids)
      AND NOT EXISTS (SELECT 1 FROM detalle_carrito d WHERE d.id = il.id);
    IF NOT EXISTS (SELECT 1 FROM detalle_carrito WHERE carrito_id = p_carrito_id) THEN
        UPDATE carrito SET estado = 'convertido' WHERE id = p_carrito_id;
    END IF;

    RETURN v_venta_id;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------------- aprobar / rechazar un comprobante
CREATE OR REPLACE FUNCTION sp_aprobar_pago_comprobante(p_venta_id INTEGER, p_empleado_id INTEGER)
RETURNS VOID AS $$
DECLARE
    v_pago_id       INTEGER;
    v_pago_metodo   VARCHAR;
    v_pago_estado   VARCHAR;
    v_sucursal_id   INTEGER;
    v_detalle       RECORD;
    v_inventario_id INTEGER;
    v_stock         INTEGER;
BEGIN
    SELECT id, metodo, estado INTO v_pago_id, v_pago_metodo, v_pago_estado FROM pago WHERE venta_id = p_venta_id;
    IF v_pago_id IS NULL OR v_pago_metodo = 'paypal' OR v_pago_estado <> 'verificando' THEN
        RAISE EXCEPTION 'pago_no_verificable';
    END IF;
    SELECT sucursal_id INTO v_sucursal_id FROM venta WHERE id = p_venta_id;

    FOR v_detalle IN
        SELECT il.producto_id, il.talla_id, il.color_id, il.cantidad
        FROM detalle_venta_digital d JOIN item_linea il ON il.id = d.id
        WHERE d.venta_digital_id = p_venta_id
    LOOP
        SELECT id, cantidad INTO v_inventario_id, v_stock FROM inventario
        WHERE producto_id = v_detalle.producto_id AND talla_id = v_detalle.talla_id
          AND color_id = v_detalle.color_id AND sucursal_id = v_sucursal_id
        FOR UPDATE;
        IF v_inventario_id IS NULL OR v_stock < v_detalle.cantidad THEN
            RAISE EXCEPTION 'stock_insuficiente';
        END IF;
        UPDATE inventario SET cantidad = cantidad - v_detalle.cantidad WHERE id = v_inventario_id;
        INSERT INTO movimiento_inventario (inventario_id, empleado_id, tipo, cantidad, fecha, documento_referencia)
        VALUES (v_inventario_id, p_empleado_id, 'salida', v_detalle.cantidad, now(),
                'Venta digital #' || p_venta_id || ' (comprobante ' || v_pago_metodo || ' aprobado)');
    END LOOP;

    UPDATE venta SET estado = 'pagada' WHERE id = p_venta_id;
    UPDATE pago SET estado = 'completado', revisado_por_id = p_empleado_id, motivo_rechazo = NULL WHERE id = v_pago_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sp_rechazar_pago_comprobante(p_venta_id INTEGER, p_empleado_id INTEGER, p_motivo TEXT)
RETURNS VOID AS $$
DECLARE
    v_pago_id     INTEGER;
    v_pago_metodo VARCHAR;
    v_pago_estado VARCHAR;
BEGIN
    SELECT id, metodo, estado INTO v_pago_id, v_pago_metodo, v_pago_estado FROM pago WHERE venta_id = p_venta_id;
    IF v_pago_id IS NULL OR v_pago_metodo = 'paypal' OR v_pago_estado <> 'verificando' THEN
        RAISE EXCEPTION 'pago_no_verificable';
    END IF;
    IF p_motivo IS NULL OR length(trim(p_motivo)) < 3 THEN
        RAISE EXCEPTION 'motivo_rechazo_requerido';
    END IF;
    UPDATE venta SET estado = 'cancelada' WHERE id = p_venta_id;
    UPDATE pago SET estado = 'rechazado', revisado_por_id = p_empleado_id, motivo_rechazo = trim(p_motivo)
    WHERE id = v_pago_id;
END;
$$ LANGUAGE plpgsql;
"""

DOWNGRADE = r"""
DROP FUNCTION IF EXISTS sp_rechazar_pago_comprobante(INTEGER, INTEGER, TEXT);
DROP FUNCTION IF EXISTS sp_aprobar_pago_comprobante(INTEGER, INTEGER);
DROP FUNCTION IF EXISTS sp_crear_venta_tienda(INTEGER, INTEGER, INTEGER, JSONB, INTEGER[], INTEGER, VARCHAR, VARCHAR);
ALTER TABLE pago DROP COLUMN IF EXISTS motivo_rechazo, DROP COLUMN IF EXISTS metodo_pago_id;
DROP TABLE IF EXISTS metodo_pago_empresa;
ALTER TABLE empresa DROP COLUMN IF EXISTS telefono, DROP COLUMN IF EXISTS direccion_fiscal,
    DROP COLUMN IF EXISTS nit, DROP COLUMN IF EXISTS razon_social;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
