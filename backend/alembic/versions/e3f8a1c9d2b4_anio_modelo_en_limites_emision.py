"""anio_modelo_desde/hasta en cat_limites_emision (estratificación por año de NOM-041)

Revision ID: e3f8a1c9d2b4
Revises: 90406768e121
Create Date: 2026-09-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3f8a1c9d2b4'
down_revision: Union[str, None] = '90406768e121'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cat_limites_emision', sa.Column('anio_modelo_desde', sa.Integer(), nullable=True))
    op.add_column('cat_limites_emision', sa.Column('anio_modelo_hasta', sa.Integer(), nullable=True))
    op.drop_constraint('uq_limite_emision_metodo_fase_parametro', 'cat_limites_emision', type_='unique')
    op.create_unique_constraint(
        'uq_limite_emision_metodo_fase_parametro_anio',
        'cat_limites_emision',
        ['metodo', 'fase', 'parametro', 'anio_modelo_desde', 'anio_modelo_hasta'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_limite_emision_metodo_fase_parametro_anio', 'cat_limites_emision', type_='unique'
    )
    op.create_unique_constraint(
        'uq_limite_emision_metodo_fase_parametro',
        'cat_limites_emision',
        ['metodo', 'fase', 'parametro'],
    )
    op.drop_column('cat_limites_emision', 'anio_modelo_hasta')
    op.drop_column('cat_limites_emision', 'anio_modelo_desde')
