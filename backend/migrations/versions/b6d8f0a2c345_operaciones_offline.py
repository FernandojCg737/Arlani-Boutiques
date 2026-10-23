"""P4 Offline y sincronizacion (CU11 a CU14 del 2do parcial)

- fn_empresa_con_offline: la tienda puede operar sin conexion (su plan
  vigente lo incluye: Basico y Profesional) y esta operativa.
- operacion_offline: cada venta o reserva hecha sin conexion que llega al
  sincronizar (CU12). La identifica el uuid que genera el dispositivo:
  reenviarla no la duplica (idempotencia), devuelve el mismo resultado.
  Estados: confirmada, conflicto (sin stock al llegar, CU14), rechazada,
  resuelta (el personal la ajusto) o anulada.
- sp_crear_venta_offline: venta de contado con la fecha y hora en que se
  hizo y los precios que se cobraron; origen 'offline'. trg_venta_caja la
  pone en la caja de ese momento.
- Permisos 2P-CU11/12/13 para todo el personal; 2P-CU14 (conflictos) para
  Administrador y Encargado de Sucursal.

Revision ID: b6d8f0a2c345
Revises: a4c6e8f0b123
Create Date: 2026-10-23

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "b6d8f0a2c345"
down_revision = "a4c6e8f0b123"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE OR REPLACE FUNCTION fn_empresa_con_offline(p_empresa_id INTEGER)
RETURNS BOOLEAN AS $$
    SELECT fn_empresa_operativa(p_empresa_id) AND EXISTS (
        SELECT 1 FROM suscripcion s JOIN plan_suscripcion p ON p.id = s.plan_id
        WHERE s.empresa_id = p_empresa_id AND s.estado = 'activa' AND p.operacion_offline
    );
$$ LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public;

CREATE TABLE operacion_offline (
    id              SERIAL PRIMARY KEY,
    uuid            UUID NOT NULL UNIQUE,
    empresa_id      INTEGER NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    sucursal_id     INTEGER REFERENCES sucursal(id) ON DELETE SET NULL,
    usuario_id      INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    tipo            VARCHAR(10) NOT NULL CHECK (tipo IN ('venta', 'reserva')),
    datos           JSONB NOT NULL,
    registrada_en   TIMESTAMP NOT NULL,
    recibida_en     TIMESTAMP NOT NULL DEFAULT now(),
    actualizada_en  TIMESTAMP NOT NULL DEFAULT now(),
    estado          VARCHAR(12) NOT NULL
                    CHECK (estado IN ('confirmada', 'conflicto', 'rechazada', 'resuelta', 'anulada')),
    mensaje         TEXT,
    conflicto       JSONB,
    venta_id        INTEGER REFERENCES venta(id) ON DELETE SET NULL,
    reserva_id      INTEGER REFERENCES reserva(id) ON DELETE SET NULL,
    intentos        INTEGER NOT NULL DEFAULT 1,
    resuelta_por_id INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    resuelta_en     TIMESTAMP,
    resolucion      TEXT
);
CREATE INDEX ix_operacion_offline_empresa ON operacion_offline (empresa_id, estado, recibida_en DESC);
CREATE INDEX ix_operacion_offline_usuario ON operacion_offline (usuario_id, recibida_en DESC);
ALTER TABLE operacion_offline ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_operacion_offline_empresa ON operacion_offline FOR ALL TO arlani_tenant
    USING (empresa_id = fn_empresa_actual()) WITH CHECK (empresa_id = fn_empresa_actual());

CREATE OR REPLACE FUNCTION sp_crear_venta_offline(
    p_cliente_id  INTEGER,
    p_sucursal_id INTEGER,
    p_empleado_id INTEGER,
    p_items       JSONB,
    p_fecha       TIMESTAMP
) RETURNS INTEGER AS $$
DECLARE
    v_venta_id INTEGER;
    v_item JSONB;
    v_precio NUMERIC(10,2);
    v_total NUMERIC(10,2) := 0;
    v_inventario_id INTEGER;
    v_stock INTEGER;
    v_detalle_id INTEGER;
BEGIN
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items) LOOP
        SELECT coalesce((v_item->>'precio')::NUMERIC, precio) INTO v_precio
        FROM producto WHERE id = (v_item->>'producto_id')::INTEGER;
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
    VALUES (p_cliente_id, p_sucursal_id, p_fecha, v_total, 'pagada', 'venta_presencial', 'offline', now())
    RETURNING id INTO v_venta_id;

    INSERT INTO venta_presencial (id, empleado_id) VALUES (v_venta_id, p_empleado_id);

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items) LOOP
        SELECT coalesce((v_item->>'precio')::NUMERIC, precio) INTO v_precio
        FROM producto WHERE id = (v_item->>'producto_id')::INTEGER;

        INSERT INTO item_linea (producto_id, talla_id, color_id, cantidad, tipo)
        VALUES ((v_item->>'producto_id')::INTEGER, (v_item->>'talla_id')::INTEGER,
                (v_item->>'color_id')::INTEGER, (v_item->>'cantidad')::INTEGER, 'detalle_venta_presencial')
        RETURNING id INTO v_detalle_id;

        INSERT INTO detalle_venta_presencial (id, venta_presencial_id, precio_unitario)
        VALUES (v_detalle_id, v_venta_id, v_precio);

        UPDATE inventario SET cantidad = cantidad - (v_item->>'cantidad')::INTEGER
        WHERE producto_id = (v_item->>'producto_id')::INTEGER AND talla_id = (v_item->>'talla_id')::INTEGER
          AND color_id = (v_item->>'color_id')::INTEGER AND sucursal_id = p_sucursal_id
        RETURNING id INTO v_inventario_id;

        INSERT INTO movimiento_inventario (inventario_id, empleado_id, tipo, cantidad, fecha, documento_referencia)
        VALUES (v_inventario_id, p_empleado_id, 'salida', (v_item->>'cantidad')::INTEGER, now(),
                'Venta offline #' || v_venta_id);
    END LOOP;

    INSERT INTO pago (venta_id, monto, metodo, estado, fecha)
    VALUES (v_venta_id, v_total, 'efectivo', 'completado', p_fecha);

    RETURN v_venta_id;
END;
$$ LANGUAGE plpgsql;

INSERT INTO rol_permiso (rol_id, permiso_id)
SELECT r.id, p.id FROM rol r, permiso p
WHERE (r.nombre IN ('Administrador', 'Encargado de Sucursal', 'Cajero') AND p.nombre IN ('2P-CU11', '2P-CU12', '2P-CU13'))
   OR (r.nombre IN ('Administrador', 'Encargado de Sucursal') AND p.nombre = '2P-CU14')
ON CONFLICT DO NOTHING;
INSERT INTO empresa_rol_permiso (empresa_id, rol_id, permiso_id)
SELECT e.id, r.id, p.id FROM empresa e, rol r, permiso p
WHERE (r.nombre IN ('Administrador', 'Encargado de Sucursal', 'Cajero') AND p.nombre IN ('2P-CU11', '2P-CU12', '2P-CU13'))
   OR (r.nombre IN ('Administrador', 'Encargado de Sucursal') AND p.nombre = '2P-CU14')
ON CONFLICT DO NOTHING;
"""

DOWNGRADE = r"""
DELETE FROM empresa_rol_permiso
WHERE permiso_id IN (SELECT id FROM permiso WHERE nombre IN ('2P-CU11', '2P-CU12', '2P-CU13', '2P-CU14'))
  AND rol_id IN (SELECT id FROM rol WHERE nombre IN ('Administrador', 'Encargado de Sucursal', 'Cajero'));
DELETE FROM rol_permiso
WHERE permiso_id IN (SELECT id FROM permiso WHERE nombre IN ('2P-CU11', '2P-CU12', '2P-CU13', '2P-CU14'))
  AND rol_id IN (SELECT id FROM rol WHERE nombre IN ('Administrador', 'Encargado de Sucursal', 'Cajero'));
DROP FUNCTION IF EXISTS sp_crear_venta_offline(INTEGER, INTEGER, INTEGER, JSONB, TIMESTAMP);
DROP TABLE IF EXISTS operacion_offline;
DROP FUNCTION IF EXISTS fn_empresa_con_offline(INTEGER);
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
