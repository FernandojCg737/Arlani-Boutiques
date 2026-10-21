"""SaaS: bitacora por empresa (CU08)

Cada registro de la bitacora queda asociado a la empresa (tenant) a la que
se refiere, para que cada tienda vea solo lo suyo y el SuperAdministrador
vea todo.

- bitacora.empresa_id + trigger BEFORE INSERT que la deduce:
    1. por lo afectado: reserva / venta / devolucion -> sucursal -> empresa;
       sucursal, marcado de asistencia, empresa, suscripcion, uso del
       probador AR;
    2. si no, por quien lo hizo: el personal de una tienda -> su empresa.
  Lo que no es de ninguna tienda (logins de clientes, acciones de la
  plataforma) queda con empresa_id NULL: solo lo ve el SuperAdministrador.
- Se completan los registros existentes con la misma regla.
- El uso del probador AR (CU09) pasa a quedar en la bitacora (trigger en
  uso_ar_prenda) y se cargan los usos anteriores.

Revision ID: f2b7c4e1d905
Revises: e9c5b2d8a713
Create Date: 2026-10-21

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "f2b7c4e1d905"
down_revision = "e9c5b2d8a713"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE bitacora ADD COLUMN empresa_id INTEGER REFERENCES empresa(id) ON DELETE SET NULL;
CREATE INDEX ix_bitacora_empresa_fecha ON bitacora (empresa_id, fecha DESC);

-- Empresa duena de un producto. El catalogo todavia no es multiempresa:
-- todos los productos son de la tienda original. Cuando producto tenga su
-- empresa_id, basta con cambiar esta funcion.
CREATE OR REPLACE FUNCTION fn_empresa_de_producto(p_producto_id INTEGER)
RETURNS INTEGER AS $$
    SELECT fn_empresa_por_defecto();
$$ LANGUAGE sql STABLE;

-- A que empresa se refiere un registro de bitacora.
CREATE OR REPLACE FUNCTION fn_empresa_de_bitacora(
    p_usuario_id INTEGER, p_entidad VARCHAR, p_entidad_id INTEGER
) RETURNS INTEGER AS $$
DECLARE
    v_empresa INTEGER;
BEGIN
    -- 1. Por lo afectado (asi una compra o reserva de un cliente cae en la
    --    tienda donde ocurrio, aunque el cliente sea de la plataforma).
    IF p_entidad_id IS NOT NULL THEN
        CASE p_entidad
            WHEN 'reserva' THEN
                SELECT s.empresa_id INTO v_empresa FROM reserva r JOIN sucursal s ON s.id = r.sucursal_id
                WHERE r.id = p_entidad_id;
            WHEN 'venta' THEN
                SELECT s.empresa_id INTO v_empresa FROM venta v JOIN sucursal s ON s.id = v.sucursal_id
                WHERE v.id = p_entidad_id;
            WHEN 'devolucion' THEN
                SELECT s.empresa_id INTO v_empresa FROM devolucion d
                JOIN venta v ON v.id = d.venta_id JOIN sucursal s ON s.id = v.sucursal_id
                WHERE d.id = p_entidad_id;
            WHEN 'sucursal' THEN
                SELECT empresa_id INTO v_empresa FROM sucursal WHERE id = p_entidad_id;
            WHEN 'marcado_asistencia' THEN
                SELECT u.empresa_id INTO v_empresa FROM marcado_asistencia m JOIN usuario u ON u.id = m.empleado_id
                WHERE m.id = p_entidad_id;
            WHEN 'empresa' THEN
                SELECT id INTO v_empresa FROM empresa WHERE id = p_entidad_id;
            WHEN 'suscripcion' THEN
                SELECT empresa_id INTO v_empresa FROM suscripcion WHERE id = p_entidad_id;
            WHEN 'uso_ar_prenda' THEN
                SELECT fn_empresa_de_producto(producto_id) INTO v_empresa FROM uso_ar_prenda WHERE id = p_entidad_id;
            ELSE
                v_empresa := NULL;
        END CASE;
    END IF;

    -- 2. Por quien lo hizo: el personal de una tienda.
    IF v_empresa IS NULL THEN
        SELECT empresa_id INTO v_empresa FROM usuario WHERE id = p_usuario_id;
    END IF;

    RETURN v_empresa;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION fn_trg_bitacora_empresa()
RETURNS trigger AS $$
BEGIN
    IF NEW.empresa_id IS NULL THEN
        NEW.empresa_id := fn_empresa_de_bitacora(NEW.usuario_id, NEW.entidad_afectada, NEW.entidad_id);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bitacora_empresa
BEFORE INSERT ON bitacora
FOR EACH ROW EXECUTE FUNCTION fn_trg_bitacora_empresa();

-- Registros existentes.
UPDATE bitacora SET empresa_id = fn_empresa_de_bitacora(usuario_id, entidad_afectada, entidad_id);

-- ------------------------------------------- probador AR en la bitacora
CREATE OR REPLACE FUNCTION fn_trg_bitacora_uso_ar()
RETURNS trigger AS $$
BEGIN
    INSERT INTO bitacora (usuario_id, accion, entidad_afectada, entidad_id, fecha, detalle, ip_address, plataforma)
    VALUES (
        NEW.usuario_id, 'USAR', 'uso_ar_prenda', NEW.id, NEW.fecha,
        format('Probador de realidad aumentada (%s) con "%s"',
               CASE NEW.modo WHEN 'online' THEN 'camara en vivo' ELSE 'foto' END,
               (SELECT nombre FROM producto WHERE id = NEW.producto_id)),
        nullif(current_setting('atelier.client_ip', true), ''),
        nullif(current_setting('atelier.client_platform', true), '')
    );
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bitacora_uso_ar
AFTER INSERT ON uso_ar_prenda
FOR EACH ROW EXECUTE FUNCTION fn_trg_bitacora_uso_ar();

-- Usos anteriores del probador (con su fecha original).
INSERT INTO bitacora (usuario_id, accion, entidad_afectada, entidad_id, fecha, detalle)
SELECT u.usuario_id, 'USAR', 'uso_ar_prenda', u.id, u.fecha,
       format('Probador de realidad aumentada (%s) con "%s"',
              CASE u.modo WHEN 'online' THEN 'camara en vivo' ELSE 'foto' END, p.nombre)
FROM uso_ar_prenda u JOIN producto p ON p.id = u.producto_id;
"""

DOWNGRADE = r"""
DROP TRIGGER IF EXISTS trg_bitacora_uso_ar ON uso_ar_prenda;
DROP FUNCTION IF EXISTS fn_trg_bitacora_uso_ar();
DELETE FROM bitacora WHERE entidad_afectada = 'uso_ar_prenda';
DROP TRIGGER IF EXISTS trg_bitacora_empresa ON bitacora;
DROP FUNCTION IF EXISTS fn_trg_bitacora_empresa();
DROP FUNCTION IF EXISTS fn_empresa_de_bitacora(INTEGER, VARCHAR, INTEGER);
DROP FUNCTION IF EXISTS fn_empresa_de_producto(INTEGER);
DROP INDEX IF EXISTS ix_bitacora_empresa_fecha;
ALTER TABLE bitacora DROP COLUMN IF EXISTS empresa_id;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
