"""Split CERRADO en CERRADO_APROBADO/CERRADO_RECHAZADO + cola propia
PENDIENTE_DE_IMPRESION_RECHAZO

Revisión Figma 2026-08-24, sección 14 punto 3.

Revision ID: c6386724bf52
Revises: 5519017f44f2
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c6386724bf52'
down_revision: Union[str, None] = '5519017f44f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VALORES_NUEVOS = [
    'CREADO',
    'DATOS_SIOX_CONSULTADOS',
    'DATOS_SIOX_IMPORTADOS',
    'DATOS_CAPTURADOS_MANUALMENTE',
    'DATOS_NORMALIZADOS',
    'INSPECCION_VISUAL_PENDIENTE',
    'INSPECCION_VISUAL_APROBADA',
    'INSPECCION_VISUAL_RECHAZADA',
    'OBD_NO_APLICA',
    'OBD_PENDIENTE',
    'OBD_SOLICITADO',
    'OBD_RECIBIDO',
    'LISTO_PARA_PRUEBA',
    'PRUEBA_CONFIGURADA',
    'PRUEBA_EN_PROCESO',
    'PRUEBA_FINALIZADA',
    'PENDIENTE_IMPRESION',
    'PENDIENTE_DE_IMPRESION_RECHAZO',
    'FOLIO_SOLICITADO',
    'FOLIO_ASIGNADO',
    'IMPRESO',
    'CERRADO_APROBADO',
    'CERRADO_RECHAZADO',
    'ERROR_INTEGRACION',
    'IMPRESION_FALLIDA',
    'FOLIO_ERROR',
    'CANCELADO',
]

VALORES_VIEJOS = [v for v in VALORES_NUEVOS if v not in ('PENDIENTE_DE_IMPRESION_RECHAZO', 'CERRADO_APROBADO', 'CERRADO_RECHAZADO')] + ['CERRADO']


def upgrade() -> None:
    valores_sql = ", ".join(f"'{v}'" for v in VALORES_NUEVOS)
    op.execute(f"CREATE TYPE estado_verificacion_new AS ENUM ({valores_sql})")

    # Fila CERRADO existente: se reparte según certificado_tipo, mismo dato
    # que ya usa app.services.certificado para distinguir rechazo/aprobado.
    op.execute(
        """
        ALTER TABLE verificaciones
        ALTER COLUMN estado TYPE estado_verificacion_new
        USING (
            CASE
                WHEN estado::text = 'CERRADO' AND certificado_tipo = 'RECHAZO'
                    THEN 'CERRADO_RECHAZADO'
                WHEN estado::text = 'CERRADO'
                    THEN 'CERRADO_APROBADO'
                ELSE estado::text
            END
        )::estado_verificacion_new
        """
    )

    # event_log.estado_anterior/estado_nuevo también usan este tipo (ver
    # app/models/event_log.py) — es bitácora, no estado autoritativo, así
    # que CERRADO histórico se mapea a CERRADO_APROBADO sin más criterio.
    for columna in ("estado_anterior", "estado_nuevo"):
        op.execute(
            f"""
            ALTER TABLE event_log
            ALTER COLUMN {columna} TYPE estado_verificacion_new
            USING (
                CASE
                    WHEN {columna}::text = 'CERRADO' THEN 'CERRADO_APROBADO'
                    ELSE {columna}::text
                END
            )::estado_verificacion_new
            """
        )

    op.execute("DROP TYPE estado_verificacion")
    op.execute("ALTER TYPE estado_verificacion_new RENAME TO estado_verificacion")


def downgrade() -> None:
    valores_sql = ", ".join(f"'{v}'" for v in VALORES_VIEJOS)
    op.execute(f"CREATE TYPE estado_verificacion_old AS ENUM ({valores_sql})")

    op.execute(
        """
        ALTER TABLE verificaciones
        ALTER COLUMN estado TYPE estado_verificacion_old
        USING (
            CASE
                WHEN estado::text IN ('CERRADO_APROBADO', 'CERRADO_RECHAZADO') THEN 'CERRADO'
                WHEN estado::text = 'PENDIENTE_DE_IMPRESION_RECHAZO' THEN 'PENDIENTE_IMPRESION'
                ELSE estado::text
            END
        )::estado_verificacion_old
        """
    )

    for columna in ("estado_anterior", "estado_nuevo"):
        op.execute(
            f"""
            ALTER TABLE event_log
            ALTER COLUMN {columna} TYPE estado_verificacion_old
            USING (
                CASE
                    WHEN {columna}::text IN ('CERRADO_APROBADO', 'CERRADO_RECHAZADO') THEN 'CERRADO'
                    WHEN {columna}::text = 'PENDIENTE_DE_IMPRESION_RECHAZO' THEN 'PENDIENTE_IMPRESION'
                    ELSE {columna}::text
                END
            )::estado_verificacion_old
            """
        )

    op.execute("DROP TYPE estado_verificacion")
    op.execute("ALTER TYPE estado_verificacion_old RENAME TO estado_verificacion")
