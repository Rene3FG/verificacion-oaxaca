"""hash_integridad_en_resultado_prueba

Revision ID: e2e5135e78d4
Revises: d51e439f9236
Create Date: 2026-09-14 16:54:49.605014

HU-102 (subtarea 3, Etapa 12): la columna se agrega nullable, se rellena
para las filas existentes (hoy solo la de seed_demo.py) con la misma
función de hash que usa la app en adelante, y luego se fuerza NOT NULL —
si se creara directo como NOT NULL, el ALTER fallaría contra cualquier
resultado ya guardado.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.services.integridad import calcular_hash_resultado_prueba

revision: str = 'e2e5135e78d4'
down_revision: Union[str, None] = 'd51e439f9236'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('resultados_prueba', sa.Column('hash_integridad', sa.String(length=64), nullable=True))

    conn = op.get_bind()
    filas = conn.execute(
        sa.text(
            """
            SELECT id, verificacion_id, tipo_prueba, combustible, resultado,
                   valores_medidos_json, limites_aplicados_json, equipo_id,
                   linea_id, operador_id, started_at, finished_at
            FROM resultados_prueba
            """
        )
    ).mappings().all()

    for fila in filas:
        hash_integridad = calcular_hash_resultado_prueba(
            resultado_id=fila["id"],
            verificacion_id=fila["verificacion_id"],
            tipo_prueba=fila["tipo_prueba"],
            combustible=fila["combustible"],
            resultado=fila["resultado"],
            valores_medidos_json=fila["valores_medidos_json"],
            limites_aplicados_json=fila["limites_aplicados_json"],
            equipo_id=fila["equipo_id"],
            linea_id=fila["linea_id"],
            operador_id=fila["operador_id"],
            started_at=fila["started_at"].isoformat() if fila["started_at"] else None,
            finished_at=fila["finished_at"].isoformat() if fila["finished_at"] else None,
        )
        conn.execute(
            sa.text("UPDATE resultados_prueba SET hash_integridad = :h WHERE id = :id"),
            {"h": hash_integridad, "id": fila["id"]},
        )

    op.alter_column('resultados_prueba', 'hash_integridad', nullable=False)


def downgrade() -> None:
    op.drop_column('resultados_prueba', 'hash_integridad')
