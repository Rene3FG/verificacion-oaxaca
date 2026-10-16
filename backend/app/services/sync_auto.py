"""HU-107: sincronización automática de pendientes al volver la conexión.

Un bucle asyncio dentro del propio proceso (sin Celery): cada
`sync_auto_intervalo_s` llama a `procesar_pendientes`, que ya respeta el
backoff por fila, así que mientras el central esté caído los reintentos
no se aceleran. Una excepción en una vuelta no mata el bucle."""

import asyncio
import logging

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.sync import procesar_pendientes

log = logging.getLogger(__name__)


def sync_auto_habilitado() -> bool:
    return bool(settings.central_sync_url) and settings.sync_auto_intervalo_s > 0


async def una_vuelta() -> dict:
    async with SessionLocal() as db:
        return await procesar_pendientes(db)


async def bucle_sync_auto() -> None:
    while True:
        try:
            await una_vuelta()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - el bucle debe sobrevivir a cualquier fallo
            log.exception("sync automatico: vuelta fallida")
        await asyncio.sleep(settings.sync_auto_intervalo_s)
