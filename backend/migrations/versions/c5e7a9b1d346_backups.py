"""CU21 Gestionar backups y restauracion (P1 Seguridad y Acceso)

- backup: cada copia de seguridad (de una tienda o del sistema completo), con
  su archivo ZIP en el bucket privado "backups" y lo que contiene.
- backup_programacion: backups automaticos (una vez, diario, semanal o
  mensual) con cuantas copias guardar.
- backup_restauracion: historial de restauraciones, con el backup que se hizo
  justo antes (para poder volver atras).
- Permiso 2P-CU21 (el Administrador lo tiene siempre; sus empleados, si se lo
  dan en la matriz de CU02).
- Plan: columnas backups (Basico y Profesional) y live_commerce (Profesional,
  para el CU22).

Revision ID: c5e7a9b1d346
Revises: b4d6f8a0c235
Create Date: 2026-11-06
"""
from alembic import op

revision = "c5e7a9b1d346"
down_revision = "b4d6f8a0c235"
branch_labels = None
depends_on = None

UPGRADE = """
ALTER TABLE plan_suscripcion ADD COLUMN backups BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE plan_suscripcion ADD COLUMN live_commerce BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE plan_suscripcion SET backups = codigo IN ('basico', 'profesional'), live_commerce = codigo = 'profesional';

CREATE TABLE backup_programacion (
    id              SERIAL PRIMARY KEY,
    -- NULL = sistema completo (solo el SuperAdministrador).
    empresa_id      INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    nombre          VARCHAR(80) NOT NULL,
    frecuencia      VARCHAR(10) NOT NULL CHECK (frecuencia IN ('una_vez', 'diaria', 'semanal', 'mensual')),
    -- Hora de Bolivia (America/La_Paz).
    hora            TIME NOT NULL,
    fecha           DATE,
    dia_semana      SMALLINT CHECK (dia_semana BETWEEN 0 AND 6),
    dia_mes         SMALLINT CHECK (dia_mes BETWEEN 1 AND 31),
    secciones       VARCHAR(20)[] NOT NULL,
    retener         SMALLINT NOT NULL DEFAULT 10 CHECK (retener BETWEEN 1 AND 60),
    activa          BOOLEAN NOT NULL DEFAULT TRUE,
    -- En UTC, como el resto de fechas del sistema.
    proxima_ejecucion TIMESTAMP,
    ultima_ejecucion  TIMESTAMP,
    creado_por_id   INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    creado_en       TIMESTAMP NOT NULL DEFAULT now(),
    CHECK (frecuencia <> 'una_vez' OR fecha IS NOT NULL),
    CHECK (frecuencia <> 'semanal' OR dia_semana IS NOT NULL),
    CHECK (frecuencia <> 'mensual' OR dia_mes IS NOT NULL)
);
CREATE INDEX ix_backup_programacion_proxima ON backup_programacion (proxima_ejecucion) WHERE activa;

CREATE TABLE backup (
    id              SERIAL PRIMARY KEY,
    empresa_id      INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    alcance         VARCHAR(10) NOT NULL CHECK (alcance IN ('tienda', 'sistema')),
    secciones       VARCHAR(20)[] NOT NULL,
    origen          VARCHAR(20) NOT NULL CHECK (origen IN ('manual', 'programado', 'antes_de_restaurar')),
    programacion_id INTEGER REFERENCES backup_programacion(id) ON DELETE SET NULL,
    estado          VARCHAR(12) NOT NULL DEFAULT 'en_proceso' CHECK (estado IN ('en_proceso', 'completado', 'fallido')),
    -- Rutas en el bucket "backups" (mas de una si el ZIP se guardo en partes).
    archivos        JSONB NOT NULL DEFAULT '[]',
    tamano_bytes    BIGINT,
    conteos         JSONB,
    imagenes        INTEGER,
    -- Programado que corrio tarde (el servidor estaba dormido a esa hora).
    atrasado        BOOLEAN NOT NULL DEFAULT FALSE,
    error           TEXT,
    creado_por_id   INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    creado_en       TIMESTAMP NOT NULL DEFAULT now(),
    completado_en   TIMESTAMP,
    CHECK ((alcance = 'tienda') = (empresa_id IS NOT NULL))
);
CREATE INDEX ix_backup_empresa ON backup (empresa_id, creado_en DESC);

CREATE TABLE backup_restauracion (
    id              SERIAL PRIMARY KEY,
    backup_id       INTEGER REFERENCES backup(id) ON DELETE SET NULL,
    empresa_id      INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    secciones       VARCHAR(20)[] NOT NULL,
    estado          VARCHAR(12) NOT NULL DEFAULT 'en_proceso' CHECK (estado IN ('en_proceso', 'completada', 'fallida')),
    -- Por tabla: cuantas filas volvieron, se actualizaron o no se pudieron.
    resumen         JSONB,
    backup_previo_id INTEGER REFERENCES backup(id) ON DELETE SET NULL,
    error           TEXT,
    hecho_por_id    INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    creado_en       TIMESTAMP NOT NULL DEFAULT now(),
    completado_en   TIMESTAMP
);
CREATE INDEX ix_backup_restauracion_empresa ON backup_restauracion (empresa_id, creado_en DESC);

-- RLS: el personal de una tienda solo ve lo de su empresa.
ALTER TABLE backup ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_backup_empresa ON backup FOR ALL TO arlani_tenant
    USING (empresa_id = fn_empresa_actual()) WITH CHECK (empresa_id = fn_empresa_actual());
ALTER TABLE backup_programacion ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_backup_programacion_empresa ON backup_programacion FOR ALL TO arlani_tenant
    USING (empresa_id = fn_empresa_actual()) WITH CHECK (empresa_id = fn_empresa_actual());
ALTER TABLE backup_restauracion ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_backup_restauracion_empresa ON backup_restauracion FOR ALL TO arlani_tenant
    USING (empresa_id = fn_empresa_actual()) WITH CHECK (empresa_id = fn_empresa_actual());

INSERT INTO permiso (nombre, descripcion) VALUES ('2P-CU21', 'Gestionar backups y restauracion')
ON CONFLICT (nombre) DO NOTHING;
-- El SuperAdministrador tiene todos los permisos; en cada tienda, el Administrador.
INSERT INTO rol_permiso (rol_id, permiso_id)
SELECT r.id, p.id FROM rol r, permiso p
WHERE r.nombre IN ('SuperAdministrador', 'Administrador') AND p.nombre = '2P-CU21'
ON CONFLICT DO NOTHING;
INSERT INTO empresa_rol_permiso (empresa_id, rol_id, permiso_id)
SELECT e.id, r.id, p.id FROM empresa e, rol r, permiso p
WHERE r.nombre = 'Administrador' AND p.nombre = '2P-CU21'
ON CONFLICT DO NOTHING;
"""

DOWNGRADE = """
DELETE FROM empresa_rol_permiso WHERE permiso_id = (SELECT id FROM permiso WHERE nombre = '2P-CU21');
DELETE FROM rol_permiso WHERE permiso_id = (SELECT id FROM permiso WHERE nombre = '2P-CU21');
DELETE FROM permiso WHERE nombre = '2P-CU21';
DROP TABLE backup_restauracion;
DROP TABLE backup;
DROP TABLE backup_programacion;
ALTER TABLE plan_suscripcion DROP COLUMN live_commerce;
ALTER TABLE plan_suscripcion DROP COLUMN backups;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
