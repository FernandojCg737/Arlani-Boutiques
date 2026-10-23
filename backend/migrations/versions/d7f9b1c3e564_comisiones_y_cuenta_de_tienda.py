"""SaaS: comision de Arlani por venta y estado de cuenta de cada tienda

- cuenta_tienda_movimiento: libro de cuenta entre Arlani y cada tienda.
  monto_bob con signo: positivo = la tienda le debe a Arlani (comision);
  negativo = abono de la tienda (pago con PayPal). El saldo es la suma.
    * comision: una por venta en linea pagada, con el % del plan vigente de
      la tienda al momento de pagarse. Las ventas de mostrador no pagan
      comision. Si la venta pagada cambia de monto, la comision se ajusta;
      si se cancela, se anula. Las devoluciones no la devuelven (igual que
      las comisiones de las pasarelas de pago).
    * pago: la tienda paga su saldo con PayPal (sola o junto con la
      renovacion de su suscripcion).
  RLS: cada tienda ve solo sus movimientos y no los puede tocar; los
  escriben el trigger y sp_pagar_saldo_tienda.
- fn_saldo_cuenta_tienda(empresa): lo que la tienda debe hoy.
- sp_pagar_saldo_tienda: registra el pago del saldo (no se reusa la orden).

Revision ID: d7f9b1c3e564
Revises: c5e7a9b1d342
Create Date: 2026-10-22

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "d7f9b1c3e564"
down_revision = "c5e7a9b1d342"
branch_labels = None
depends_on = None


UPGRADE = r"""
CREATE TABLE cuenta_tienda_movimiento (
    id                SERIAL PRIMARY KEY,
    empresa_id        INTEGER NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    fecha             TIMESTAMP NOT NULL DEFAULT now(),
    tipo              VARCHAR(20) NOT NULL CHECK (tipo IN ('comision', 'pago', 'ajuste')),
    -- La comision queda aunque se borre la venta: ya se genero.
    venta_id          INTEGER REFERENCES venta(id) ON DELETE SET NULL,
    base_bob          NUMERIC(10,2),
    porcentaje        NUMERIC(5,2),
    monto_bob         NUMERIC(10,2) NOT NULL,
    descripcion       VARCHAR(200) NOT NULL,
    paypal_order_id   VARCHAR(64),
    paypal_capture_id VARCHAR(64),
    monto_usd         NUMERIC(10,2),
    tipo_cambio       NUMERIC(8,4),
    CHECK (tipo <> 'comision' OR (venta_id IS NOT NULL OR base_bob IS NOT NULL)),
    CHECK (tipo <> 'pago' OR (monto_bob < 0 AND paypal_order_id IS NOT NULL))
);
CREATE UNIQUE INDEX ux_cuenta_comision_venta ON cuenta_tienda_movimiento (venta_id) WHERE tipo = 'comision';
CREATE UNIQUE INDEX ux_cuenta_orden_paypal ON cuenta_tienda_movimiento (paypal_order_id) WHERE paypal_order_id IS NOT NULL;
CREATE INDEX ix_cuenta_empresa_fecha ON cuenta_tienda_movimiento (empresa_id, fecha DESC);

ALTER TABLE cuenta_tienda_movimiento ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_cuenta_tienda_empresa ON cuenta_tienda_movimiento FOR SELECT TO arlani_tenant
    USING (empresa_id = fn_empresa_actual());
GRANT SELECT ON cuenta_tienda_movimiento TO arlani_tenant;

-- ------------------------------------------- comision de cada venta en linea
CREATE OR REPLACE FUNCTION fn_trg_venta_comision() RETURNS TRIGGER AS $$
DECLARE
    v_empresa INTEGER;
    v_pct     NUMERIC(5,2);
BEGIN
    IF NEW.tipo <> 'venta_digital' THEN
        RETURN NEW;
    END IF;

    IF NEW.estado = 'pagada' THEN
        SELECT empresa_id INTO v_empresa FROM sucursal WHERE id = NEW.sucursal_id;
        SELECT p.comision_pct INTO v_pct
        FROM suscripcion s JOIN plan_suscripcion p ON p.id = s.plan_id
        WHERE s.empresa_id = v_empresa AND s.estado = 'activa';
        v_pct := COALESCE(v_pct, 3);

        IF TG_OP = 'INSERT' OR OLD.estado IS DISTINCT FROM 'pagada' THEN
            INSERT INTO cuenta_tienda_movimiento (empresa_id, tipo, venta_id, base_bob, porcentaje, monto_bob, descripcion)
            VALUES (v_empresa, 'comision', NEW.id, NEW.total, v_pct, round(NEW.total * v_pct / 100, 2),
                    'Comisión ' || v_pct || ' % de la venta en línea #' || NEW.id)
            ON CONFLICT (venta_id) WHERE tipo = 'comision' DO NOTHING;
        ELSIF OLD.total IS DISTINCT FROM NEW.total THEN
            -- Se edito una venta ya pagada: la comision sigue al monto, con su %.
            UPDATE cuenta_tienda_movimiento
               SET base_bob = NEW.total, monto_bob = round(NEW.total * porcentaje / 100, 2)
             WHERE venta_id = NEW.id AND tipo = 'comision';
        END IF;
    ELSIF TG_OP = 'UPDATE' AND OLD.estado = 'pagada' AND NEW.estado IN ('cancelada', 'pendiente') THEN
        DELETE FROM cuenta_tienda_movimiento WHERE venta_id = NEW.id AND tipo = 'comision';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

CREATE TRIGGER trg_venta_comision
    AFTER INSERT OR UPDATE OF estado, total ON venta
    FOR EACH ROW EXECUTE FUNCTION fn_trg_venta_comision();

-- ------------------------------------------------------------------- saldo
CREATE OR REPLACE FUNCTION fn_saldo_cuenta_tienda(p_empresa_id INTEGER) RETURNS NUMERIC AS $$
    SELECT COALESCE(sum(monto_bob), 0)::NUMERIC(10,2) FROM cuenta_tienda_movimiento WHERE empresa_id = p_empresa_id;
$$ LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public;

-- La tienda paga TODO su saldo con PayPal (a la cuenta de Arlani).
CREATE OR REPLACE FUNCTION sp_pagar_saldo_tienda(
    p_empresa_id        INTEGER,
    p_monto_bob         NUMERIC,
    p_monto_usd         NUMERIC,
    p_tipo_cambio       NUMERIC,
    p_paypal_order_id   VARCHAR,
    p_paypal_capture_id VARCHAR
) RETURNS INTEGER AS $$
DECLARE
    v_saldo NUMERIC(10,2);
    v_id    INTEGER;
BEGIN
    PERFORM 1 FROM empresa WHERE id = p_empresa_id FOR UPDATE;
    v_saldo := fn_saldo_cuenta_tienda(p_empresa_id);
    IF v_saldo <= 0 THEN
        RAISE EXCEPTION 'saldo_sin_deuda';
    END IF;
    IF p_monto_bob <> v_saldo THEN
        RAISE EXCEPTION 'saldo_cambio';
    END IF;
    IF EXISTS (SELECT 1 FROM cuenta_tienda_movimiento WHERE paypal_order_id = p_paypal_order_id) THEN
        RAISE EXCEPTION 'pago_ya_usado';
    END IF;
    INSERT INTO cuenta_tienda_movimiento (empresa_id, tipo, monto_bob, descripcion, paypal_order_id,
                                          paypal_capture_id, monto_usd, tipo_cambio)
    VALUES (p_empresa_id, 'pago', -p_monto_bob, 'Pago de comisiones con PayPal', p_paypal_order_id,
            p_paypal_capture_id, p_monto_usd, p_tipo_cambio)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;
"""


DOWNGRADE = r"""
DROP FUNCTION IF EXISTS sp_pagar_saldo_tienda(INTEGER, NUMERIC, NUMERIC, NUMERIC, VARCHAR, VARCHAR);
DROP FUNCTION IF EXISTS fn_saldo_cuenta_tienda(INTEGER);
DROP TRIGGER IF EXISTS trg_venta_comision ON venta;
DROP FUNCTION IF EXISTS fn_trg_venta_comision();
DROP TABLE IF EXISTS cuenta_tienda_movimiento;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
