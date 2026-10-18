"""endurecer recuperacion de contrasena y prohibir stock negativo

- usuario.reset_code_intentos: cuenta los intentos fallidos del codigo de
  6 digitos; al llegar al limite el codigo se invalida (evita fuerza bruta).
- usuario.reset_token_jti: identificador del reset_token vigente, para que
  cada token de recuperacion sirva una sola vez.
- inventario.cantidad >= 0: red de seguridad a nivel base de datos. Se crea
  NOT VALID para no fallar si hubiera filas viejas fuera de regla; igual se
  aplica a todo INSERT/UPDATE nuevo.

Revision ID: b9e4c2a7f310
Revises: a2f7b3c8d4e1
Create Date: 2026-10-18

"""
from alembic import op
import sqlalchemy as sa

revision = "b9e4c2a7f310"
down_revision = "a2f7b3c8d4e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usuario",
        sa.Column("reset_code_intentos", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("usuario", sa.Column("reset_token_jti", sa.String(64), nullable=True))
    op.execute(
        "ALTER TABLE inventario ADD CONSTRAINT ck_inventario_cantidad_no_negativa "
        "CHECK (cantidad >= 0) NOT VALID"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE inventario DROP CONSTRAINT IF EXISTS ck_inventario_cantidad_no_negativa")
    op.drop_column("usuario", "reset_token_jti")
    op.drop_column("usuario", "reset_code_intentos")
