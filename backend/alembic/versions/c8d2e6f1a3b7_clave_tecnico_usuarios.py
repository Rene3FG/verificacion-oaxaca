"""clave_tecnico en cat_usuarios (NOM-047 punto 5, campo 001)

Revision ID: c8d2e6f1a3b7
Revises: b4e7c2a9d1f6
Create Date: 2026-11-04 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8d2e6f1a3b7'
down_revision: Union[str, None] = 'b4e7c2a9d1f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cat_usuarios', sa.Column('clave_tecnico', sa.String(20), nullable=True))
    op.create_unique_constraint('uq_cat_usuarios_clave_tecnico', 'cat_usuarios', ['clave_tecnico'])


def downgrade() -> None:
    op.drop_constraint('uq_cat_usuarios_clave_tecnico', 'cat_usuarios', type_='unique')
    op.drop_column('cat_usuarios', 'clave_tecnico')
