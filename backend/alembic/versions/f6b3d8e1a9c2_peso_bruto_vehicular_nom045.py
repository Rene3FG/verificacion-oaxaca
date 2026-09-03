"""peso_bruto_vehicular_kg en vehiculos + peso_bruto_desde_kg/hasta_kg en cat_limites_emision (estratificación por peso de NOM-045)

Revision ID: f6b3d8e1a9c2
Revises: e3f8a1c9d2b4
Create Date: 2026-09-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6b3d8e1a9c2'
down_revision: Union[str, None] = 'e3f8a1c9d2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('vehiculos', sa.Column('peso_bruto_vehicular_kg', sa.Float(), nullable=True))
    op.add_column('cat_limites_emision', sa.Column('peso_bruto_desde_kg', sa.Float(), nullable=True))
    op.add_column('cat_limites_emision', sa.Column('peso_bruto_hasta_kg', sa.Float(), nullable=True))
    op.drop_constraint(
        'uq_limite_emision_metodo_fase_parametro_anio', 'cat_limites_emision', type_='unique'
    )
    op.create_unique_constraint(
        'uq_limite_emision_metodo_fase_parametro_anio_peso',
        'cat_limites_emision',
        [
            'metodo',
            'fase',
            'parametro',
            'anio_modelo_desde',
            'anio_modelo_hasta',
            'peso_bruto_desde_kg',
            'peso_bruto_hasta_kg',
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_limite_emision_metodo_fase_parametro_anio_peso', 'cat_limites_emision', type_='unique'
    )
    op.create_unique_constraint(
        'uq_limite_emision_metodo_fase_parametro_anio',
        'cat_limites_emision',
        ['metodo', 'fase', 'parametro', 'anio_modelo_desde', 'anio_modelo_hasta'],
    )
    op.drop_column('cat_limites_emision', 'peso_bruto_hasta_kg')
    op.drop_column('cat_limites_emision', 'peso_bruto_desde_kg')
    op.drop_column('vehiculos', 'peso_bruto_vehicular_kg')
