"""SaaS: enlace unico de cada tienda (/tienda-<subdominio>)

Dos boutiques pueden llamarse igual: en vez de rechazar el alta con
"subdominio_en_uso", se le agrega un numero al final (atelier-aranier,
atelier-aranier-2, atelier-aranier-3, ...).

- fn_subdominio_disponible(p_texto): normaliza el texto y devuelve el primer
  subdominio libre. La usa el formulario para mostrar el enlace final.
- sp_crear_empresa: usa fn_subdominio_disponible (el mismo criterio que vio el
  usuario en el formulario, y a salvo de altas simultaneas por el UNIQUE).

Revision ID: c8f3a5d1e742
Revises: b6e1d4f9a250
Create Date: 2026-10-21

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "c8f3a5d1e742"
down_revision = "b6e1d4f9a250"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE OR REPLACE FUNCTION fn_subdominio_disponible(p_texto VARCHAR)
RETURNS VARCHAR AS $$
DECLARE
    -- 36 caracteres deja lugar para "-999" sin pasar el limite de 40.
    v_base VARCHAR := trim(both '-' FROM left(fn_normalizar_subdominio(coalesce(p_texto, '')), 36));
    v_candidato VARCHAR;
    v_n INTEGER := 1;
BEGIN
    IF length(v_base) < 3 THEN
        v_base := 'boutique' || CASE WHEN v_base = '' THEN '' ELSE '-' || v_base END;
    END IF;
    v_candidato := v_base;
    WHILE EXISTS (SELECT 1 FROM empresa WHERE subdominio = v_candidato) LOOP
        v_n := v_n + 1;
        v_candidato := v_base || '-' || v_n;
    END LOOP;
    RETURN v_candidato;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION sp_crear_empresa(
    p_nombre VARCHAR, p_subdominio VARCHAR, p_ciudad VARCHAR, p_color VARCHAR,
    p_email VARCHAR, p_plan_codigo VARCHAR, p_periodo VARCHAR, p_propietario_id INTEGER DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    -- Si el enlace ya lo usa otra tienda, se le agrega un numero.
    v_subdominio VARCHAR := fn_subdominio_disponible(p_subdominio);
    v_plan_id    INTEGER;
    v_empresa_id INTEGER;
BEGIN
    IF length(trim(coalesce(p_nombre, ''))) < 2 THEN
        RAISE EXCEPTION 'empresa_nombre_invalido';
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
"""

DOWNGRADE = r"""
CREATE OR REPLACE FUNCTION sp_crear_empresa(
    p_nombre VARCHAR, p_subdominio VARCHAR, p_ciudad VARCHAR, p_color VARCHAR,
    p_email VARCHAR, p_plan_codigo VARCHAR, p_periodo VARCHAR, p_propietario_id INTEGER DEFAULT NULL
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

    INSERT INTO suscripcion (empresa_id, plan_id, periodo)
    VALUES (v_empresa_id, v_plan_id, p_periodo);

    RETURN v_empresa_id;
END;
$$ LANGUAGE plpgsql;

DROP FUNCTION IF EXISTS fn_subdominio_disponible(VARCHAR);
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
