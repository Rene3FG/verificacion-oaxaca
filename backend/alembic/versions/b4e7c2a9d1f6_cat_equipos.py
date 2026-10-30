"""Catálogo de equipos por estación de Prueba (F4, 2026-10-30)

Revision ID: b4e7c2a9d1f6
Revises: e5b1c8d4a9f3
Create Date: 2026-10-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b4e7c2a9d1f6'
down_revision: Union[str, None] = 'e5b1c8d4a9f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cat_equipos',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'workstation_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('workstations.id'),
            nullable=False,
        ),
        sa.Column('tipo', sa.String(30), nullable=False),
        sa.Column('marca', sa.String(80), nullable=True),
        sa.Column('modelo', sa.String(80), nullable=True),
        sa.Column('numero_serie', sa.String(80), nullable=False, unique=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_cat_equipos_workstation_id', 'cat_equipos', ['workstation_id'])


def downgrade() -> None:
    op.drop_index('ix_cat_equipos_workstation_id', table_name='cat_equipos')
    op.drop_table('cat_equipos')
