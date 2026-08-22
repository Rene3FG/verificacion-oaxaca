from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionContext, get_current_session, get_db, requiere_supervisor
from app.models.enums import SyncStatus
from app.models.sync_outbox import SyncOutbox
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
