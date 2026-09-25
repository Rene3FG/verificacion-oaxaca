"""valor_minimo en cat_limites_emision (rango de dilución CO+CO2 de NOM-041)

Revision ID: a7c4e02f5b1d
Revises: e2e5135e78d4
Create Date: 2026-09-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c4e02f5b1d'
down_revision: Union[str, None] = 'e2e5135e78d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cat_limites_emision', sa.Column('valor_minimo', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('cat_limites_emision', 'valor_minimo')
