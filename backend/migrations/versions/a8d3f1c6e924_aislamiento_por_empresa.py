"""SaaS: cada tienda ve y modifica solo sus propios datos (Row Level Security)

Cuando la peticion es del personal de una tienda, el backend cambia en esa
transaccion al rol arlani_tenant (SET LOCAL ROLE) y guarda su empresa en
arlani.empresa_scope (ver app/db/session.py). Las politicas de abajo solo
aplican a ese rol: el SuperAdministrador, los clientes y la portada siguen
viendo todo (la conexion normal es duena de las tablas).

- producto, marca, temporada, notificacion y chatbot pasan a tener empresa_id
  (lo existente queda en la empresa por defecto; lo nuevo toma la empresa del
  que lo crea).
- Lo demas se deduce: por la sucursal (inventario, reservas, ventas, lineas
  de carrito), por el producto (imagenes, prendas AR, lineas, vistas,
  recomendaciones, usos del probador) o por la fila padre (detalles, pagos,
  devoluciones, colecciones...). Una politica que mira a otra tabla con RLS
  hereda su filtro.
- Categorias, colores y tallas son comunes a toda la plataforma.
- Proveedores: quedan en la empresa de quien los registra.

Revision ID: a8d3f1c6e924
Revises: f6a2c9d4b813
Create Date: 2026-10-21

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "a8d3f1c6e924"
down_revision = "f6a2c9d4b813"
branch_labels = None
depends_on = None

# (tabla, condicion) para el rol arlani_tenant. fn_empresa_actual() es la
# empresa de la peticion; "x IN (SELECT id FROM t)" hereda el filtro de t.
SUC = "sucursal_id IN (SELECT id FROM sucursal WHERE empresa_id = fn_empresa_actual())"
POLITICAS = [
    ("sucursal", "empresa_id = fn_empresa_actual()"),
    ("producto", "empresa_id = fn_empresa_actual()"),
    ("marca", "empresa_id = fn_empresa_actual()"),
    ("temporada", "empresa_id = fn_empresa_actual()"),
    ("notificacion", "empresa_id = fn_empresa_actual()"),
    ("chatbot", "empresa_id = fn_empresa_actual()"),
    ("coleccion", "temporada_id IN (SELECT id FROM temporada)"),
    ("producto_imagen", "producto_id IN (SELECT id FROM producto)"),
    ("prenda_ar", "producto_id IN (SELECT id FROM producto)"),
    ("producto_relacionado", "producto_id IN (SELECT id FROM producto)"),
    ("item_linea", "producto_id IN (SELECT id FROM producto)"),
    ("recomendacion", "producto_id IN (SELECT id FROM producto)"),
    ("vista_producto", "producto_id IN (SELECT id FROM producto)"),
    ("uso_ar_prenda", "producto_id IN (SELECT id FROM producto)"),
    ("inventario", f"{SUC} AND producto_id IN (SELECT id FROM producto)"),
    ("movimiento_inventario", "inventario_id IN (SELECT id FROM inventario)"),
    ("detalle_carrito", SUC),
    ("reserva", SUC),
    ("detalle_reserva", "reserva_id IN (SELECT id FROM reserva)"),
    ("venta", SUC),
    ("venta_digital", "id IN (SELECT id FROM venta)"),
    ("venta_presencial", "id IN (SELECT id FROM venta)"),
    ("detalle_venta_digital", "venta_digital_id IN (SELECT id FROM venta_digital)"),
    ("detalle_venta_presencial", "venta_presencial_id IN (SELECT id FROM venta_presencial)"),
    ("pago", "venta_id IN (SELECT id FROM venta)"),
    ("transaccion", "pago_id IN (SELECT id FROM pago)"),
    ("devolucion", "venta_id IN (SELECT id FROM venta)"),
    ("detalle_devolucion", "devolucion_id IN (SELECT id FROM devolucion)"),
    ("calificacion", "venta_id IN (SELECT id FROM venta)"),
    ("chatbot_mensaje", "chatbot_id IN (SELECT id FROM chatbot)"),
    ("reporte", "empleado_id IN (SELECT id FROM usuario WHERE empresa_id = fn_empresa_actual())"),
    ("proveedor", "id IN (SELECT id FROM usuario WHERE empresa_id = fn_empresa_actual())"),
]

BASE = r"""
-- ------------------------------------------------ empresa de la peticion
CREATE OR REPLACE FUNCTION fn_empresa_actual()
RETURNS INTEGER AS $$
    SELECT nullif(current_setting('arlani.empresa_scope', true), '')::int;
$$ LANGUAGE sql STABLE;

-- Empresa para una fila nueva: la de la peticion o, sin ella (SuperAdmin,
-- procesos), la empresa por defecto.
CREATE OR REPLACE FUNCTION fn_empresa_para_alta()
RETURNS INTEGER AS $$
    SELECT coalesce(fn_empresa_actual(),
                    nullif(current_setting('arlani.empresa_id', true), '')::int,
                    fn_empresa_por_defecto());
$$ LANGUAGE sql STABLE;

-- ------------------------------------------------------- columnas nuevas
ALTER TABLE producto ADD COLUMN empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE;
ALTER TABLE marca ADD COLUMN empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE;
ALTER TABLE temporada ADD COLUMN empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE;
ALTER TABLE chatbot ADD COLUMN empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE;
ALTER TABLE notificacion ADD COLUMN empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE;

UPDATE producto SET empresa_id = fn_empresa_por_defecto();
UPDATE marca SET empresa_id = fn_empresa_por_defecto();
UPDATE temporada SET empresa_id = fn_empresa_por_defecto();
UPDATE chatbot SET empresa_id = fn_empresa_por_defecto();

ALTER TABLE producto ALTER COLUMN empresa_id SET DEFAULT fn_empresa_para_alta(), ALTER COLUMN empresa_id SET NOT NULL;
ALTER TABLE marca ALTER COLUMN empresa_id SET DEFAULT fn_empresa_para_alta(), ALTER COLUMN empresa_id SET NOT NULL;
ALTER TABLE temporada ALTER COLUMN empresa_id SET DEFAULT fn_empresa_para_alta(), ALTER COLUMN empresa_id SET NOT NULL;
ALTER TABLE chatbot ALTER COLUMN empresa_id SET DEFAULT fn_empresa_para_alta(), ALTER COLUMN empresa_id SET NOT NULL;
CREATE INDEX ix_producto_empresa ON producto (empresa_id);
CREATE INDEX ix_marca_empresa ON marca (empresa_id);
CREATE INDEX ix_temporada_empresa ON temporada (empresa_id);
CREATE INDEX ix_notificacion_empresa ON notificacion (empresa_id);

-- Dos tiendas pueden tener una marca con el mismo nombre.
ALTER TABLE marca DROP CONSTRAINT marca_nombre_key;
ALTER TABLE marca ADD CONSTRAINT marca_empresa_nombre_key UNIQUE (empresa_id, nombre);

-- Alta de marca (busca o crea por nombre) dentro de la empresa.
CREATE OR REPLACE FUNCTION sp_crear_marca(p_nombre VARCHAR)
RETURNS INTEGER AS $$
DECLARE
    v_id INTEGER;
BEGIN
    INSERT INTO marca (nombre, empresa_id) VALUES (p_nombre, fn_empresa_para_alta())
    ON CONFLICT (empresa_id, nombre) DO UPDATE SET nombre = EXCLUDED.nombre
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- Una sucursal nueva es de la empresa de quien la crea (antes: la empresa por defecto).
CREATE OR REPLACE FUNCTION public.fn_trg_sucursal_limite_plan()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_estado  VARCHAR;
    v_maximo  INTEGER;
    v_usadas  INTEGER;
BEGIN
    IF NEW.empresa_id IS NULL THEN
        NEW.empresa_id := fn_empresa_para_alta();
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
$function$;

-- El producto ya sabe de que empresa es.
CREATE OR REPLACE FUNCTION fn_empresa_de_producto(p_producto_id INTEGER)
RETURNS INTEGER AS $$
    SELECT empresa_id FROM producto WHERE id = p_producto_id;
$$ LANGUAGE sql STABLE;

-- Notificaciones: la empresa sale de la reserva/venta/pago que las genera.
CREATE OR REPLACE FUNCTION fn_empresa_de_notificacion(p_tipo VARCHAR, p_id INTEGER)
RETURNS INTEGER AS $$
    SELECT CASE p_tipo
        WHEN 'reserva' THEN (SELECT s.empresa_id FROM reserva r JOIN sucursal s ON s.id = r.sucursal_id WHERE r.id = p_id)
        WHEN 'venta' THEN (SELECT s.empresa_id FROM venta v JOIN sucursal s ON s.id = v.sucursal_id WHERE v.id = p_id)
        WHEN 'pago' THEN (SELECT s.empresa_id FROM pago pg JOIN venta v ON v.id = pg.venta_id
                          JOIN sucursal s ON s.id = v.sucursal_id WHERE pg.id = p_id)
        WHEN 'devolucion' THEN (SELECT s.empresa_id FROM devolucion d JOIN venta v ON v.id = d.venta_id
                                JOIN sucursal s ON s.id = v.sucursal_id WHERE d.id = p_id)
    END;
$$ LANGUAGE sql STABLE;

UPDATE notificacion
SET empresa_id = coalesce(fn_empresa_de_notificacion(entidad_tipo, entidad_id), fn_empresa_por_defecto());

CREATE OR REPLACE FUNCTION fn_trg_notificacion_empresa()
RETURNS trigger AS $$
BEGIN
    IF NEW.empresa_id IS NULL THEN
        NEW.empresa_id := coalesce(fn_empresa_de_notificacion(NEW.entidad_tipo, NEW.entidad_id), fn_empresa_para_alta());
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_notificacion_empresa
BEFORE INSERT ON notificacion
FOR EACH ROW EXECUTE FUNCTION fn_trg_notificacion_empresa();

-- Proveedores: son usuarios; quedan en la empresa de quien los registra.
UPDATE usuario SET empresa_id = fn_empresa_por_defecto()
WHERE tipo = 'proveedor' AND empresa_id IS NULL;

-- (al crear el usuario, antes de la fila de proveedor: su politica lo exige)
CREATE OR REPLACE FUNCTION fn_trg_proveedor_empresa()
RETURNS trigger AS $$
BEGIN
    IF NEW.tipo = 'proveedor' AND NEW.empresa_id IS NULL THEN
        NEW.empresa_id := fn_empresa_para_alta();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_proveedor_empresa
BEFORE INSERT ON usuario
FOR EACH ROW EXECUTE FUNCTION fn_trg_proveedor_empresa();

-- "Personal" en Mi suscripcion: sin contar proveedores.
CREATE OR REPLACE FUNCTION fn_mi_suscripcion(p_empresa_id INTEGER)
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

-- Una tienda muestra su catalogo en cuanto tiene productos; la original
-- ademas tiene su sitio completo.
DROP FUNCTION IF EXISTS fn_tienda_publica(VARCHAR);
CREATE FUNCTION fn_tienda_publica(p_subdominio VARCHAR)
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

-- ------------------------------------------------------- rol de las tiendas
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'arlani_tenant') THEN
        CREATE ROLE arlani_tenant NOLOGIN NOBYPASSRLS;
    END IF;
END $$;
GRANT arlani_tenant TO CURRENT_USER;
GRANT USAGE ON SCHEMA public TO arlani_tenant;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO arlani_tenant;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO arlani_tenant;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO arlani_tenant;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO arlani_tenant;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO arlani_tenant;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO arlani_tenant;
"""


def upgrade() -> None:
    op.execute(BASE)
    for tabla, condicion in POLITICAS:
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY pol_{tabla}_empresa ON {tabla} FOR ALL TO arlani_tenant "
            f"USING ({condicion}) WITH CHECK ({condicion})"
        )


def downgrade() -> None:
    for tabla, _ in POLITICAS:
        op.execute(f"DROP POLICY IF EXISTS pol_{tabla}_empresa ON {tabla}")
        op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")
    op.execute(
        r"""
        ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM arlani_tenant;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM arlani_tenant;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM arlani_tenant;
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM arlani_tenant;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM arlani_tenant;
        REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM arlani_tenant;
        REVOKE USAGE ON SCHEMA public FROM arlani_tenant;

        DROP TRIGGER IF EXISTS trg_proveedor_empresa ON usuario;
        DROP FUNCTION IF EXISTS fn_trg_proveedor_empresa();
        DROP TRIGGER IF EXISTS trg_notificacion_empresa ON notificacion;
        DROP FUNCTION IF EXISTS fn_trg_notificacion_empresa();
        DROP FUNCTION IF EXISTS fn_empresa_de_notificacion(VARCHAR, INTEGER);

        CREATE OR REPLACE FUNCTION fn_empresa_de_producto(p_producto_id INTEGER)
        RETURNS INTEGER AS $$ SELECT fn_empresa_por_defecto(); $$ LANGUAGE sql STABLE;
        DROP FUNCTION IF EXISTS fn_tienda_publica(VARCHAR);
        CREATE FUNCTION fn_tienda_publica(p_subdominio VARCHAR)
        RETURNS TABLE (id INTEGER, nombre VARCHAR, subdominio VARCHAR, ciudad VARCHAR, color_marca VARCHAR,
                       logo_url VARCHAR, estado VARCHAR, tiene_catalogo BOOLEAN) AS $$
            SELECT e.id, e.nombre, e.subdominio, e.ciudad, e.color_marca, e.logo_url, e.estado,
                   e.id = fn_empresa_por_defecto()
            FROM empresa e WHERE e.subdominio = lower(trim(p_subdominio));
        $$ LANGUAGE sql STABLE;

        CREATE OR REPLACE FUNCTION sp_crear_marca(p_nombre VARCHAR)
        RETURNS INTEGER AS $$
        DECLARE v_id INTEGER;
        BEGIN
            INSERT INTO marca (nombre) VALUES (p_nombre)
            ON CONFLICT (nombre) DO UPDATE SET nombre = EXCLUDED.nombre
            RETURNING id INTO v_id;
            RETURN v_id;
        END;
        $$ LANGUAGE plpgsql;
        ALTER TABLE marca DROP CONSTRAINT IF EXISTS marca_empresa_nombre_key;
        ALTER TABLE marca ADD CONSTRAINT marca_nombre_key UNIQUE (nombre);
        ALTER TABLE notificacion DROP COLUMN IF EXISTS empresa_id;
        ALTER TABLE chatbot DROP COLUMN IF EXISTS empresa_id;
        ALTER TABLE temporada DROP COLUMN IF EXISTS empresa_id;
        ALTER TABLE marca DROP COLUMN IF EXISTS empresa_id;
        ALTER TABLE producto DROP COLUMN IF EXISTS empresa_id;
        DROP FUNCTION IF EXISTS fn_empresa_para_alta();
        DROP FUNCTION IF EXISTS fn_empresa_actual();
        """
    )
