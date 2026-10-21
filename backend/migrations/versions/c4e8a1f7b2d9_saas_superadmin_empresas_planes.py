"""SaaS: SuperAdministrador, empresas (tenants), planes y suscripciones

CU09 Gestionar empresas (tenants) y CU10 Gestionar y verificar planes,
suscripciones y limites. Toda escritura pasa por funciones/PA de Postgres;
los triggers calculan montos y vencimientos, hacen cumplir el limite de
sucursales del plan y dejan rastro en la bitacora (CU08).

Revision ID: c4e8a1f7b2d9
Revises: b9e4c2a7f310
Create Date: 2026-10-20

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "c4e8a1f7b2d9"
down_revision = "b9e4c2a7f310"
branch_labels = None
depends_on = None

SUPERADMIN_EMAIL = "superadmin@arlaniboutiques.com"
# Hash bcrypt de la contrasena inicial del SuperAdministrador (cambiarla desde
# su perfil despues del primer ingreso).
SUPERADMIN_PASSWORD_HASH = "$2b$12$DqW/CZCG9LSLfKbDurXq7.D/6nmi56qrYaHEDQsICG/kjdLih54bq"

# ----------------------------------------------------------------- tablas

TABLAS = """
CREATE TABLE plan_suscripcion (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(30)   NOT NULL UNIQUE,
    nombre          VARCHAR(60)   NOT NULL,
    precio_mensual  NUMERIC(10,2) NOT NULL CHECK (precio_mensual >= 0),
    max_sucursales  INTEGER       NOT NULL CHECK (max_sucursales > 0),
    dias_prueba     INTEGER       CHECK (dias_prueba IS NULL OR dias_prueba > 0),
    ia_generativa   BOOLEAN       NOT NULL DEFAULT FALSE,
    activo          BOOLEAN       NOT NULL DEFAULT TRUE,
    orden           INTEGER       NOT NULL DEFAULT 0
);

CREATE TABLE empresa (
    id                  SERIAL PRIMARY KEY,
    nombre              VARCHAR(120) NOT NULL,
    subdominio          VARCHAR(40)  NOT NULL UNIQUE,
    ciudad              VARCHAR(80),
    color_marca         VARCHAR(7)   NOT NULL DEFAULT '#1f2a44',
    logo_url            VARCHAR(500),
    email_contacto      VARCHAR(150),
    estado              VARCHAR(20)  NOT NULL DEFAULT 'activa'
                        CHECK (estado IN ('activa', 'suspendida')),
    propietario_id      INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    fecha_creacion      TIMESTAMP    NOT NULL DEFAULT now(),
    fecha_actualizacion TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT ck_empresa_subdominio CHECK (subdominio ~ '^[a-z0-9]([a-z0-9-]{1,38}[a-z0-9])$')
);

CREATE TABLE suscripcion (
    id             SERIAL PRIMARY KEY,
    empresa_id     INTEGER       NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    plan_id        INTEGER       NOT NULL REFERENCES plan_suscripcion(id),
    periodo        VARCHAR(10)   NOT NULL CHECK (periodo IN ('mensual', 'anual', 'prueba')),
    monto          NUMERIC(10,2) NOT NULL DEFAULT 0,
    fecha_inicio   DATE          NOT NULL DEFAULT CURRENT_DATE,
    fecha_fin      DATE,
    estado         VARCHAR(20)   NOT NULL DEFAULT 'activa'
                   CHECK (estado IN ('activa', 'reemplazada', 'cancelada', 'vencida')),
    fecha_registro TIMESTAMP     NOT NULL DEFAULT now()
);
-- Una sola suscripcion vigente por empresa.
CREATE UNIQUE INDEX ux_suscripcion_activa ON suscripcion (empresa_id) WHERE estado = 'activa';

-- Cada sucursal y cada usuario del personal pertenecen a una empresa. Los
-- clientes y el SuperAdministrador son de la plataforma (empresa_id NULL).
ALTER TABLE sucursal ADD COLUMN empresa_id INTEGER REFERENCES empresa(id);
ALTER TABLE usuario  ADD COLUMN empresa_id INTEGER REFERENCES empresa(id);
CREATE INDEX ix_sucursal_empresa ON sucursal (empresa_id);
CREATE INDEX ix_usuario_empresa ON usuario (empresa_id);

-- SuperAdministrador: especializacion de Administrador (hereda todo su
-- acceso) con potestad sobre todas las empresas.
CREATE TABLE superadministrador (
    id INTEGER PRIMARY KEY REFERENCES administrador(id) ON DELETE CASCADE
);
"""

# --------------------------------------------------------------- funciones

FUNCIONES = r"""
-- Empresa a la que se asignan sucursales creadas por las pantallas del
-- 1er parcial (que no conocen empresas): la tienda original, Atelier Aranier.
CREATE OR REPLACE FUNCTION fn_empresa_por_defecto()
RETURNS INTEGER AS $$
    SELECT id FROM empresa WHERE subdominio = 'atelier-aranier';
$$ LANGUAGE sql STABLE;

-- Normaliza un texto a subdominio: minusculas, sin acentos ni espacios.
CREATE OR REPLACE FUNCTION fn_normalizar_subdominio(p_texto VARCHAR)
RETURNS VARCHAR AS $$
    SELECT trim(both '-' FROM regexp_replace(
        translate(lower(trim(p_texto)), 'áéíóúüñ', 'aeiouun'),
        '[^a-z0-9]+', '-', 'g'
    ));
$$ LANGUAGE sql IMMUTABLE;

-- Sucursales activas de una empresa frente al maximo de su plan vigente.
CREATE OR REPLACE FUNCTION fn_verificar_limite_sucursales(p_empresa_id INTEGER)
RETURNS TABLE (usadas INTEGER, maximo INTEGER, disponibles INTEGER) AS $$
    SELECT
        (SELECT count(*)::int FROM sucursal s WHERE s.empresa_id = p_empresa_id AND s.estado = 'activa'),
        p.max_sucursales,
        GREATEST(p.max_sucursales - (SELECT count(*)::int FROM sucursal s
                                     WHERE s.empresa_id = p_empresa_id AND s.estado = 'activa'), 0)
    FROM suscripcion su
    JOIN plan_suscripcion p ON p.id = su.plan_id
    WHERE su.empresa_id = p_empresa_id AND su.estado = 'activa';
$$ LANGUAGE sql STABLE;

-- ------------------------------------------------------ PA: empresas (CU09)

CREATE OR REPLACE FUNCTION sp_crear_empresa(
    p_nombre         VARCHAR,
    p_subdominio     VARCHAR,
    p_ciudad         VARCHAR,
    p_color          VARCHAR,
    p_email          VARCHAR,
    p_plan_codigo    VARCHAR,
    p_periodo        VARCHAR,
    p_propietario_id INTEGER DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_subdominio VARCHAR := fn_normalizar_subdominio(p_subdominio);
    v_plan_id    INTEGER;
    v_empresa_id INTEGER;
BEGIN
    IF length(trim(coalesce(p_nombre, ''))) < 2 THEN
        RAISE EXCEPTION 'empresa_nombre_invalido';
    END IF;
    IF EXISTS (SELECT 1 FROM empresa WHERE subdominio = v_subdominio) THEN
        RAISE EXCEPTION 'subdominio_en_uso';
    END IF;
    SELECT id INTO v_plan_id FROM plan_suscripcion WHERE codigo = p_plan_codigo AND activo;
    IF v_plan_id IS NULL THEN
        RAISE EXCEPTION 'plan_no_encontrado';
    END IF;

    INSERT INTO empresa (nombre, subdominio, ciudad, color_marca, email_contacto, propietario_id)
    VALUES (trim(p_nombre), v_subdominio, nullif(trim(p_ciudad), ''),
            coalesce(nullif(p_color, ''), '#1f2a44'), nullif(trim(p_email), ''), p_propietario_id)
    RETURNING id INTO v_empresa_id;

    -- Monto y vencimiento los calcula trg_suscripcion_preparar.
    INSERT INTO suscripcion (empresa_id, plan_id, periodo)
    VALUES (v_empresa_id, v_plan_id, p_periodo);

    RETURN v_empresa_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sp_actualizar_empresa(
    p_id     INTEGER,
    p_nombre VARCHAR,
    p_ciudad VARCHAR,
    p_color  VARCHAR,
    p_email  VARCHAR
) RETURNS VOID AS $$
BEGIN
    IF length(trim(coalesce(p_nombre, ''))) < 2 THEN
        RAISE EXCEPTION 'empresa_nombre_invalido';
    END IF;
    UPDATE empresa
    SET nombre = trim(p_nombre),
        ciudad = nullif(trim(p_ciudad), ''),
        color_marca = coalesce(nullif(p_color, ''), color_marca),
        email_contacto = nullif(trim(p_email), '')
    WHERE id = p_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'empresa_no_encontrada';
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sp_cambiar_estado_empresa(p_id INTEGER, p_estado VARCHAR)
RETURNS VOID AS $$
BEGIN
    IF p_estado NOT IN ('activa', 'suspendida') THEN
        RAISE EXCEPTION 'estado_invalido';
    END IF;
    UPDATE empresa SET estado = p_estado WHERE id = p_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'empresa_no_encontrada';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Cambiar de plan: el nuevo plan tiene que cubrir las sucursales activas
-- que la empresa ya tiene (CU10: verificar limites).
CREATE OR REPLACE FUNCTION sp_cambiar_plan_empresa(p_id INTEGER, p_plan_codigo VARCHAR, p_periodo VARCHAR)
RETURNS VOID AS $$
DECLARE
    v_plan   plan_suscripcion%ROWTYPE;
    v_usadas INTEGER;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM empresa WHERE id = p_id) THEN
        RAISE EXCEPTION 'empresa_no_encontrada';
    END IF;
    SELECT * INTO v_plan FROM plan_suscripcion WHERE codigo = p_plan_codigo AND activo;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'plan_no_encontrado';
    END IF;
    SELECT count(*) INTO v_usadas FROM sucursal WHERE empresa_id = p_id AND estado = 'activa';
    IF v_usadas > v_plan.max_sucursales THEN
        RAISE EXCEPTION 'plan_no_cubre_sucursales'
            USING DETAIL = format('La empresa tiene %s sucursales activas y el plan %s admite %s.',
                                  v_usadas, v_plan.nombre, v_plan.max_sucursales);
    END IF;
    -- La suscripcion anterior queda "reemplazada" (trg_suscripcion_preparar).
    INSERT INTO suscripcion (empresa_id, plan_id, periodo) VALUES (p_id, v_plan.id, p_periodo);
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sp_eliminar_empresa(p_id INTEGER)
RETURNS VOID AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM sucursal WHERE empresa_id = p_id) THEN
        RAISE EXCEPTION 'empresa_con_sucursales';
    END IF;
    IF EXISTS (SELECT 1 FROM usuario WHERE empresa_id = p_id) THEN
        RAISE EXCEPTION 'empresa_con_usuarios';
    END IF;
    DELETE FROM empresa WHERE id = p_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'empresa_no_encontrada';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- --------------------------------------------------------- PA: planes (CU10)

-- Bajar el maximo de sucursales de un plan no puede dejar a una empresa
-- suscrita por encima del limite nuevo.
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

-- ------------------------------------------------- consultas del panel

CREATE OR REPLACE FUNCTION fn_listar_empresas()
RETURNS TABLE (
    id INTEGER, nombre VARCHAR, subdominio VARCHAR, ciudad VARCHAR, color_marca VARCHAR,
    email_contacto VARCHAR, estado VARCHAR, fecha_creacion TIMESTAMP,
    plan_codigo VARCHAR, plan_nombre VARCHAR, periodo VARCHAR, monto NUMERIC, fecha_fin DATE,
    sucursales_activas INTEGER, max_sucursales INTEGER, usuarios INTEGER, ventas_total NUMERIC
) AS $$
    SELECT
        e.id, e.nombre, e.subdominio, e.ciudad, e.color_marca, e.email_contacto, e.estado, e.fecha_creacion,
        p.codigo, p.nombre, su.periodo, su.monto, su.fecha_fin,
        (SELECT count(*)::int FROM sucursal s WHERE s.empresa_id = e.id AND s.estado = 'activa'),
        p.max_sucursales,
        (SELECT count(*)::int FROM usuario u WHERE u.empresa_id = e.id),
        coalesce((SELECT sum(v.total) FROM venta v JOIN sucursal s ON s.id = v.sucursal_id
                  WHERE s.empresa_id = e.id AND v.estado <> 'anulada'), 0)
    FROM empresa e
    LEFT JOIN suscripcion su ON su.empresa_id = e.id AND su.estado = 'activa'
    LEFT JOIN plan_suscripcion p ON p.id = su.plan_id
    ORDER BY e.fecha_creacion;
$$ LANGUAGE sql STABLE;

-- Ingreso mensual recurrente (MRR): una anual aporta su monto / 12.
CREATE OR REPLACE FUNCTION fn_mrr_suscripcion(p_periodo VARCHAR, p_monto NUMERIC)
RETURNS NUMERIC AS $$
    SELECT CASE p_periodo WHEN 'anual' THEN round(p_monto / 12, 2)
                          WHEN 'mensual' THEN p_monto
                          ELSE 0 END;
$$ LANGUAGE sql IMMUTABLE;

CREATE OR REPLACE FUNCTION fn_resumen_plataforma()
RETURNS TABLE (
    empresas_total INTEGER, empresas_activas INTEGER, empresas_suspendidas INTEGER, empresas_prueba INTEGER,
    mrr NUMERIC, sucursales_activas INTEGER, personal INTEGER, clientes INTEGER, ventas_mes NUMERIC
) AS $$
    SELECT
        (SELECT count(*)::int FROM empresa),
        (SELECT count(*)::int FROM empresa WHERE estado = 'activa'),
        (SELECT count(*)::int FROM empresa WHERE estado = 'suspendida'),
        (SELECT count(*)::int FROM suscripcion WHERE estado = 'activa' AND periodo = 'prueba'),
        (SELECT coalesce(sum(fn_mrr_suscripcion(su.periodo, su.monto)), 0)
           FROM suscripcion su JOIN empresa e ON e.id = su.empresa_id
          WHERE su.estado = 'activa' AND e.estado = 'activa'),
        (SELECT count(*)::int FROM sucursal WHERE estado = 'activa'),
        (SELECT count(*)::int FROM usuario WHERE empresa_id IS NOT NULL),
        (SELECT count(*)::int FROM usuario WHERE tipo = 'cliente'),
        (SELECT coalesce(sum(total), 0) FROM venta
          WHERE estado <> 'anulada' AND fecha >= date_trunc('month', now()));
$$ LANGUAGE sql STABLE;

-- MRR de los ultimos p_meses meses: lo que aportaban las suscripciones
-- vigentes al cierre de cada mes (o hoy, para el mes en curso).
CREATE OR REPLACE FUNCTION fn_ingresos_mensuales(p_meses INTEGER DEFAULT 6)
RETURNS TABLE (mes DATE, ingresos NUMERIC) AS $$
    WITH meses AS (
        SELECT m::date AS mes,
               LEAST((m + interval '1 month - 1 day')::date, CURRENT_DATE) AS corte
        FROM generate_series(date_trunc('month', now()) - make_interval(months => p_meses - 1),
                             date_trunc('month', now()), interval '1 month') AS m
    )
    SELECT meses.mes,
           coalesce(sum(fn_mrr_suscripcion(su.periodo, su.monto))
                    FILTER (WHERE e.id IS NOT NULL), 0)
    FROM meses
    LEFT JOIN suscripcion su
           ON su.fecha_inicio <= meses.corte
          AND (su.fecha_fin IS NULL OR su.fecha_fin >= meses.corte)
          AND su.estado <> 'cancelada'
    LEFT JOIN empresa e ON e.id = su.empresa_id
    GROUP BY meses.mes
    ORDER BY meses.mes;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION fn_distribucion_planes()
RETURNS TABLE (codigo VARCHAR, nombre VARCHAR, empresas INTEGER) AS $$
    SELECT p.codigo, p.nombre,
           (SELECT count(*)::int FROM suscripcion su WHERE su.plan_id = p.id AND su.estado = 'activa')
    FROM plan_suscripcion p
    ORDER BY p.orden;
$$ LANGUAGE sql STABLE;
"""

# ---------------------------------------------------------------- triggers

TRIGGERS = r"""
-- Suscripcion nueva: monto y vencimiento segun plan y periodo, y la
-- suscripcion vigente anterior de la empresa pasa a "reemplazada".
CREATE OR REPLACE FUNCTION fn_trg_suscripcion_preparar()
RETURNS trigger AS $$
DECLARE
    v_plan plan_suscripcion%ROWTYPE;
BEGIN
    SELECT * INTO v_plan FROM plan_suscripcion WHERE id = NEW.plan_id;

    IF v_plan.dias_prueba IS NOT NULL THEN
        NEW.periodo := 'prueba';
    ELSIF NEW.periodo NOT IN ('mensual', 'anual') THEN
        RAISE EXCEPTION 'periodo_invalido';
    END IF;

    NEW.monto := CASE NEW.periodo
                     WHEN 'anual' THEN v_plan.precio_mensual * 10   -- 2 meses de regalo
                     WHEN 'mensual' THEN v_plan.precio_mensual
                     ELSE 0 END;
    NEW.fecha_fin := CASE NEW.periodo
                         WHEN 'prueba' THEN NEW.fecha_inicio + v_plan.dias_prueba
                         WHEN 'anual' THEN (NEW.fecha_inicio + interval '1 year')::date
                         ELSE (NEW.fecha_inicio + interval '1 month')::date END;

    IF NEW.estado = 'activa' THEN
        -- La anterior se cierra el dia previo al inicio de la nueva, asi un
        -- cambio de plan no cuenta doble en los ingresos del mes.
        UPDATE suscripcion
        SET estado = 'reemplazada',
            fecha_fin = LEAST(coalesce(fecha_fin, NEW.fecha_inicio), NEW.fecha_inicio - 1)
        WHERE empresa_id = NEW.empresa_id AND estado = 'activa';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_suscripcion_preparar
BEFORE INSERT ON suscripcion
FOR EACH ROW EXECUTE FUNCTION fn_trg_suscripcion_preparar();

-- Empresa: fecha de actualizacion siempre al dia.
CREATE OR REPLACE FUNCTION fn_trg_empresa_actualizacion()
RETURNS trigger AS $$
BEGIN
    NEW.fecha_actualizacion := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_empresa_actualizacion
BEFORE UPDATE ON empresa
FOR EACH ROW EXECUTE FUNCTION fn_trg_empresa_actualizacion();

-- Sucursal: pertenece a una empresa, la empresa tiene que estar activa y
-- no puede pasarse del maximo de sucursales de su plan (CU10).
CREATE OR REPLACE FUNCTION fn_trg_sucursal_limite_plan()
RETURNS trigger AS $$
DECLARE
    v_estado  VARCHAR;
    v_maximo  INTEGER;
    v_usadas  INTEGER;
BEGIN
    IF NEW.empresa_id IS NULL THEN
        NEW.empresa_id := fn_empresa_por_defecto();
    END IF;
    IF NEW.empresa_id IS NULL OR NEW.estado <> 'activa' THEN
        RETURN NEW;
    END IF;
    -- Solo se valida cuando la sucursal pasa a contar como activa.
    IF TG_OP = 'UPDATE' THEN
        IF OLD.estado = 'activa' AND OLD.empresa_id IS NOT DISTINCT FROM NEW.empresa_id THEN
            RETURN NEW;
        END IF;
    END IF;

    SELECT estado INTO v_estado FROM empresa WHERE id = NEW.empresa_id;
    IF v_estado = 'suspendida' THEN
        RAISE EXCEPTION 'empresa_suspendida';
    END IF;

    SELECT p.max_sucursales INTO v_maximo
    FROM suscripcion su JOIN plan_suscripcion p ON p.id = su.plan_id
    WHERE su.empresa_id = NEW.empresa_id AND su.estado = 'activa';

    SELECT count(*) INTO v_usadas FROM sucursal
    WHERE empresa_id = NEW.empresa_id AND estado = 'activa' AND id IS DISTINCT FROM NEW.id;

    IF v_maximo IS NOT NULL AND v_usadas >= v_maximo THEN
        RAISE EXCEPTION 'limite_sucursales_plan'
            USING DETAIL = format('El plan permite %s sucursales activas.', v_maximo);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sucursal_limite_plan
BEFORE INSERT OR UPDATE OF estado, empresa_id ON sucursal
FOR EACH ROW EXECUTE FUNCTION fn_trg_sucursal_limite_plan();

-- Auditoria (CU08): cada cambio en empresas, suscripciones y planes queda
-- en la bitacora con el usuario que lo hizo. El backend pasa el usuario, la
-- IP y la plataforma con SET LOCAL (ver app/core/audit.py).
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

    -- Cada tabla tiene sus propias columnas: una rama por tabla (en PL/pgSQL
    -- no se puede nombrar NEW.nombre si la tabla no tiene esa columna).
    IF TG_TABLE_NAME = 'empresa' THEN
        IF TG_OP = 'DELETE' THEN
            v_id := OLD.id;
            v_detalle := format('Empresa "%s" eliminada (%s.arlani.bo)', OLD.nombre, OLD.subdominio);
        ELSIF TG_OP = 'UPDATE' AND OLD.estado IS DISTINCT FROM NEW.estado THEN
            v_id := NEW.id;
            v_accion := CASE NEW.estado WHEN 'suspendida' THEN 'SUSPENDER' ELSE 'REACTIVAR' END;
            v_detalle := format('Empresa "%s" %s', NEW.nombre,
                                CASE NEW.estado WHEN 'suspendida' THEN 'suspendida' ELSE 'reactivada' END);
        ELSE
            v_id := NEW.id;
            v_detalle := format('Empresa "%s" (%s.arlani.bo)', NEW.nombre, NEW.subdominio);
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

CREATE TRIGGER trg_auditar_empresa
AFTER INSERT OR UPDATE OR DELETE ON empresa
FOR EACH ROW EXECUTE FUNCTION fn_trg_auditar_plataforma();

CREATE TRIGGER trg_auditar_suscripcion
AFTER INSERT ON suscripcion
FOR EACH ROW EXECUTE FUNCTION fn_trg_auditar_plataforma();

CREATE TRIGGER trg_auditar_plan
AFTER UPDATE ON plan_suscripcion
FOR EACH ROW EXECUTE FUNCTION fn_trg_auditar_plataforma();
"""

# ------------------------------------------------------------------- datos

SEED = f"""
DO $$
DECLARE
    v_atelier   INTEGER;
    v_rol_id    INTEGER;
    v_usuario   INTEGER;
    v_inicio    DATE;
BEGIN
    -- Planes del requerimiento (Basico / Profesional) + plan de prueba.
    INSERT INTO plan_suscripcion (codigo, nombre, precio_mensual, max_sucursales, dias_prueba, ia_generativa, orden) VALUES
        ('prueba',      'Prueba',      0,   1,  14,   FALSE, 1),
        ('basico',      'Básico',      199, 2,  NULL, FALSE, 2),
        ('profesional', 'Profesional', 499, 10, NULL, TRUE,  3);

    -- Atelier Aranier pasa a ser la primera empresa (tenant) de la plataforma.
    SELECT coalesce(min(fecha_creacion), CURRENT_DATE) INTO v_inicio FROM sucursal;
    INSERT INTO empresa (nombre, subdominio, ciudad, color_marca, email_contacto, fecha_creacion)
    VALUES ('Atelier Aranier', 'atelier-aranier', 'Santa Cruz', '#203c40', 'contacto@atelieraranier.com', v_inicio)
    RETURNING id INTO v_atelier;

    INSERT INTO suscripcion (empresa_id, plan_id, periodo, fecha_inicio)
    SELECT v_atelier, id, 'anual', v_inicio FROM plan_suscripcion WHERE codigo = 'profesional';

    UPDATE sucursal SET empresa_id = v_atelier WHERE empresa_id IS NULL;
    -- Todo el personal actual (incluido admin@atelieraranier.com) es de Atelier.
    UPDATE usuario SET empresa_id = v_atelier
    WHERE tipo IN ('administrador', 'encargado_sucursal', 'cajero');

    -- Rol y cuenta del SuperAdministrador de la plataforma.
    INSERT INTO rol (nombre, descripcion)
    VALUES ('SuperAdministrador', 'Potestad sobre toda la plataforma Arlani Boutiques y todas sus empresas.')
    ON CONFLICT (nombre) DO NOTHING;
    SELECT id INTO v_rol_id FROM rol WHERE nombre = 'SuperAdministrador';
    INSERT INTO rol_permiso (rol_id, permiso_id)
    SELECT v_rol_id, id FROM permiso ON CONFLICT DO NOTHING;

    INSERT INTO usuario (nombre, email, password_hash, estado, fecha_registro, tipo, metodo_registro, rol_id)
    VALUES ('Super Administrador', '{SUPERADMIN_EMAIL}', '{SUPERADMIN_PASSWORD_HASH}',
            'activo', CURRENT_DATE, 'superadministrador', 'sistema', v_rol_id)
    RETURNING id INTO v_usuario;
    INSERT INTO empleado (id, sucursal_id) VALUES (v_usuario, NULL);
    INSERT INTO administrador (id) VALUES (v_usuario);
    INSERT INTO superadministrador (id) VALUES (v_usuario);
END $$;
"""

DOWNGRADE = f"""
DROP TRIGGER IF EXISTS trg_auditar_plan ON plan_suscripcion;
DROP TRIGGER IF EXISTS trg_auditar_suscripcion ON suscripcion;
DROP TRIGGER IF EXISTS trg_auditar_empresa ON empresa;
DROP TRIGGER IF EXISTS trg_sucursal_limite_plan ON sucursal;
DROP TRIGGER IF EXISTS trg_empresa_actualizacion ON empresa;
DROP TRIGGER IF EXISTS trg_suscripcion_preparar ON suscripcion;
DROP FUNCTION IF EXISTS fn_trg_auditar_plataforma();
DROP FUNCTION IF EXISTS fn_trg_sucursal_limite_plan();
DROP FUNCTION IF EXISTS fn_trg_empresa_actualizacion();
DROP FUNCTION IF EXISTS fn_trg_suscripcion_preparar();
DROP FUNCTION IF EXISTS fn_distribucion_planes();
DROP FUNCTION IF EXISTS fn_ingresos_mensuales(INTEGER);
DROP FUNCTION IF EXISTS fn_resumen_plataforma();
DROP FUNCTION IF EXISTS fn_mrr_suscripcion(VARCHAR, NUMERIC);
DROP FUNCTION IF EXISTS fn_listar_empresas();
DROP FUNCTION IF EXISTS sp_actualizar_plan(VARCHAR, NUMERIC, INTEGER, BOOLEAN);
DROP FUNCTION IF EXISTS sp_eliminar_empresa(INTEGER);
DROP FUNCTION IF EXISTS sp_cambiar_plan_empresa(INTEGER, VARCHAR, VARCHAR);
DROP FUNCTION IF EXISTS sp_cambiar_estado_empresa(INTEGER, VARCHAR);
DROP FUNCTION IF EXISTS sp_actualizar_empresa(INTEGER, VARCHAR, VARCHAR, VARCHAR, VARCHAR);
DROP FUNCTION IF EXISTS sp_crear_empresa(VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, INTEGER);
DROP FUNCTION IF EXISTS fn_verificar_limite_sucursales(INTEGER);
DROP FUNCTION IF EXISTS fn_normalizar_subdominio(VARCHAR);
DROP FUNCTION IF EXISTS fn_empresa_por_defecto();

DELETE FROM bitacora WHERE usuario_id IN (SELECT id FROM usuario WHERE email = '{SUPERADMIN_EMAIL}');
DELETE FROM superadministrador;
DELETE FROM administrador WHERE id IN (SELECT id FROM usuario WHERE email = '{SUPERADMIN_EMAIL}');
DELETE FROM empleado WHERE id IN (SELECT id FROM usuario WHERE email = '{SUPERADMIN_EMAIL}');
DELETE FROM usuario WHERE email = '{SUPERADMIN_EMAIL}';
DELETE FROM rol_permiso WHERE rol_id IN (SELECT id FROM rol WHERE nombre = 'SuperAdministrador');
DELETE FROM rol WHERE nombre = 'SuperAdministrador';

DROP TABLE IF EXISTS superadministrador;
ALTER TABLE usuario DROP COLUMN IF EXISTS empresa_id;
ALTER TABLE sucursal DROP COLUMN IF EXISTS empresa_id;
DROP TABLE IF EXISTS suscripcion;
DROP TABLE IF EXISTS empresa;
DROP TABLE IF EXISTS plan_suscripcion;
"""


def upgrade() -> None:
    op.execute(TABLAS)
    op.execute(FUNCIONES)
    op.execute(TRIGGERS)
    op.execute(SEED)


def downgrade() -> None:
    op.execute(DOWNGRADE)
