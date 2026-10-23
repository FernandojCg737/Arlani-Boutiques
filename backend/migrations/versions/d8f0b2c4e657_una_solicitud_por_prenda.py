"""Politica: una sola solicitud de cambio o devolucion por prenda

Una prenda comprada (linea de venta) admite UNA sola solicitud: si ya tuvo
un cambio (aunque se haya rechazado) o una devolucion, no admite otro cambio
ni devolucion. Un cambio que el propio cliente cancela antes de que la
tienda lo atienda no cuenta. Evita "pasear" una prenda dentro del plazo.

sp_solicitar_cambio lo valida (prenda_ya_solicitada); las devoluciones lo
validan en el backend.

Revision ID: d8f0b2c4e657
Revises: c6e8a0b2d43f
Create Date: 2026-10-23

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "d8f0b2c4e657"
down_revision = "c6e8a0b2d43f"
branch_labels = None
depends_on = None

ANTES = """    SELECT COALESCE(sum(cantidad), 0) INTO v_usadas FROM cambio_prenda
    WHERE item_linea_id = p_item_linea_id AND estado IN ('solicitado', 'por_pagar', 'verificando', 'completado');
"""

AHORA = """    -- Una sola solicitud por prenda: si ya tuvo un cambio (aunque se haya
    -- rechazado) o una devolucion, no admite otra.
    IF EXISTS (SELECT 1 FROM cambio_prenda WHERE item_linea_id = p_item_linea_id AND estado <> 'cancelado')
       OR EXISTS (SELECT 1 FROM detalle_devolucion WHERE item_linea_id = p_item_linea_id) THEN
        RAISE EXCEPTION 'prenda_ya_solicitada';
    END IF;
    v_usadas := 0;
"""


def _reemplazar(de: str, a: str) -> str:
    # Reescribe sp_solicitar_cambio tal como esta, cambiando solo ese bloque.
    return f"""
DO $$
DECLARE
    v_def   TEXT;
    v_nueva TEXT;
BEGIN
    SELECT pg_get_functiondef('sp_solicitar_cambio'::regproc) INTO v_def;
    v_nueva := replace(v_def, $a${de}$a$, $b${a}$b$);
    IF v_nueva = v_def THEN
        RAISE EXCEPTION 'sp_solicitar_cambio no tiene el bloque esperado';
    END IF;
    EXECUTE v_nueva;
END $$;
"""


def upgrade() -> None:
    op.execute(_reemplazar(ANTES, AHORA))


def downgrade() -> None:
    op.execute(_reemplazar(AHORA, ANTES))
