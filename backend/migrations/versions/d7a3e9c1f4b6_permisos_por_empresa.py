"""SaaS: permisos por empresa (tenant) y CUs del 2do parcial

CU02 Administrar usuarios, roles y permisos, ahora por empresa: cada tienda
tiene su propia matriz rol -> permisos (empresa_rol_permiso). La matriz
global rol_permiso queda como plantilla para empresas nuevas y para el rol
Cliente, que es de toda la plataforma.

- Nuevos permisos para los CUs propios del 2do parcial (prefijo 2P-).
- Trigger: al crear una empresa copia la plantilla de permisos.
- Trigger: el personal hereda la empresa al crearse y no puede quedar en una
  sucursal de otra empresa.
- PA sp_reemplazar_permisos_empresa_rol y funcion fn_permisos_usuario (la
  que usa el backend para decidir que puede hacer cada usuario).

Revision ID: d7a3e9c1f4b6
Revises: c4e8a1f7b2d9
Create Date: 2026-10-21

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "d7a3e9c1f4b6"
down_revision = "c4e8a1f7b2d9"
branch_labels = None
depends_on = None

# CUs nuevos del 2do parcial (los mejorados reusan el permiso del 1er parcial).
PERMISOS_2P = [
    ("2P-CU09", "Gestionar empresas (tenants)"),
    ("2P-CU10", "Gestionar y verificar planes, suscripciones y limites"),
    ("2P-CU11", "Descargar y consultar catalogo offline"),
    ("2P-CU12", "Sincronizar operaciones pendientes"),
    ("2P-CU13", "Consultar operaciones locales y su estado"),
    ("2P-CU14", "Gestionar conflictos de sincronizacion"),
    ("2P-CU15", "Gestionar cambio de prendas"),
    ("2P-CU16", "Arqueo y cierre de caja"),
    ("2P-CU17", "Solicitar y exportar reporte generativo (texto o voz)"),
]

# Roles del personal de una tienda (los que tienen matriz por empresa).
ROLES_TIENDA = "('Administrador', 'Encargado de Sucursal', 'Cajero')"

UPGRADE = f"""
INSERT INTO permiso (nombre, descripcion) VALUES
{",".join(f"('{c}', '{d}')" for c, d in PERMISOS_2P)}
ON CONFLICT (nombre) DO NOTHING;

-- El SuperAdministrador tiene todos los permisos, tambien los nuevos.
INSERT INTO rol_permiso (rol_id, permiso_id)
SELECT r.id, p.id FROM rol r CROSS JOIN permiso p WHERE r.nombre = 'SuperAdministrador'
ON CONFLICT DO NOTHING;

CREATE TABLE empresa_rol_permiso (
    empresa_id INTEGER NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    rol_id     INTEGER NOT NULL REFERENCES rol(id) ON DELETE CASCADE,
    permiso_id INTEGER NOT NULL REFERENCES permiso(id) ON DELETE CASCADE,
    PRIMARY KEY (empresa_id, rol_id, permiso_id)
);

-- Cada empresa existente arranca con la matriz global actual.
INSERT INTO empresa_rol_permiso (empresa_id, rol_id, permiso_id)
SELECT e.id, rp.rol_id, rp.permiso_id
FROM empresa e
CROSS JOIN rol_permiso rp
JOIN rol r ON r.id = rp.rol_id AND r.nombre IN {ROLES_TIENDA};

-- ------------------------------------------------------------------ PA

CREATE OR REPLACE FUNCTION sp_reemplazar_permisos_empresa_rol(
    p_empresa_id  INTEGER,
    p_rol_id      INTEGER,
    p_permiso_ids INTEGER[]
) RETURNS VOID AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM empresa WHERE id = p_empresa_id) THEN
        RAISE EXCEPTION 'empresa_no_encontrada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM rol WHERE id = p_rol_id AND nombre IN {ROLES_TIENDA}) THEN
        RAISE EXCEPTION 'rol_no_es_de_tienda';
    END IF;

    DELETE FROM empresa_rol_permiso WHERE empresa_id = p_empresa_id AND rol_id = p_rol_id;
    IF p_permiso_ids IS NOT NULL THEN
        INSERT INTO empresa_rol_permiso (empresa_id, rol_id, permiso_id)
        SELECT p_empresa_id, p_rol_id, unnest(p_permiso_ids);
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Codigos de permiso efectivos de un usuario: el personal de una empresa
-- usa la matriz de su empresa; el resto (clientes, SuperAdministrador) la
-- matriz global de su rol.
CREATE OR REPLACE FUNCTION fn_permisos_usuario(p_usuario_id INTEGER)
RETURNS SETOF VARCHAR AS $$
    SELECT p.nombre
    FROM usuario u
    JOIN empresa_rol_permiso erp ON erp.empresa_id = u.empresa_id AND erp.rol_id = u.rol_id
    JOIN permiso p ON p.id = erp.permiso_id
    WHERE u.id = p_usuario_id AND u.empresa_id IS NOT NULL
    UNION
    SELECT p.nombre
    FROM usuario u
    JOIN rol_permiso rp ON rp.rol_id = u.rol_id
    JOIN permiso p ON p.id = rp.permiso_id
    WHERE u.id = p_usuario_id AND u.empresa_id IS NULL;
$$ LANGUAGE sql STABLE;

-- Matriz de un rol en una empresa (para la pantalla de permisos).
CREATE OR REPLACE FUNCTION fn_permisos_empresa_rol(p_empresa_id INTEGER, p_rol_id INTEGER)
RETURNS SETOF VARCHAR AS $$
    SELECT p.nombre
    FROM empresa_rol_permiso erp JOIN permiso p ON p.id = erp.permiso_id
    WHERE erp.empresa_id = p_empresa_id AND erp.rol_id = p_rol_id
    ORDER BY p.nombre;
$$ LANGUAGE sql STABLE;

-- ------------------------------------------------------------- triggers

-- Empresa nueva: copia la plantilla global de permisos de los roles de tienda.
CREATE OR REPLACE FUNCTION fn_trg_empresa_permisos_iniciales()
RETURNS trigger AS $$
BEGIN
    INSERT INTO empresa_rol_permiso (empresa_id, rol_id, permiso_id)
    SELECT NEW.id, rp.rol_id, rp.permiso_id
    FROM rol_permiso rp JOIN rol r ON r.id = rp.rol_id AND r.nombre IN {ROLES_TIENDA}
    ON CONFLICT DO NOTHING;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_empresa_permisos_iniciales
AFTER INSERT ON empresa
FOR EACH ROW EXECUTE FUNCTION fn_trg_empresa_permisos_iniciales();

-- Personal: al crearse queda en una empresa (la que indique el backend con
-- arlani.empresa_id, la de su sucursal o, por compatibilidad, Atelier) y
-- nunca puede quedar asignado a una sucursal de otra empresa.
CREATE OR REPLACE FUNCTION fn_trg_empleado_empresa()
RETURNS trigger AS $$
DECLARE
    v_tipo    VARCHAR;
    v_empresa INTEGER;
    v_suc_emp INTEGER;
BEGIN
    SELECT tipo, empresa_id INTO v_tipo, v_empresa FROM usuario WHERE id = NEW.id;
    IF v_tipo = 'superadministrador' THEN
        RETURN NULL;
    END IF;

    IF NEW.sucursal_id IS NOT NULL THEN
        SELECT empresa_id INTO v_suc_emp FROM sucursal WHERE id = NEW.sucursal_id;
    END IF;

    IF v_empresa IS NULL THEN
        v_empresa := coalesce(nullif(current_setting('arlani.empresa_id', true), '')::int,
                              v_suc_emp, fn_empresa_por_defecto());
        UPDATE usuario SET empresa_id = v_empresa WHERE id = NEW.id;
    END IF;

    IF v_suc_emp IS NOT NULL AND v_suc_emp <> v_empresa THEN
        RAISE EXCEPTION 'sucursal_de_otra_empresa';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_empleado_empresa
AFTER INSERT OR UPDATE OF sucursal_id ON empleado
FOR EACH ROW EXECUTE FUNCTION fn_trg_empleado_empresa();
"""

DOWNGRADE = f"""
DROP TRIGGER IF EXISTS trg_empleado_empresa ON empleado;
DROP FUNCTION IF EXISTS fn_trg_empleado_empresa();
DROP TRIGGER IF EXISTS trg_empresa_permisos_iniciales ON empresa;
DROP FUNCTION IF EXISTS fn_trg_empresa_permisos_iniciales();
DROP FUNCTION IF EXISTS fn_permisos_empresa_rol(INTEGER, INTEGER);
DROP FUNCTION IF EXISTS fn_permisos_usuario(INTEGER);
DROP FUNCTION IF EXISTS sp_reemplazar_permisos_empresa_rol(INTEGER, INTEGER, INTEGER[]);
DROP TABLE IF EXISTS empresa_rol_permiso;
DELETE FROM rol_permiso WHERE permiso_id IN (SELECT id FROM permiso WHERE nombre LIKE '2P-%');
DELETE FROM permiso WHERE nombre LIKE '2P-%';
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
