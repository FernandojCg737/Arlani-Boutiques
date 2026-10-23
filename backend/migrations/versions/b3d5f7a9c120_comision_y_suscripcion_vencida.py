"""SaaS: comision por plan, tienda bloqueada al vencer y renovacion de la suscripcion

- plan_suscripcion.comision_pct: porcentaje que Arlani cobra por cada venta
  de la tienda (Prueba y Basico 3 %, Profesional 1.5 %). El SuperAdministrador
  lo cambia junto con el resto del plan (sp_actualizar_plan).
- fn_empresa_operativa: la tienda esta activa y su suscripcion vigente no
  vencio. Si vencio (la prueba o un plan sin renovar) la tienda no opera: su
  personal solo puede entrar a "Mi suscripcion" para pagar, y desaparece de
  la portada y del catalogo (fn_tienda_publica la informa como 'vencida').
- sp_renovar_suscripcion: una tienda que ya existe compra o renueva su plan
  (pago con PayPal). Si renueva el mismo plan antes de que venza, el nuevo
  periodo empieza al terminar el actual; si cambia de plan, empieza hoy.

Revision ID: b3d5f7a9c120
Revises: a8d3f1c6e924
Create Date: 2026-10-22

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "b3d5f7a9c120"
down_revision = "a8d3f1c6e924"
branch_labels = None
depends_on = None


UPGRADE = r"""
-- --------------------------------------------------------------- comision
ALTER TABLE plan_suscripcion ADD COLUMN comision_pct NUMERIC(5, 2) NOT NULL DEFAULT 3
    CHECK (comision_pct >= 0 AND comision_pct <= 30);
UPDATE plan_suscripcion SET comision_pct = 1.5 WHERE codigo = 'profesional';

DROP FUNCTION IF EXISTS sp_actualizar_plan(VARCHAR, NUMERIC, INTEGER, BOOLEAN);
CREATE OR REPLACE FUNCTION sp_actualizar_plan(
    p_codigo         VARCHAR,
    p_precio         NUMERIC,
    p_max_sucursales INTEGER,
    p_ia_generativa  BOOLEAN,
    p_comision_pct   NUMERIC
) RETURNS VOID AS $$
DECLARE
    v_plan_id INTEGER;
    v_excede  INTEGER;
BEGIN
    SELECT id INTO v_plan_id FROM plan_suscripcion WHERE codigo = p_codigo;
    IF v_plan_id IS NULL THEN
        RAISE EXCEPTION 'plan_no_encontrado';
    END IF;
    IF p_precio < 0 OR p_max_sucursales < 1 OR p_comision_pct < 0 OR p_comision_pct > 30 THEN
        RAISE EXCEPTION 'plan_valores_invalidos';
    END IF;
    SELECT count(*) INTO v_excede
    FROM suscripcion su
    WHERE su.plan_id = v_plan_id AND su.estado = 'activa'
      AND (SELECT count(*) FROM sucursal s WHERE s.empresa_id = su.empresa_id AND s.estado = 'activa') > p_max_sucursales;
    IF v_excede > 0 THEN
        RAISE EXCEPTION 'plan_limite_menor_al_uso'
            USING DETAIL = format('%s empresa(s) del plan ya usan mas de %s sucursales.', v_excede, p_max_sucursales);
    END IF;
    UPDATE plan_suscripcion
    SET precio_mensual = p_precio, max_sucursales = p_max_sucursales,
        ia_generativa = p_ia_generativa, comision_pct = p_comision_pct
    WHERE id = v_plan_id;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------------- tienda operativa o no
-- SECURITY DEFINER: el personal de una tienda (rol con RLS) igual puede
-- preguntar por su propia suscripcion.
CREATE OR REPLACE FUNCTION fn_empresa_operativa(p_empresa_id INTEGER)
RETURNS BOOLEAN AS $$
    SELECT EXISTS (
        SELECT 1
        FROM empresa e
        JOIN suscripcion s ON s.empresa_id = e.id AND s.estado = 'activa'
        WHERE e.id = p_empresa_id AND e.estado = 'activa'
          AND (s.fecha_fin IS NULL OR s.fecha_fin >= (now() AT TIME ZONE 'America/La_Paz')::date)
    );
$$ LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public;

-- Ficha publica: una tienda con la suscripcion vencida figura como 'vencida'
-- (sin catalogo, igual que una suspendida).
CREATE OR REPLACE FUNCTION fn_tienda_publica(p_subdominio VARCHAR)
RETURNS TABLE (
    id INTEGER, nombre VARCHAR, subdominio VARCHAR, ciudad VARCHAR, color_marca VARCHAR,
    logo_url VARCHAR, estado VARCHAR, tiene_catalogo BOOLEAN, sitio_propio BOOLEAN
) AS $$
    SELECT e.id, e.nombre, e.subdominio, e.ciudad, e.color_marca, e.logo_url,
           (CASE WHEN e.estado = 'activa' AND NOT fn_empresa_operativa(e.id) THEN 'vencida'
                 ELSE e.estado END)::varchar,
           EXISTS (SELECT 1 FROM producto p WHERE p.empresa_id = e.id AND p.estado = 'activo'),
           e.id = fn_empresa_por_defecto()
    FROM empresa e
    WHERE e.subdominio = lower(trim(p_subdominio));
$$ LANGUAGE sql STABLE;

-- Portada: solo las tiendas que estan operando.
CREATE OR REPLACE FUNCTION fn_tiendas_publicas()
RETURNS TABLE (
    id INTEGER, nombre VARCHAR, subdominio VARCHAR, ciudad VARCHAR,
    color_marca VARCHAR, logo_url VARCHAR
) AS $$
    SELECT e.id, e.nombre, e.subdominio, e.ciudad, e.color_marca, e.logo_url
    FROM empresa e
    WHERE e.estado = 'activa' AND fn_empresa_operativa(e.id)
    ORDER BY e.fecha_creacion, e.id;
$$ LANGUAGE sql STABLE;

-- "Mi suscripcion": ademas, si la tienda esta operando y la comision del plan.
DROP FUNCTION IF EXISTS fn_mi_suscripcion(INTEGER);
CREATE FUNCTION fn_mi_suscripcion(p_empresa_id INTEGER)
RETURNS TABLE (
    empresa_id INTEGER, empresa_nombre VARCHAR, subdominio VARCHAR, color_marca VARCHAR,
    empresa_estado VARCHAR, plan_codigo VARCHAR, plan_nombre VARCHAR, precio_mensual NUMERIC,
    ia_generativa BOOLEAN, periodo VARCHAR, monto NUMERIC, fecha_inicio DATE, fecha_fin DATE,
    dias_restantes INTEGER, sucursales_usadas INTEGER, max_sucursales INTEGER,
    personal INTEGER, clientes INTEGER, operativa BOOLEAN, comision_pct NUMERIC
) AS $$
    SELECT
        e.id, e.nombre, e.subdominio, e.color_marca, e.estado,
        p.codigo, p.nombre, p.precio_mensual, p.ia_generativa,
        su.periodo, su.monto, su.fecha_inicio, su.fecha_fin,
        CASE WHEN su.fecha_fin IS NULL THEN NULL
             ELSE (su.fecha_fin - (now() AT TIME ZONE 'America/La_Paz')::date) END,
        (SELECT count(*)::int FROM sucursal s WHERE s.empresa_id = e.id AND s.estado = 'activa'),
        p.max_sucursales,
        (SELECT count(*)::int FROM usuario u WHERE u.empresa_id = e.id
                                              AND u.tipo IN ('administrador', 'encargado_sucursal', 'cajero')),
        (SELECT count(*)::int FROM fn_clientes_de_empresa(e.id)),
        fn_empresa_operativa(e.id),
        p.comision_pct
    FROM empresa e
    LEFT JOIN suscripcion su ON su.empresa_id = e.id AND su.estado = 'activa'
    LEFT JOIN plan_suscripcion p ON p.id = su.plan_id
    WHERE e.id = p_empresa_id;
$$ LANGUAGE sql STABLE;

-- --------------------------------------------- renovar / comprar el plan
-- SECURITY DEFINER: lo llama el Administrador de la tienda (rol con RLS) y
-- toca suscripcion y pago_suscripcion de su propia empresa.
CREATE OR REPLACE FUNCTION sp_renovar_suscripcion(
    p_empresa_id INTEGER, p_plan_codigo VARCHAR, p_periodo VARCHAR,
    p_paypal_order_id VARCHAR, p_paypal_capture_id VARCHAR, p_monto_usd NUMERIC
) RETURNS INTEGER AS $$
DECLARE
    v_plan   plan_suscripcion%ROWTYPE;
    v_actual suscripcion%ROWTYPE;
    v_hoy    DATE := (now() AT TIME ZONE 'America/La_Paz')::date;
    v_inicio DATE;
    v_susc   INTEGER;
BEGIN
    SELECT * INTO v_plan FROM plan_suscripcion WHERE codigo = p_plan_codigo AND activo;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'plan_no_encontrado';
    END IF;
    IF v_plan.dias_prueba IS NOT NULL THEN
        RAISE EXCEPTION 'prueba_no_renovable';
    END IF;
    IF p_periodo NOT IN ('mensual', 'anual') THEN
        RAISE EXCEPTION 'periodo_invalido';
    END IF;
    IF (SELECT count(*) FROM sucursal WHERE empresa_id = p_empresa_id AND estado = 'activa') > v_plan.max_sucursales THEN
        RAISE EXCEPTION 'limite_sucursales_plan'
            USING DETAIL = format('El plan permite %s sucursales activas.', v_plan.max_sucursales);
    END IF;
    IF EXISTS (SELECT 1 FROM pago_suscripcion WHERE paypal_order_id = p_paypal_order_id) THEN
        RAISE EXCEPTION 'pago_ya_usado';
    END IF;

    v_inicio := v_hoy;
    SELECT * INTO v_actual FROM suscripcion WHERE empresa_id = p_empresa_id AND estado = 'activa';
    IF FOUND AND v_actual.plan_id = v_plan.id AND v_actual.fecha_fin IS NOT NULL AND v_actual.fecha_fin >= v_hoy THEN
        v_inicio := v_actual.fecha_fin + 1;
    END IF;

    -- trg_suscripcion_preparar calcula monto y vencimiento y cierra la anterior.
    INSERT INTO suscripcion (empresa_id, plan_id, periodo, fecha_inicio, estado)
    VALUES (p_empresa_id, v_plan.id, p_periodo, v_inicio, 'activa')
    RETURNING id INTO v_susc;

    -- trg_pago_suscripcion_preparar valida que lo cobrado sea el monto del plan.
    INSERT INTO pago_suscripcion (empresa_id, suscripcion_id, metodo, paypal_order_id, paypal_capture_id, monto_usd)
    VALUES (p_empresa_id, v_susc, 'paypal', p_paypal_order_id, p_paypal_capture_id, p_monto_usd);

    -- Si estaba suspendida solo por falta de pago, vuelve a operar.
    RETURN v_susc;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;
"""

DOWNGRADE = r"""
DROP FUNCTION IF EXISTS sp_renovar_suscripcion(INTEGER, VARCHAR, VARCHAR, VARCHAR, VARCHAR, NUMERIC);

DROP FUNCTION IF EXISTS fn_mi_suscripcion(INTEGER);
CREATE FUNCTION fn_mi_suscripcion(p_empresa_id INTEGER)
RETURNS TABLE (
    empresa_id INTEGER, empresa_nombre VARCHAR, subdominio VARCHAR, color_marca VARCHAR,
    empresa_estado VARCHAR, plan_codigo VARCHAR, plan_nombre VARCHAR, precio_mensual NUMERIC,
    ia_generativa BOOLEAN, periodo VARCHAR, monto NUMERIC, fecha_inicio DATE, fecha_fin DATE,
    dias_restantes INTEGER, sucursales_usadas INTEGER, max_sucursales INTEGER,
    personal INTEGER, clientes INTEGER
) AS $$
    SELECT
        e.id, e.nombre, e.subdominio, e.color_marca, e.estado,
        p.codigo, p.nombre, p.precio_mensual, p.ia_generativa,
        su.periodo, su.monto, su.fecha_inicio, su.fecha_fin,
        CASE WHEN su.fecha_fin IS NULL THEN NULL
             ELSE (su.fecha_fin - (now() AT TIME ZONE 'America/La_Paz')::date) END,
        (SELECT count(*)::int FROM sucursal s WHERE s.empresa_id = e.id AND s.estado = 'activa'),
        p.max_sucursales,
        (SELECT count(*)::int FROM usuario u WHERE u.empresa_id = e.id
                                              AND u.tipo IN ('administrador', 'encargado_sucursal', 'cajero')),
        (SELECT count(*)::int FROM fn_clientes_de_empresa(e.id))
    FROM empresa e
    LEFT JOIN suscripcion su ON su.empresa_id = e.id AND su.estado = 'activa'
    LEFT JOIN plan_suscripcion p ON p.id = su.plan_id
    WHERE e.id = p_empresa_id;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION fn_tiendas_publicas()
RETURNS TABLE (
    id INTEGER, nombre VARCHAR, subdominio VARCHAR, ciudad VARCHAR,
    color_marca VARCHAR, logo_url VARCHAR
) AS $$
    SELECT e.id, e.nombre, e.subdominio, e.ciudad, e.color_marca, e.logo_url
    FROM empresa e
    WHERE e.estado = 'activa'
    ORDER BY e.fecha_creacion, e.id;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION fn_tienda_publica(p_subdominio VARCHAR)
RETURNS TABLE (
    id INTEGER, nombre VARCHAR, subdominio VARCHAR, ciudad VARCHAR, color_marca VARCHAR,
    logo_url VARCHAR, estado VARCHAR, tiene_catalogo BOOLEAN, sitio_propio BOOLEAN
) AS $$
    SELECT e.id, e.nombre, e.subdominio, e.ciudad, e.color_marca, e.logo_url, e.estado,
           EXISTS (SELECT 1 FROM producto p WHERE p.empresa_id = e.id AND p.estado = 'activo'),
           e.id = fn_empresa_por_defecto()
    FROM empresa e
    WHERE e.subdominio = lower(trim(p_subdominio));
$$ LANGUAGE sql STABLE;

DROP FUNCTION IF EXISTS fn_empresa_operativa(INTEGER);

DROP FUNCTION IF EXISTS sp_actualizar_plan(VARCHAR, NUMERIC, INTEGER, BOOLEAN, NUMERIC);
CREATE OR REPLACE FUNCTION sp_actualizar_plan(
    p_codigo         VARCHAR,
    p_precio         NUMERIC,
    p_max_sucursales INTEGER,
    p_ia_generativa  BOOLEAN
) RETURNS VOID AS $$
DECLARE
    v_plan_id INTEGER;
    v_excede  INTEGER;
BEGIN
    SELECT id INTO v_plan_id FROM plan_suscripcion WHERE codigo = p_codigo;
    IF v_plan_id IS NULL THEN
        RAISE EXCEPTION 'plan_no_encontrado';
    END IF;
    IF p_precio < 0 OR p_max_sucursales < 1 THEN
        RAISE EXCEPTION 'plan_valores_invalidos';
    END IF;
    SELECT count(*) INTO v_excede
    FROM suscripcion su
    WHERE su.plan_id = v_plan_id AND su.estado = 'activa'
      AND (SELECT count(*) FROM sucursal s WHERE s.empresa_id = su.empresa_id AND s.estado = 'activa') > p_max_sucursales;
    IF v_excede > 0 THEN
        RAISE EXCEPTION 'plan_limite_menor_al_uso'
            USING DETAIL = format('%s empresa(s) del plan ya usan mas de %s sucursales.', v_excede, p_max_sucursales);
    END IF;
    UPDATE plan_suscripcion
    SET precio_mensual = p_precio, max_sucursales = p_max_sucursales, ia_generativa = p_ia_generativa
    WHERE id = v_plan_id;
END;
$$ LANGUAGE plpgsql;

ALTER TABLE plan_suscripcion DROP COLUMN comision_pct;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
