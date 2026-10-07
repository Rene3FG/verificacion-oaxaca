import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SessionContext,
    assert_linea_permitida,
    get_current_session,
    get_db,
    requiere_supervisor,
)
from app.models.enums import SyncStatus
from app.models.sync_outbox import SyncOutbox
from app.models.verificacion import Verificacion
from app.services.sync import enviar_uno_a_central, procesar_pendientes

router = APIRouter(prefix="/api/sync", tags=["sync"])


async def _enviar_a_central(row: SyncOutbox) -> dict:
    """Indirección monkeypatcheable en pruebas (mismo patrón que
    `folios._consultar_sistema_externo_folios`): no hay integración real
    con un central todavía."""

    return await enviar_uno_a_central(row)


@router.post("/procesar")
async def procesar(
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Etapa 12: no hay Celery corriendo pese a estar en requirements.txt,
    así que el envío de sync_outbox se dispara manualmente (botón de
    supervisor, o un cron/systemd timer local pegándole a este endpoint)
    en vez de un worker en segundo plano. `requiere_supervisor` porque es
    una operación de centro, no de una estación física particular."""

    return await procesar_pendientes(db, enviar=_enviar_a_central)


@router.get("/estado")
async def estado(
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Conteos de `sync_outbox` por `sync_status`, para que cualquier
    estación (no solo Supervisor) muestre en el Top App Bar el estado real
    de sincronización con el central — antes `session.conexion` en el
    frontend era un valor fijo, nunca reflejaba `sync_outbox`. Cualquier
    sesión activa puede consultarlo (`get_current_session`, no
    `requiere_supervisor`): es información de solo lectura que todo
    operador necesita ver, no una operación de centro."""

    filas = (
        await db.execute(
            select(SyncOutbox.sync_status, func.count())
            .group_by(SyncOutbox.sync_status)
        )
    ).all()
    conteos = {status.value: 0 for status in SyncStatus}
    for status, total in filas:
        conteos[status.value] = total

    mas_antiguo = (
        await db.execute(
            select(func.min(SyncOutbox.created_at)).where(
                SyncOutbox.sync_status.in_([SyncStatus.PENDING, SyncStatus.ERROR])
            )
        )
    ).scalar_one_or_none()

    return {
        "pendientes": conteos[SyncStatus.PENDING.value] + conteos[SyncStatus.ERROR.value],
        "sincronizando": conteos[SyncStatus.SYNCING.value],
        "en_error": conteos[SyncStatus.ERROR.value],
        "sincronizados": conteos[SyncStatus.SYNCED.value],
        "pendiente_mas_antiguo": mas_antiguo.isoformat() if mas_antiguo else None,
    }


@router.get("/expediente/{expediente_id}")
async def estado_expediente(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """HU-105/109/110: estado de sincronización de UN expediente — su
    snapshot (`verificacion`) y todos sus eventos de bitácora (`event_log`,
    ligados por `payload.verificacion_id`). `estado` resume: ERROR si alguna
    fila falló, PENDIENTE si hay filas sin enviar, SINCRONIZADO si todas
    llegaron, SIN_REGISTROS si nada se encoló. Misma restricción de línea
    que el resto de endpoints del expediente."""

    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    assert_linea_permitida(session, verificacion.centro_id, verificacion.linea_id)

    filas = (
        await db.execute(
            select(SyncOutbox)
            .where(
                or_(
                    SyncOutbox.entity_uuid == expediente_id,
                    SyncOutbox.payload["verificacion_id"].as_string() == str(expediente_id),
                )
            )
            .order_by(SyncOutbox.created_at)
        )
    ).scalars().all()

    conteos = {status.value: 0 for status in SyncStatus}
    for fila in filas:
        conteos[fila.sync_status.value] += 1

    if not filas:
        estado_global = "SIN_REGISTROS"
    elif conteos[SyncStatus.ERROR.value]:
        estado_global = "ERROR"
    elif conteos[SyncStatus.PENDING.value] or conteos[SyncStatus.SYNCING.value]:
        estado_global = "PENDIENTE"
    else:
        estado_global = "SINCRONIZADO"

    ultima = max((f.last_attempt_at for f in filas if f.last_attempt_at), default=None)
    return {
        "expediente_id": str(expediente_id),
        "estado": estado_global,
        "total": len(filas),
        "pendientes": conteos[SyncStatus.PENDING.value] + conteos[SyncStatus.SYNCING.value],
        "en_error": conteos[SyncStatus.ERROR.value],
        "sincronizados": conteos[SyncStatus.SYNCED.value],
        "ultimo_intento": ultima.isoformat() if ultima else None,
    }
