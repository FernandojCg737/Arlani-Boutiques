"""CU22 Gestionar live commerce (P3 Operacion de Tiendas)

- live: cada transmision en vivo de una tienda (una a la vez por tienda), su
  sala de LiveKit, su grabacion en Backblaze B2 y, si el SuperAdministrador
  la corto, el motivo.
- live_producto: las prendas que se muestran (una puede estar fijada en
  pantalla con "Agregar al carrito").
- live_comentario: comentarios y emojis (la tienda puede ocultarlos).
- live_espectador: quien entro y salio (lo avisa LiveKit por el webhook).
- live_bloqueo: espectadores silenciados o expulsados de un live.
- Permiso 2P-CU22 (el Administrador lo tiene siempre). Solo plan Profesional
  (plan_suscripcion.live_commerce, migracion c5e7a9b1d346).

Revision ID: d6f8b0c2e457
Revises: c5e7a9b1d346
Create Date: 2026-11-06
"""
from alembic import op

revision = "d6f8b0c2e457"
down_revision = "c5e7a9b1d346"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE live (
    id               SERIAL PRIMARY KEY,
    empresa_id       INTEGER NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    titulo           VARCHAR(120) NOT NULL,
    descripcion      VARCHAR(500),
    sala             VARCHAR(80) NOT NULL UNIQUE,
    estado           VARCHAR(12) NOT NULL DEFAULT 'en_vivo' CHECK (estado IN ('en_vivo', 'finalizado', 'cortado')),
    iniciado_por_id  INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    inicio           TIMESTAMP NOT NULL DEFAULT now(),
    fin              TIMESTAMP,
    espectadores_max INTEGER NOT NULL DEFAULT 0,
    egress_id        VARCHAR(80),
    grabacion_estado VARCHAR(12) NOT NULL DEFAULT 'pendiente'
                     CHECK (grabacion_estado IN ('pendiente', 'grabando', 'procesando', 'lista', 'fallida', 'borrada')),
    grabacion_clave  VARCHAR(300),
    grabacion_bytes  BIGINT,
    grabacion_segundos INTEGER,
    grabacion_error  VARCHAR(300),
    cortado_por_id   INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    motivo_corte     VARCHAR(500)
);
-- Una tienda emite un live a la vez (muchas tiendas pueden estar en vivo).
CREATE UNIQUE INDEX ux_live_en_vivo ON live (empresa_id) WHERE estado = 'en_vivo';
CREATE INDEX ix_live_empresa ON live (empresa_id, inicio DESC);

CREATE TABLE live_producto (
    live_id     INTEGER NOT NULL REFERENCES live(id) ON DELETE CASCADE,
    producto_id INTEGER NOT NULL REFERENCES producto(id) ON DELETE CASCADE,
    orden       SMALLINT NOT NULL DEFAULT 0,
    fijado_en   TIMESTAMP,
    PRIMARY KEY (live_id, producto_id)
);

CREATE TABLE live_comentario (
    id          SERIAL PRIMARY KEY,
    live_id     INTEGER NOT NULL REFERENCES live(id) ON DELETE CASCADE,
    usuario_id  INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    texto       VARCHAR(300) NOT NULL,
    fecha       TIMESTAMP NOT NULL DEFAULT now(),
    oculto      BOOLEAN NOT NULL DEFAULT FALSE,
    oculto_por_id INTEGER REFERENCES usuario(id) ON DELETE SET NULL
);
CREATE INDEX ix_live_comentario ON live_comentario (live_id, fecha);

CREATE TABLE live_espectador (
    live_id     INTEGER NOT NULL REFERENCES live(id) ON DELETE CASCADE,
    usuario_id  INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    entro_en    TIMESTAMP NOT NULL DEFAULT now(),
    salio_en    TIMESTAMP,
    veces       SMALLINT NOT NULL DEFAULT 1,
    PRIMARY KEY (live_id, usuario_id)
);

CREATE TABLE live_bloqueo (
    live_id     INTEGER NOT NULL REFERENCES live(id) ON DELETE CASCADE,
    usuario_id  INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    tipo        VARCHAR(10) NOT NULL CHECK (tipo IN ('silenciado', 'expulsado')),
    por_id      INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    fecha       TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (live_id, usuario_id)
);

-- RLS: el personal de una tienda solo ve y maneja sus lives.
ALTER TABLE live ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_live_empresa ON live FOR ALL TO arlani_tenant
    USING (empresa_id = fn_empresa_actual()) WITH CHECK (empresa_id = fn_empresa_actual());
ALTER TABLE live_producto ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_live_producto_empresa ON live_producto FOR ALL TO arlani_tenant
    USING (live_id IN (SELECT id FROM live)) WITH CHECK (live_id IN (SELECT id FROM live));
ALTER TABLE live_comentario ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_live_comentario_empresa ON live_comentario FOR ALL TO arlani_tenant
    USING (live_id IN (SELECT id FROM live)) WITH CHECK (live_id IN (SELECT id FROM live));
ALTER TABLE live_espectador ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_live_espectador_empresa ON live_espectador FOR ALL TO arlani_tenant
    USING (live_id IN (SELECT id FROM live)) WITH CHECK (live_id IN (SELECT id FROM live));
ALTER TABLE live_bloqueo ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_live_bloqueo_empresa ON live_bloqueo FOR ALL TO arlani_tenant
    USING (live_id IN (SELECT id FROM live)) WITH CHECK (live_id IN (SELECT id FROM live));

INSERT INTO permiso (nombre, descripcion) VALUES ('2P-CU22', 'Gestionar live commerce')
ON CONFLICT (nombre) DO NOTHING;
INSERT INTO rol_permiso (rol_id, permiso_id)
SELECT r.id, p.id FROM rol r, permiso p
WHERE r.nombre IN ('SuperAdministrador', 'Administrador') AND p.nombre = '2P-CU22'
ON CONFLICT DO NOTHING;
INSERT INTO empresa_rol_permiso (empresa_id, rol_id, permiso_id)
SELECT e.id, r.id, p.id FROM empresa e, rol r, permiso p
WHERE r.nombre = 'Administrador' AND p.nombre = '2P-CU22'
ON CONFLICT DO NOTHING;
"""

DOWNGRADE = """
DELETE FROM empresa_rol_permiso WHERE permiso_id = (SELECT id FROM permiso WHERE nombre = '2P-CU22');
DELETE FROM rol_permiso WHERE permiso_id = (SELECT id FROM permiso WHERE nombre = '2P-CU22');
DELETE FROM permiso WHERE nombre = '2P-CU22';
DROP TABLE live_bloqueo;
DROP TABLE live_espectador;
DROP TABLE live_comentario;
DROP TABLE live_producto;
DROP TABLE live;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
