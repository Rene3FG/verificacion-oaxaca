"""Corrida vigente del gateway de equipo en el expediente (2026-10-19)

Revision ID: e5b1c8d4a9f3
Revises: d7a2f9c4e3b1
Create Date: 2026-10-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e5b1c8d4a9f3'
down_revision: Union[str, None] = 'd7a2f9c4e3b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'verificaciones',
        sa.Column('equipo_test_run_id', postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('verificaciones', 'equipo_test_run_id')
