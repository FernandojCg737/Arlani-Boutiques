"""SaaS: control de asistencia por empresa (CU01)

Antes habia una sola configuracion de asistencia (fila unica id = 1): la
misma clave diaria y la misma hora para todas las tiendas. Ahora cada
empresa tiene la suya y la gestiona su Administrador.

- configuracion_asistencia: deja de ser fila unica; una fila por empresa.
- Trigger: cada empresa nueva arranca con su configuracion (08:00).
- fn_estado_asistencia_hoy(p_empresa_id), sp_configurar_hora_asistencia
  (p_empresa_id, p_hora), sp_liberar_asistencia_manual(p_empresa_id).
- sp_marcar_asistencia valida contra la clave de la empresa del empleado.

Revision ID: e9c5b2d8a713
Revises: d7a3e9c1f4b6
Create Date: 2026-10-21

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "e9c5b2d8a713"
down_revision = "d7a3e9c1f4b6"
branch_labels = None
depends_on = None

UPGRADE = r"""
-- ---------------------------------------------------- tabla por empresa
ALTER TABLE configuracion_asistencia DROP CONSTRAINT configuracion_asistencia_singleton;
CREATE SEQUENCE configuracion_asistencia_id_seq OWNED BY configuracion_asistencia.id;
SELECT setval('configuracion_asistencia_id_seq', (SELECT coalesce(max(id), 1) FROM configuracion_asistencia));
ALTER TABLE configuracion_asistencia ALTER COLUMN id SET DEFAULT nextval('configuracion_asistencia_id_seq');

ALTER TABLE configuracion_asistencia ADD COLUMN empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE;
-- La configuracion que existia era la de Atelier Aranier.
UPDATE configuracion_asistencia SET empresa_id = fn_empresa_por_defecto() WHERE id = 1;
INSERT INTO configuracion_asistencia (hora_liberacion, empresa_id)
SELECT '08:00', e.id FROM empresa e
WHERE NOT EXISTS (SELECT 1 FROM configuracion_asistencia c WHERE c.empresa_id = e.id);
ALTER TABLE configuracion_asistencia ALTER COLUMN empresa_id SET NOT NULL;
ALTER TABLE configuracion_asistencia ADD CONSTRAINT uq_configuracion_asistencia_empresa UNIQUE (empresa_id);

-- --------------------------------------------------------------- trigger
CREATE OR REPLACE FUNCTION fn_trg_empresa_config_asistencia()
RETURNS trigger AS $$
BEGIN
    INSERT INTO configuracion_asistencia (hora_liberacion, empresa_id)
    VALUES ('08:00', NEW.id)
    ON CONFLICT (empresa_id) DO NOTHING;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_empresa_config_asistencia
AFTER INSERT ON empresa
FOR EACH ROW EXECUTE FUNCTION fn_trg_empresa_config_asistencia();

-- ------------------------------------------------------------ funciones
DROP FUNCTION IF EXISTS sp_configurar_hora_asistencia(TIME);
DROP FUNCTION IF EXISTS sp_liberar_asistencia_manual();
DROP FUNCTION IF EXISTS fn_estado_asistencia_hoy();

-- Estado de hoy para una empresa (con barrido perezoso: genera la clave del
-- dia y arranca la ventana al pasar la hora configurada).
CREATE OR REPLACE FUNCTION fn_estado_asistencia_hoy(p_empresa_id INTEGER)
RETURNS TABLE(codigo VARCHAR, hora_liberacion TIME, liberado BOOLEAN, ventana_cerrada BOOLEAN,
              ventana_inicio TIMESTAMP, codigo_fecha DATE) AS $$
DECLARE
    v_codigo VARCHAR(10);
    v_hora TIME;
    v_ventana_inicio TIMESTAMP;
    v_hoy_bolivia DATE;
    v_ahora_bolivia TIMESTAMP;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM configuracion_asistencia c WHERE c.empresa_id = p_empresa_id) THEN
        RAISE EXCEPTION 'empresa_no_encontrada';
    END IF;

    v_ahora_bolivia := fn_bolivia_now();
    v_hoy_bolivia := v_ahora_bolivia::DATE;

    UPDATE configuracion_asistencia c
    SET codigo = LPAD(FLOOR(RANDOM() * 900000 + 100000)::TEXT, 6, '0'),
        codigo_fecha = v_hoy_bolivia,
        ventana_inicio = NULL
    WHERE c.empresa_id = p_empresa_id AND (c.codigo_fecha IS NULL OR c.codigo_fecha != v_hoy_bolivia);

    SELECT c.codigo, c.hora_liberacion, c.ventana_inicio
    INTO v_codigo, v_hora, v_ventana_inicio
    FROM configuracion_asistencia c WHERE c.empresa_id = p_empresa_id;

    IF v_ventana_inicio IS NULL AND v_ahora_bolivia::TIME >= v_hora THEN
        UPDATE configuracion_asistencia c SET ventana_inicio = v_ahora_bolivia WHERE c.empresa_id = p_empresa_id;
        v_ventana_inicio := v_ahora_bolivia;
    END IF;

    RETURN QUERY SELECT
        v_codigo,
        v_hora,
        (v_ventana_inicio IS NOT NULL AND v_ahora_bolivia < v_ventana_inicio + INTERVAL '5 minutes'),
        (v_ventana_inicio IS NOT NULL AND v_ahora_bolivia >= v_ventana_inicio + INTERVAL '5 minutes'),
        v_ventana_inicio,
        v_hoy_bolivia;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sp_configurar_hora_asistencia(p_empresa_id INTEGER, p_hora TIME)
RETURNS VOID AS $$
BEGIN
    UPDATE configuracion_asistencia SET hora_liberacion = p_hora WHERE empresa_id = p_empresa_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'empresa_no_encontrada';
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sp_liberar_asistencia_manual(p_empresa_id INTEGER)
RETURNS VOID AS $$
BEGIN
    PERFORM * FROM fn_estado_asistencia_hoy(p_empresa_id);
    UPDATE configuracion_asistencia SET ventana_inicio = fn_bolivia_now() WHERE empresa_id = p_empresa_id;
END;
$$ LANGUAGE plpgsql;

-- Marcar: la clave y la ventana son las de la empresa del empleado.
CREATE OR REPLACE FUNCTION sp_marcar_asistencia(
    p_empleado_id INTEGER, p_codigo VARCHAR, p_latitud DOUBLE PRECISION,
    p_longitud DOUBLE PRECISION, p_foto_url VARCHAR
) RETURNS INTEGER AS $$
DECLARE
    v_empresa INTEGER;
    v_estado RECORD;
    v_sucursal RECORD;
    v_distancia DOUBLE PRECISION;
    v_id INTEGER;
BEGIN
    SELECT u.empresa_id INTO v_empresa FROM usuario u WHERE u.id = p_empleado_id;
    IF v_empresa IS NULL THEN
        RAISE EXCEPTION 'Solo el personal de una tienda puede marcar asistencia.';
    END IF;

    SELECT * INTO v_estado FROM fn_estado_asistencia_hoy(v_empresa);

    IF v_estado.ventana_cerrada THEN
        RAISE EXCEPTION 'La ventana de 5 minutos para marcar ya se cerro.';
    END IF;

    IF NOT v_estado.liberado THEN
        RAISE EXCEPTION 'La clave de asistencia todavia no fue liberada.';
    END IF;

    IF p_codigo IS NULL OR p_codigo != v_estado.codigo THEN
        RAISE EXCEPTION 'La clave ingresada no es correcta.';
    END IF;

    IF EXISTS (SELECT 1 FROM marcado_asistencia WHERE empleado_id = p_empleado_id AND fecha = v_estado.codigo_fecha) THEN
        RAISE EXCEPTION 'Ya marcaste tu asistencia hoy.';
    END IF;

    SELECT s.latitud, s.longitud INTO v_sucursal
    FROM empleado e JOIN sucursal s ON s.id = e.sucursal_id
    WHERE e.id = p_empleado_id;

    IF v_sucursal.latitud IS NOT NULL AND v_sucursal.longitud IS NOT NULL THEN
        v_distancia := fn_distancia_metros(p_latitud, p_longitud, v_sucursal.latitud, v_sucursal.longitud);
        IF v_distancia > 200 THEN
            RAISE EXCEPTION 'Estas a % metros de tu sucursal (maximo 200m). No se pudo marcar.', ROUND(v_distancia::NUMERIC, 0);
        END IF;
    END IF;

    INSERT INTO marcado_asistencia (empleado_id, fecha, latitud, longitud, foto_url)
    VALUES (p_empleado_id, v_estado.codigo_fecha, p_latitud, p_longitud, p_foto_url)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$ LANGUAGE plpgsql;
"""

DOWNGRADE = r"""
DROP TRIGGER IF EXISTS trg_empresa_config_asistencia ON empresa;
DROP FUNCTION IF EXISTS fn_trg_empresa_config_asistencia();
DROP FUNCTION IF EXISTS sp_liberar_asistencia_manual(INTEGER);
DROP FUNCTION IF EXISTS sp_configurar_hora_asistencia(INTEGER, TIME);
DROP FUNCTION IF EXISTS fn_estado_asistencia_hoy(INTEGER);

DELETE FROM configuracion_asistencia WHERE id <> 1;
ALTER TABLE configuracion_asistencia DROP CONSTRAINT IF EXISTS uq_configuracion_asistencia_empresa;
ALTER TABLE configuracion_asistencia DROP COLUMN IF EXISTS empresa_id;
ALTER TABLE configuracion_asistencia ALTER COLUMN id SET DEFAULT 1;
DROP SEQUENCE IF EXISTS configuracion_asistencia_id_seq;
ALTER TABLE configuracion_asistencia ADD CONSTRAINT configuracion_asistencia_singleton CHECK (id = 1);

CREATE OR REPLACE FUNCTION fn_estado_asistencia_hoy()
RETURNS TABLE(codigo VARCHAR, hora_liberacion TIME, liberado BOOLEAN, ventana_cerrada BOOLEAN,
              ventana_inicio TIMESTAMP, codigo_fecha DATE) AS $$
DECLARE
    v_codigo VARCHAR(10);
    v_hora TIME;
    v_ventana_inicio TIMESTAMP;
    v_hoy_bolivia DATE;
    v_ahora_bolivia TIMESTAMP;
BEGIN
    v_ahora_bolivia := fn_bolivia_now();
    v_hoy_bolivia := v_ahora_bolivia::DATE;
    UPDATE configuracion_asistencia c
    SET codigo = LPAD(FLOOR(RANDOM() * 900000 + 100000)::TEXT, 6, '0'),
        codigo_fecha = v_hoy_bolivia, ventana_inicio = NULL
    WHERE c.id = 1 AND (c.codigo_fecha IS NULL OR c.codigo_fecha != v_hoy_bolivia);
    SELECT c.codigo, c.hora_liberacion, c.ventana_inicio INTO v_codigo, v_hora, v_ventana_inicio
    FROM configuracion_asistencia c WHERE c.id = 1;
    IF v_ventana_inicio IS NULL AND v_ahora_bolivia::TIME >= v_hora THEN
        UPDATE configuracion_asistencia SET ventana_inicio = v_ahora_bolivia WHERE id = 1;
        v_ventana_inicio := v_ahora_bolivia;
    END IF;
    RETURN QUERY SELECT v_codigo, v_hora,
        (v_ventana_inicio IS NOT NULL AND v_ahora_bolivia < v_ventana_inicio + INTERVAL '5 minutes'),
        (v_ventana_inicio IS NOT NULL AND v_ahora_bolivia >= v_ventana_inicio + INTERVAL '5 minutes'),
        v_ventana_inicio, v_hoy_bolivia;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sp_configurar_hora_asistencia(p_hora TIME)
RETURNS VOID AS $$
BEGIN
    UPDATE configuracion_asistencia SET hora_liberacion = p_hora WHERE id = 1;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sp_liberar_asistencia_manual()
RETURNS VOID AS $$
BEGIN
    PERFORM * FROM fn_estado_asistencia_hoy();
    UPDATE configuracion_asistencia SET ventana_inicio = fn_bolivia_now() WHERE id = 1;
END;
$$ LANGUAGE plpgsql;

-- sp_marcar_asistencia original (configuracion unica).
CREATE OR REPLACE FUNCTION sp_marcar_asistencia(
    p_empleado_id INTEGER, p_codigo VARCHAR, p_latitud DOUBLE PRECISION,
    p_longitud DOUBLE PRECISION, p_foto_url VARCHAR
) RETURNS INTEGER AS $$
DECLARE
    v_estado RECORD;
    v_sucursal RECORD;
    v_distancia DOUBLE PRECISION;
    v_id INTEGER;
BEGIN
    SELECT * INTO v_estado FROM fn_estado_asistencia_hoy();

    IF v_estado.ventana_cerrada THEN
        RAISE EXCEPTION 'La ventana de 5 minutos para marcar ya se cerro.';
    END IF;

    IF NOT v_estado.liberado THEN
        RAISE EXCEPTION 'La clave de asistencia todavia no fue liberada.';
    END IF;

    IF p_codigo IS NULL OR p_codigo != v_estado.codigo THEN
        RAISE EXCEPTION 'La clave ingresada no es correcta.';
    END IF;

    IF EXISTS (SELECT 1 FROM marcado_asistencia WHERE empleado_id = p_empleado_id AND fecha = v_estado.codigo_fecha) THEN
        RAISE EXCEPTION 'Ya marcaste tu asistencia hoy.';
    END IF;

    SELECT s.latitud, s.longitud INTO v_sucursal
    FROM empleado e JOIN sucursal s ON s.id = e.sucursal_id
    WHERE e.id = p_empleado_id;

    IF v_sucursal.latitud IS NOT NULL AND v_sucursal.longitud IS NOT NULL THEN
        v_distancia := fn_distancia_metros(p_latitud, p_longitud, v_sucursal.latitud, v_sucursal.longitud);
        IF v_distancia > 200 THEN
            RAISE EXCEPTION 'Estas a % metros de tu sucursal (maximo 200m). No se pudo marcar.', ROUND(v_distancia::NUMERIC, 0);
        END IF;
    END IF;

    INSERT INTO marcado_asistencia (empleado_id, fecha, latitud, longitud, foto_url)
    VALUES (p_empleado_id, v_estado.codigo_fecha, p_latitud, p_longitud, p_foto_url)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
