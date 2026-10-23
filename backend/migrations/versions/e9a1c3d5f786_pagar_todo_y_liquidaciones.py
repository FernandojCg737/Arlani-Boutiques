"""SaaS: "Pagar todo" (un solo cobro de Arlani) y liquidaciones a cada tienda

- liquidacion_tienda: cuando el cliente paga todo su carrito de una vez,
  Arlani cobra con SU PayPal y le envia a cada tienda (PayPal Payouts, al
  instante) lo suyo menos la comision: bruto - comision = neto.
  Estados: pendiente (aun no se envio), enviada, fallida (se reintenta).
- pago.liquidacion_id: la venta la cobro Arlani (no la tienda).
- transaccion.captura_id: id de la captura de PayPal, para poder reembolsar.
- cuenta_tienda_movimiento:
    * retencion: la comision que Arlani se quedo al liquidar (negativa: deja
      la comision de esas ventas en cero).
    * reembolso: si una venta cobrada por Arlani se devuelve "al mismo medio"
      despues de liquidar, Arlani le devuelve el dinero al cliente y la
      tienda queda debiendo ese monto (positivo). Lo deja un trigger al
      completarse la devolucion.
- sp_registrar_liquidacion / sp_marcar_liquidacion.

Revision ID: e9a1c3d5f786
Revises: d7f9b1c3e564
Create Date: 2026-10-23

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "e9a1c3d5f786"
down_revision = "d7f9b1c3e564"
branch_labels = None
depends_on = None


UPGRADE = r"""
ALTER TABLE transaccion ADD COLUMN captura_id VARCHAR(64);

CREATE TABLE liquidacion_tienda (
    id                SERIAL PRIMARY KEY,
    empresa_id        INTEGER NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    fecha             TIMESTAMP NOT NULL DEFAULT now(),
    paypal_order_id   VARCHAR(64) NOT NULL,
    paypal_capture_id VARCHAR(64) NOT NULL,
    bruto_bob         NUMERIC(10,2) NOT NULL CHECK (bruto_bob > 0),
    comision_bob      NUMERIC(10,2) NOT NULL CHECK (comision_bob >= 0),
    neto_bob          NUMERIC(10,2) NOT NULL CHECK (neto_bob >= 0),
    tipo_cambio       NUMERIC(8,4) NOT NULL,
    neto_usd          NUMERIC(10,2) NOT NULL,
    paypal_email      VARCHAR(150) NOT NULL,
    estado            VARCHAR(20) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'enviada', 'fallida')),
    payout_batch_id   VARCHAR(64),
    error             VARCHAR(300),
    fecha_envio       TIMESTAMP,
    UNIQUE (paypal_order_id, empresa_id)
);
CREATE INDEX ix_liquidacion_empresa ON liquidacion_tienda (empresa_id, fecha DESC);
ALTER TABLE liquidacion_tienda ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_liquidacion_tienda_empresa ON liquidacion_tienda FOR SELECT TO arlani_tenant
    USING (empresa_id = fn_empresa_actual());
GRANT SELECT ON liquidacion_tienda TO arlani_tenant;

ALTER TABLE pago ADD COLUMN liquidacion_id INTEGER REFERENCES liquidacion_tienda(id) ON DELETE SET NULL;

ALTER TABLE cuenta_tienda_movimiento DROP CONSTRAINT cuenta_tienda_movimiento_tipo_check;
ALTER TABLE cuenta_tienda_movimiento ADD CONSTRAINT cuenta_tienda_movimiento_tipo_check
    CHECK (tipo IN ('comision', 'pago', 'ajuste', 'retencion', 'reembolso'));
ALTER TABLE cuenta_tienda_movimiento
    ADD COLUMN liquidacion_id INTEGER REFERENCES liquidacion_tienda(id) ON DELETE SET NULL,
    ADD COLUMN devolucion_id INTEGER REFERENCES devolucion(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX ux_cuenta_retencion ON cuenta_tienda_movimiento (liquidacion_id) WHERE tipo = 'retencion';
CREATE UNIQUE INDEX ux_cuenta_reembolso ON cuenta_tienda_movimiento (devolucion_id) WHERE tipo = 'reembolso';

-- ------------------------------------------------- liquidar a una tienda
-- Ventas de UNA tienda cobradas por Arlani en un "Pagar todo". Las
-- comisiones de esas ventas ya las dejo trg_venta_comision; aca se retienen.
CREATE OR REPLACE FUNCTION sp_registrar_liquidacion(
    p_empresa_id      INTEGER,
    p_order_id        VARCHAR,
    p_capture_id      VARCHAR,
    p_venta_ids       INTEGER[],
    p_tipo_cambio     NUMERIC
) RETURNS INTEGER AS $$
DECLARE
    v_bruto    NUMERIC(10,2);
    v_comision NUMERIC(10,2);
    v_email    VARCHAR;
    v_id       INTEGER;
BEGIN
    SELECT COALESCE(sum(v.total), 0) INTO v_bruto
    FROM venta v JOIN sucursal s ON s.id = v.sucursal_id
    WHERE v.id = ANY(p_venta_ids) AND s.empresa_id = p_empresa_id AND v.estado = 'pagada';
    IF v_bruto <= 0 OR (SELECT count(*) FROM unnest(p_venta_ids)) <>
        (SELECT count(*) FROM venta v JOIN sucursal s ON s.id = v.sucursal_id
          WHERE v.id = ANY(p_venta_ids) AND s.empresa_id = p_empresa_id) THEN
        RAISE EXCEPTION 'liquidacion_invalida';
    END IF;
    SELECT COALESCE(sum(monto_bob), 0) INTO v_comision
    FROM cuenta_tienda_movimiento WHERE tipo = 'comision' AND venta_id = ANY(p_venta_ids);
    SELECT paypal_email INTO v_email FROM metodo_pago_empresa
    WHERE empresa_id = p_empresa_id AND tipo = 'paypal' AND activo AND paypal_email IS NOT NULL;
    IF v_email IS NULL THEN
        RAISE EXCEPTION 'tienda_sin_paypal_email';
    END IF;

    INSERT INTO liquidacion_tienda (empresa_id, paypal_order_id, paypal_capture_id, bruto_bob, comision_bob,
                                    neto_bob, tipo_cambio, neto_usd, paypal_email)
    VALUES (p_empresa_id, p_order_id, p_capture_id, v_bruto, v_comision, v_bruto - v_comision, p_tipo_cambio,
            round((v_bruto - v_comision) / p_tipo_cambio, 2), v_email)
    RETURNING id INTO v_id;

    UPDATE pago SET liquidacion_id = v_id WHERE venta_id = ANY(p_venta_ids);
    IF v_comision > 0 THEN
        INSERT INTO cuenta_tienda_movimiento (empresa_id, tipo, monto_bob, descripcion, liquidacion_id)
        VALUES (p_empresa_id, 'retencion', -v_comision,
                'Comisión retenida al liquidar el pago conjunto #' || v_id, v_id);
    END IF;
    RETURN v_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

CREATE OR REPLACE FUNCTION sp_marcar_liquidacion(
    p_id       INTEGER,
    p_estado   VARCHAR,
    p_batch_id VARCHAR,
    p_error    VARCHAR
) RETURNS VOID AS $$
BEGIN
    UPDATE liquidacion_tienda
       SET estado = p_estado,
           payout_batch_id = COALESCE(p_batch_id, payout_batch_id),
           error = left(p_error, 300),
           fecha_envio = CASE WHEN p_estado = 'enviada' THEN now() ELSE fecha_envio END
     WHERE id = p_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- ------------------------------- reembolso de una venta cobrada por Arlani
CREATE OR REPLACE FUNCTION fn_trg_devolucion_deuda() RETURNS TRIGGER AS $$
DECLARE
    v_liq     INTEGER;
    v_empresa INTEGER;
BEGIN
    IF NEW.estado <> 'completada' OR OLD.estado = 'completada' OR NEW.metodo_reembolso <> 'mismo_medio' THEN
        RETURN NEW;
    END IF;
    SELECT p.liquidacion_id, s.empresa_id INTO v_liq, v_empresa
    FROM pago p JOIN venta v ON v.id = p.venta_id JOIN sucursal s ON s.id = v.sucursal_id
    WHERE p.venta_id = NEW.venta_id;
    IF v_liq IS NOT NULL THEN
        INSERT INTO cuenta_tienda_movimiento (empresa_id, tipo, venta_id, monto_bob, descripcion, liquidacion_id, devolucion_id)
        VALUES (v_empresa, 'reembolso', NEW.venta_id, NEW.monto_reembolso,
                'Reembolso de la venta #' || NEW.venta_id || ' (devolución #' || NEW.id || ') pagado por Arlani',
                v_liq, NEW.id)
        ON CONFLICT (devolucion_id) WHERE tipo = 'reembolso' DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

CREATE TRIGGER trg_devolucion_deuda
    AFTER UPDATE OF estado ON devolucion
    FOR EACH ROW EXECUTE FUNCTION fn_trg_devolucion_deuda();
"""


DOWNGRADE = r"""
DROP TRIGGER IF EXISTS trg_devolucion_deuda ON devolucion;
DROP FUNCTION IF EXISTS fn_trg_devolucion_deuda();
DROP FUNCTION IF EXISTS sp_marcar_liquidacion(INTEGER, VARCHAR, VARCHAR, VARCHAR);
DROP FUNCTION IF EXISTS sp_registrar_liquidacion(INTEGER, VARCHAR, VARCHAR, INTEGER[], NUMERIC);
DELETE FROM cuenta_tienda_movimiento WHERE tipo IN ('retencion', 'reembolso');
DROP INDEX IF EXISTS ux_cuenta_reembolso;
DROP INDEX IF EXISTS ux_cuenta_retencion;
ALTER TABLE cuenta_tienda_movimiento DROP COLUMN IF EXISTS devolucion_id, DROP COLUMN IF EXISTS liquidacion_id;
ALTER TABLE cuenta_tienda_movimiento DROP CONSTRAINT cuenta_tienda_movimiento_tipo_check;
ALTER TABLE cuenta_tienda_movimiento ADD CONSTRAINT cuenta_tienda_movimiento_tipo_check
    CHECK (tipo IN ('comision', 'pago', 'ajuste'));
ALTER TABLE pago DROP COLUMN IF EXISTS liquidacion_id;
DROP TABLE IF EXISTS liquidacion_tienda;
ALTER TABLE transaccion DROP COLUMN IF EXISTS captura_id;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
