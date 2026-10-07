"""entidad_federativa en vehiculos (HU-016)

Revision ID: b9d4f7a2c6e1
Revises: a7c4e02f5b1d
Create Date: 2026-10-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b9d4f7a2c6e1'
down_revision: Union[str, None] = 'a7c4e02f5b1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('vehiculos', sa.Column('entidad_federativa', sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column('vehiculos', 'entidad_federativa')
