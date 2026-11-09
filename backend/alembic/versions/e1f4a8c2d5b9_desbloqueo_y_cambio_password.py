"""Desbloqueo por supervisor, cambio de contraseña obligatorio y usuarios
sin distinguir mayúsculas (X1 desbloqueo, X6-b, X6-c)

- access_event_resultado gana el valor DESBLOQUEO.
- cat_usuarios.must_change_password (false para los existentes).
- Índice único sobre lower(username): "Admin" y "admin" ya no pueden ser
  cuentas distintas.

Revision ID: e1f4a8c2d5b9
Revises: d9e3f7a2b4c8
Create Date: 2026-11-09 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f4a8c2d5b9'
down_revision: Union[str, None] = 'd9e3f7a2b4c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Un valor nuevo de enum no se puede usar en la misma transacción que lo
    # crea; va en su propio bloque autocommit.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE access_event_resultado ADD VALUE IF NOT EXISTS 'DESBLOQUEO'")

    op.add_column(
        'cat_usuarios',
        sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    conn = op.get_bind()
    duplicados = conn.execute(sa.text(
        "SELECT lower(username) FROM cat_usuarios GROUP BY 1 HAVING count(*) > 1"
    )).scalars().all()
    if duplicados:
        raise RuntimeError(
            "Hay usuarios que solo difieren en mayúsculas; renombra uno de cada par antes de migrar: "
            + ", ".join(duplicados)
        )
    op.create_index(
        'uq_cat_usuarios_username_lower', 'cat_usuarios',
        [sa.text('lower(username)')], unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_cat_usuarios_username_lower', table_name='cat_usuarios')
    op.drop_column('cat_usuarios', 'must_change_password')
    # PostgreSQL no permite quitar un valor de un enum; DESBLOQUEO se queda
    # (inofensivo). Las filas con ese valor se borran para no dejar datos que
    # el modelo anterior no sabría leer.
    op.execute("DELETE FROM access_events WHERE resultado = 'DESBLOQUEO'")
