from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionContext, get_db, requiere_supervisor
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
