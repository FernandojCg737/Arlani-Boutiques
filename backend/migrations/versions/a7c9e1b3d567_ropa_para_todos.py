"""Ropa para todos: mujer, hombre, unisex, ninos y bebes

- producto.publico: para quien es la prenda (mujer, hombre, unisex, nina,
  nino, bebe). Las prendas de Atelier Aranier (tienda de hombre) quedan como
  hombre; el resto, unisex.
- categoria.empresa_id: NULL = categoria base (todas las tiendas); con
  empresa = categoria propia de esa tienda. Se suman categorias base de ropa
  de mujer, ninos y bebes.
- talla.tipo: letra, numero, calzado, nino, bebe (cada prenda usa el suyo).
- empresa.publicos: para quien vende la boutique (lo elige al registrarse).

Revision ID: a7c9e1b3d567
Revises: f4b6d8e0a123
Create Date: 2026-10-24

"""
from alembic import op

revision = "a7c9e1b3d567"
down_revision = "f4b6d8e0a123"
branch_labels = None
depends_on = None


UPGRADE = r"""
ALTER TABLE producto ADD COLUMN publico VARCHAR(10) NOT NULL DEFAULT 'unisex'
    CHECK (publico IN ('mujer', 'hombre', 'unisex', 'nina', 'nino', 'bebe'));
UPDATE producto SET publico = 'hombre'
WHERE empresa_id IN (SELECT id FROM empresa WHERE subdominio = 'atelier-aranier');

ALTER TABLE categoria ADD COLUMN empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE;
ALTER TABLE categoria DROP CONSTRAINT IF EXISTS categoria_nombre_key;
CREATE UNIQUE INDEX ux_categoria_nombre ON categoria (lower(nombre), coalesce(empresa_id, 0));
INSERT INTO categoria (nombre)
SELECT n FROM unnest(ARRAY['Vestidos', 'Faldas', 'Blusas', 'Tops', 'Leggings', 'Shorts', 'Jeans', 'Abrigos',
                           'Pijamas', 'Ropa interior', 'Trajes de baño', 'Conjuntos', 'Enterizos', 'Ropa de bebé',
                           'Uniformes escolares', 'Deportiva']) AS n
WHERE NOT EXISTS (SELECT 1 FROM categoria c WHERE lower(c.nombre) = lower(n) AND c.empresa_id IS NULL);
-- Cada tienda ve las categorias base y las suyas.
ALTER TABLE categoria ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_categoria_empresa ON categoria
    USING (empresa_id IS NULL OR empresa_id = fn_empresa_actual())
    WITH CHECK (empresa_id = fn_empresa_actual());

ALTER TABLE talla ADD COLUMN tipo VARCHAR(10) NOT NULL DEFAULT 'letra'
    CHECK (tipo IN ('letra', 'numero', 'calzado', 'nino', 'bebe'));
ALTER TABLE talla DROP CONSTRAINT IF EXISTS talla_codigo_key;
CREATE UNIQUE INDEX ux_talla_tipo_codigo ON talla (tipo, codigo);
INSERT INTO talla (codigo, tipo)
SELECT t.codigo, t.tipo FROM (VALUES
    ('XXXL', 'letra'), ('Única', 'letra'),
    ('26', 'numero'), ('28', 'numero'), ('30', 'numero'), ('32', 'numero'), ('34', 'numero'), ('36', 'numero'),
    ('38', 'numero'), ('40', 'numero'), ('42', 'numero'), ('44', 'numero'), ('46', 'numero'),
    ('33', 'calzado'), ('34', 'calzado'), ('35', 'calzado'), ('36', 'calzado'), ('37', 'calzado'), ('38', 'calzado'),
    ('39', 'calzado'), ('40', 'calzado'), ('41', 'calzado'), ('42', 'calzado'), ('43', 'calzado'), ('44', 'calzado'),
    ('45', 'calzado'),
    ('2', 'nino'), ('4', 'nino'), ('6', 'nino'), ('8', 'nino'), ('10', 'nino'), ('12', 'nino'), ('14', 'nino'),
    ('16', 'nino'),
    ('0-3 m', 'bebe'), ('3-6 m', 'bebe'), ('6-9 m', 'bebe'), ('9-12 m', 'bebe'), ('12-18 m', 'bebe'),
    ('18-24 m', 'bebe')
) AS t(codigo, tipo)
WHERE NOT EXISTS (SELECT 1 FROM talla x WHERE x.tipo = t.tipo AND x.codigo = t.codigo);

ALTER TABLE empresa ADD COLUMN publicos VARCHAR(10)[] NOT NULL DEFAULT '{}';
UPDATE empresa SET publicos = '{hombre}' WHERE subdominio = 'atelier-aranier';
"""

DOWNGRADE = r"""
ALTER TABLE empresa DROP COLUMN IF EXISTS publicos;
DELETE FROM talla t WHERE (t.tipo <> 'letra' OR t.codigo IN ('XXXL', 'Única'))
    AND NOT EXISTS (SELECT 1 FROM inventario i WHERE i.talla_id = t.id);
DROP INDEX IF EXISTS ux_talla_tipo_codigo;
ALTER TABLE talla DROP COLUMN IF EXISTS tipo;
ALTER TABLE talla ADD CONSTRAINT talla_codigo_key UNIQUE (codigo);
DROP POLICY IF EXISTS pol_categoria_empresa ON categoria;
ALTER TABLE categoria DISABLE ROW LEVEL SECURITY;
DELETE FROM categoria c WHERE c.empresa_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM producto p WHERE p.categoria_id = c.id);
DROP INDEX IF EXISTS ux_categoria_nombre;
ALTER TABLE categoria DROP COLUMN IF EXISTS empresa_id;
ALTER TABLE categoria ADD CONSTRAINT categoria_nombre_key UNIQUE (nombre);
ALTER TABLE producto DROP COLUMN IF EXISTS publico;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
