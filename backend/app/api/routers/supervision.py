import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import SessionContext, get_db, requiere_supervisor
from app.models.enums import EstadoVerificacion
from app.models.event_log import EventLog
from app.models.verificacion import Verificacion
from app.schemas.event_log import EventLogRead
from app.schemas.verificacion import ExpedienteCompleto

router = APIRouter(prefix="/api/supervision", tags=["supervision"])

# Un expediente CERRADO_APROBADO/CERRADO_RECHAZADO/CANCELADO ya no es
# "piso" — no aparece en el monitor en vivo, aunque su bitácora siga
# consultable por separado.
ESTADOS_TERMINALES = {
    EstadoVerificacion.CERRADO_APROBADO,
    EstadoVerificacion.CERRADO_RECHAZADO,
    EstadoVerificacion.CANCELADO,
}


@router.get("/monitor", response_model=list[ExpedienteCompleto])
async def monitor_centro(
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> list[Verificacion]:
    """HU-111: todas las líneas del centro de la sesión del supervisor, a
    diferencia de las colas por estación (Captura/Prueba/Impresión), que
    solo ven su propia línea o sus allowed_line_ids."""

    if session.center_id is None:
        raise HTTPException(status_code=400, detail="La sesión no tiene centro asociado.")

    result = await db.execute(
        select(Verificacion)
        .options(selectinload(Verificacion.vehiculo))
        .where(
            Verificacion.centro_id == session.center_id,
            Verificacion.estado.not_in(ESTADOS_TERMINALES),
        )
        .order_by(Verificacion.linea_id, Verificacion.created_at)
    )
    return list(result.scalars().all())


@router.get("/expedientes/{expediente_id}/bitacora", response_model=list[EventLogRead])
async def bitacora_expediente(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> list[EventLog]:
    """HU-117: línea de tiempo completa de un expediente — todos los
    módulos que lo tocaron (captura, siox, visual, obd, prueba, folios,
    impresión, supervisión), no solo el de quien consulta."""

    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    if session.center_id is not None and verificacion.centro_id != session.center_id:
        raise HTTPException(
            status_code=403, detail="No puedes ver expedientes de otro centro."
        )

    result = await db.execute(
        select(EventLog)
        .where(EventLog.verificacion_id == expediente_id)
        .order_by(EventLog.created_at)
    )
    return list(result.scalars().all())
