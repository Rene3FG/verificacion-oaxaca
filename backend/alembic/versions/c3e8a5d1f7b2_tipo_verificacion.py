"""tipo_verificacion en verificaciones (N2)

Revision ID: c3e8a5d1f7b2
Revises: b9d4f7a2c6e1
Create Date: 2026-10-06 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3e8a5d1f7b2'
down_revision: Union[str, None] = 'b9d4f7a2c6e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('verificaciones', sa.Column('tipo_verificacion', sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column('verificaciones', 'tipo_verificacion')
