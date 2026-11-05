"""event_log admite eventos administrativos sin expediente (X7-c)

verificacion_id pasa a nullable, se agrega centro_id (backfill desde el
expediente) y un CHECK que solo permite verificacion_id NULL cuando
modulo = 'administracion'.

Revision ID: d9e3f7a2b4c8
Revises: c8d2e6f1a3b7
Create Date: 2026-11-04 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd9e3f7a2b4c8'
down_revision: Union[str, None] = 'c8d2e6f1a3b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('event_log', sa.Column('centro_id', sa.String(60), nullable=True))
    op.execute(
        "UPDATE event_log e SET centro_id = v.centro_id "
        "FROM verificaciones v WHERE v.id = e.verificacion_id"
    )
    op.alter_column('event_log', 'verificacion_id', nullable=True)
    op.create_check_constraint(
        'ck_event_log_expediente_o_admin',
        'event_log',
        "verificacion_id IS NOT NULL OR modulo = 'administracion'",
    )
    op.create_index('ix_event_log_centro_created', 'event_log', ['centro_id', 'created_at'])


def downgrade() -> None:
    # Los eventos administrativos no tienen expediente: no caben en el
    # esquema anterior y se descartan al bajar de versión.
    op.execute("DELETE FROM event_log WHERE verificacion_id IS NULL")
    op.drop_index('ix_event_log_centro_created', table_name='event_log')
    op.drop_constraint('ck_event_log_expediente_o_admin', 'event_log', type_='check')
    op.alter_column('event_log', 'verificacion_id', nullable=False)
    op.drop_column('event_log', 'centro_id')
