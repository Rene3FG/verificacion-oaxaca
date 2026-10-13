"""Datos del certificado pedidos por el cliente (2026-10-09)

Folio de multa y certificado anterior en el expediente; población,
cilindros y clasificación de carrocería en el vehículo; y el folio pasa a
sobreimprimirse por defecto.

Revision ID: d7a2f9c4e3b1
Revises: c3e8a5d1f7b2
Create Date: 2026-10-12 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd7a2f9c4e3b1'
down_revision: Union[str, None] = 'c3e8a5d1f7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('verificaciones', sa.Column('folio_multa', sa.String(length=30), nullable=True))
    op.add_column('verificaciones', sa.Column('certificado_anterior', sa.String(length=30), nullable=True))
    op.add_column('vehiculos', sa.Column('propietario_poblacion', sa.String(length=100), nullable=True))
    op.add_column('vehiculos', sa.Column('numero_cilindros', sa.Integer(), nullable=True))
    op.add_column('vehiculos', sa.Column('clasificacion_carroceria', sa.String(length=20), nullable=True))
    # El cliente confirmó que el folio SÍ se imprime (fila "Folio
    # Certificado" de cada tanto). Solo se cambia si sigue en el valor
    # anterior por defecto; un valor que alguien ya editó se respeta.
    op.execute(
        "UPDATE cat_parametros_sistema SET valor = 'true' "
        "WHERE clave = 'certificado_imprime_folio' AND valor = 'false'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE cat_parametros_sistema SET valor = 'false' "
        "WHERE clave = 'certificado_imprime_folio' AND valor = 'true'"
    )
    op.drop_column('vehiculos', 'clasificacion_carroceria')
    op.drop_column('vehiculos', 'numero_cilindros')
    op.drop_column('vehiculos', 'propietario_poblacion')
    op.drop_column('verificaciones', 'certificado_anterior')
    op.drop_column('verificaciones', 'folio_multa')
