"""SaaS: compra de la suscripcion de una boutique (PayPal) y su administrador

Flujo: la persona arma su boutique en /empezar, paga con PayPal (en USD al
tipo de cambio oficial) y recien entonces se crean la empresa, la
suscripcion, su Administrador (credenciales por correo) y el pago.

- plan_suscripcion.operacion_offline: el plan Prueba no la incluye.
- pago_suscripcion: cada pago (o activacion de prueba) con el monto en Bs, en
  USD y el tipo de cambio usado. paypal_order_id unico: la misma orden no se
  puede usar dos veces.
- fn_tipo_cambio_oficial(): Bs por USD del Banco Central de Bolivia (6,96).
- fn_cotizar_suscripcion(plan, periodo): cuanto cuesta en Bs y en USD.
- sp_registrar_empresa_suscrita(...): crea todo en una sola transaccion.
- trg_pago_suscripcion_preparar: completa montos/tipo de cambio desde la
  suscripcion y rechaza un pago de PayPal que no coincida con lo cotizado.
- trg_pago_suscripcion_auditar: deja el pago en la bitacora de la empresa.
- La auditoria de empresas muestra el enlace /tienda-<subdominio>.

Revision ID: f6a2c9d4b813
Revises: d5b8e2f4a961
Create Date: 2026-10-21

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "f6a2c9d4b813"
down_revision = "d5b8e2f4a961"
branch_labels = None
depends_on = None

UPGRADE = r"""
-- ------------------------------------------------------------ planes
ALTER TABLE plan_suscripcion ADD COLUMN operacion_offline BOOLEAN NOT NULL DEFAULT TRUE;
UPDATE plan_suscripcion SET operacion_offline = FALSE WHERE codigo = 'prueba';

-- --------------------------------------------------------- tipo de cambio
-- Tipo de cambio oficial de venta del Banco Central de Bolivia.
CREATE OR REPLACE FUNCTION fn_tipo_cambio_oficial()
RETURNS NUMERIC AS $$
    SELECT 6.96::numeric;
$$ LANGUAGE sql IMMUTABLE;

-- Precio de un plan en Bs (mismo calculo que trg_suscripcion_preparar) y en USD.
CREATE OR REPLACE FUNCTION fn_cotizar_suscripcion(p_plan_codigo VARCHAR, p_periodo VARCHAR)
RETURNS TABLE (
    plan_codigo VARCHAR, plan_nombre VARCHAR, periodo VARCHAR, max_sucursales INTEGER,
    monto_bob NUMERIC, tipo_cambio NUMERIC, monto_usd NUMERIC
) AS $$
    SELECT p.codigo, p.nombre,
           (CASE WHEN p.dias_prueba IS NOT NULL THEN 'prueba' ELSE p_periodo END)::varchar,
           p.max_sucursales,
           x.bob, fn_tipo_cambio_oficial(), round(x.bob / fn_tipo_cambio_oficial(), 2)
    FROM plan_suscripcion p
    CROSS JOIN LATERAL (
        SELECT CASE
                   WHEN p.dias_prueba IS NOT NULL THEN 0
                   WHEN p_periodo = 'anual' THEN p.precio_mensual * 10   -- 2 meses de regalo
                   ELSE p.precio_mensual
               END::numeric AS bob
    ) x
    WHERE p.codigo = p_plan_codigo AND p.activo
      AND (p.dias_prueba IS NOT NULL OR p_periodo IN ('mensual', 'anual'));
$$ LANGUAGE sql STABLE;

-- ----------------------------------------------------------------- pagos
CREATE TABLE pago_suscripcion (
    id                SERIAL PRIMARY KEY,
    empresa_id        INTEGER NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    suscripcion_id    INTEGER NOT NULL REFERENCES suscripcion(id) ON DELETE CASCADE,
    metodo            VARCHAR(20) NOT NULL CHECK (metodo IN ('paypal', 'prueba')),
    paypal_order_id   VARCHAR(64) UNIQUE,
    paypal_capture_id VARCHAR(64),
    monto_bob         NUMERIC(10, 2) NOT NULL DEFAULT 0,
    tipo_cambio       NUMERIC(8, 4) NOT NULL DEFAULT 0,
    monto_usd         NUMERIC(10, 2) NOT NULL DEFAULT 0,
    estado            VARCHAR(20) NOT NULL DEFAULT 'completado' CHECK (estado IN ('completado', 'reembolsado')),
    fecha             TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX ix_pago_suscripcion_empresa ON pago_suscripcion (empresa_id, fecha DESC);

CREATE OR REPLACE FUNCTION fn_trg_pago_suscripcion_preparar()
RETURNS trigger AS $$
DECLARE
    v_monto_bob NUMERIC;
    v_esperado  NUMERIC;
BEGIN
    SELECT monto INTO v_monto_bob FROM suscripcion WHERE id = NEW.suscripcion_id;
    NEW.monto_bob := v_monto_bob;
    NEW.tipo_cambio := fn_tipo_cambio_oficial();
    v_esperado := round(v_monto_bob / NEW.tipo_cambio, 2);

    IF NEW.metodo = 'paypal' THEN
        IF NEW.paypal_order_id IS NULL OR v_monto_bob <= 0 THEN
            RAISE EXCEPTION 'pago_requerido';
        END IF;
        -- Lo que cobro PayPal tiene que ser exactamente lo cotizado.
        IF abs(coalesce(NEW.monto_usd, 0) - v_esperado) > 0.01 THEN
            RAISE EXCEPTION 'monto_pago_incorrecto'
                USING DETAIL = format('Se esperaba US$ %s y se recibio US$ %s.', v_esperado, NEW.monto_usd);
        END IF;
    ELSE
        IF v_monto_bob > 0 THEN
            RAISE EXCEPTION 'pago_requerido';
        END IF;
        NEW.monto_usd := 0;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_pago_suscripcion_preparar
BEFORE INSERT ON pago_suscripcion
FOR EACH ROW EXECUTE FUNCTION fn_trg_pago_suscripcion_preparar();

CREATE OR REPLACE FUNCTION fn_trg_pago_suscripcion_auditar()
RETURNS trigger AS $$
DECLARE
    v_usuario INTEGER := nullif(current_setting('arlani.usuario_id', true), '')::int;
BEGIN
    IF v_usuario IS NULL THEN
        RETURN NULL;
    END IF;
    INSERT INTO bitacora (usuario_id, accion, entidad_afectada, entidad_id, fecha, detalle,
                          ip_address, plataforma, empresa_id)
    VALUES (
        v_usuario, 'PAGAR', 'pago_suscripcion', NEW.id, now(),
        CASE NEW.metodo
            WHEN 'paypal' THEN format('Pago de suscripcion con PayPal: US$ %s (Bs %s al cambio %s), orden %s',
                                      NEW.monto_usd, NEW.monto_bob, NEW.tipo_cambio, NEW.paypal_order_id)
            ELSE 'Activacion del plan de prueba (sin pago)'
        END,
        nullif(current_setting('atelier.client_ip', true), ''),
        nullif(current_setting('atelier.client_platform', true), ''),
        NEW.empresa_id
    );
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_pago_suscripcion_auditar
AFTER INSERT ON pago_suscripcion
FOR EACH ROW EXECUTE FUNCTION fn_trg_pago_suscripcion_auditar();

-- ----------------------------------------------- alta completa (una transaccion)
CREATE OR REPLACE FUNCTION sp_registrar_empresa_suscrita(
    p_nombre VARCHAR, p_subdominio VARCHAR, p_ciudad VARCHAR, p_color VARCHAR,
    p_plan_codigo VARCHAR, p_periodo VARCHAR, p_propietario_id INTEGER,
    p_admin_nombre VARCHAR, p_admin_email VARCHAR, p_admin_password_hash VARCHAR,
    p_paypal_order_id VARCHAR, p_paypal_capture_id VARCHAR, p_monto_usd NUMERIC
) RETURNS TABLE (empresa_id INTEGER, subdominio VARCHAR, admin_id INTEGER, suscripcion_id INTEGER) AS $$
DECLARE
    v_empresa  INTEGER;
    v_admin    INTEGER;
    v_susc     INTEGER;
    v_rol      INTEGER;
    v_correo   VARCHAR := lower(trim(p_admin_email));
BEGIN
    IF EXISTS (SELECT 1 FROM usuario WHERE lower(email) = v_correo) THEN
        RAISE EXCEPTION 'correo_en_uso';
    END IF;

    -- Empresa + suscripcion (sp_crear_empresa; el trigger de la suscripcion
    -- calcula monto y vencimiento, otros triggers copian permisos y crean la
    -- configuracion de asistencia).
    v_empresa := sp_crear_empresa(p_nombre, p_subdominio, p_ciudad, p_color, v_correo,
                                  p_plan_codigo, p_periodo, p_propietario_id);
    SELECT s.id INTO v_susc FROM suscripcion s WHERE s.empresa_id = v_empresa AND s.estado = 'activa';

    -- Administrador de la boutique: trg_empleado_empresa lo asigna a la empresa.
    SELECT id INTO v_rol FROM rol WHERE nombre = 'Administrador';
    PERFORM set_config('arlani.empresa_id', v_empresa::text, true);
    v_admin := sp_crear_empleado(p_admin_nombre, v_correo, p_admin_password_hash,
                                 'administrador', NULL, v_rol, 'sistema');

    -- El pago (trg_pago_suscripcion_preparar valida el monto cobrado).
    INSERT INTO pago_suscripcion (empresa_id, suscripcion_id, metodo, paypal_order_id, paypal_capture_id, monto_usd)
    VALUES (v_empresa, v_susc,
            CASE WHEN p_paypal_order_id IS NULL THEN 'prueba' ELSE 'paypal' END,
            p_paypal_order_id, p_paypal_capture_id, p_monto_usd);

    RETURN QUERY SELECT v_empresa, e.subdominio, v_admin, v_susc FROM empresa e WHERE e.id = v_empresa;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------- auditoria: enlace /tienda-<subdominio>
CREATE OR REPLACE FUNCTION fn_trg_auditar_plataforma()
RETURNS trigger AS $$
DECLARE
    v_usuario INTEGER := nullif(current_setting('arlani.usuario_id', true), '')::int;
    v_id      INTEGER;
    v_accion  VARCHAR;
    v_detalle TEXT;
BEGIN
    IF v_usuario IS NULL THEN
        RETURN NULL;
    END IF;

    IF TG_OP = 'INSERT' THEN
        v_accion := 'CREAR';
    ELSIF TG_OP = 'UPDATE' THEN
        v_accion := 'ACTUALIZAR';
    ELSE
        v_accion := 'ELIMINAR';
    END IF;

    IF TG_TABLE_NAME = 'empresa' THEN
        IF TG_OP = 'DELETE' THEN
            v_id := OLD.id;
            v_detalle := format('Empresa "%s" eliminada (/tienda-%s)', OLD.nombre, OLD.subdominio);
        ELSIF TG_OP = 'UPDATE' AND OLD.estado IS DISTINCT FROM NEW.estado THEN
            v_id := NEW.id;
            v_accion := CASE NEW.estado WHEN 'suspendida' THEN 'SUSPENDER' ELSE 'REACTIVAR' END;
            v_detalle := format('Empresa "%s" %s', NEW.nombre,
                                CASE NEW.estado WHEN 'suspendida' THEN 'suspendida' ELSE 'reactivada' END);
        ELSE
            v_id := NEW.id;
            v_detalle := format('Empresa "%s" (/tienda-%s)', NEW.nombre, NEW.subdominio);
        END IF;
    ELSIF TG_TABLE_NAME = 'suscripcion' THEN
        v_id := NEW.id;
        v_detalle := format('Empresa "%s" suscrita al plan %s (%s, Bs %s)',
                            (SELECT nombre FROM empresa WHERE id = NEW.empresa_id),
                            (SELECT nombre FROM plan_suscripcion WHERE id = NEW.plan_id),
                            NEW.periodo, NEW.monto);
    ELSE
        v_id := NEW.id;
        v_detalle := format('Plan "%s": Bs %s/mes, hasta %s sucursales, IA %s',
                            NEW.nombre, NEW.precio_mensual, NEW.max_sucursales,
                            CASE WHEN NEW.ia_generativa THEN 'incluida' ELSE 'no incluida' END);
    END IF;

    INSERT INTO bitacora (usuario_id, accion, entidad_afectada, entidad_id, fecha, detalle, ip_address, plataforma)
    VALUES (v_usuario, v_accion, TG_TABLE_NAME, v_id, now(), v_detalle,
            nullif(current_setting('atelier.client_ip', true), ''),
            nullif(current_setting('atelier.client_platform', true), ''));
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

DOWNGRADE = r"""
DROP FUNCTION IF EXISTS sp_registrar_empresa_suscrita(VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, INTEGER,
                                                      VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, NUMERIC);
DROP TABLE IF EXISTS pago_suscripcion;
DROP FUNCTION IF EXISTS fn_trg_pago_suscripcion_auditar();
DROP FUNCTION IF EXISTS fn_trg_pago_suscripcion_preparar();
DROP FUNCTION IF EXISTS fn_cotizar_suscripcion(VARCHAR, VARCHAR);
DROP FUNCTION IF EXISTS fn_tipo_cambio_oficial();
ALTER TABLE plan_suscripcion DROP COLUMN IF EXISTS operacion_offline;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
