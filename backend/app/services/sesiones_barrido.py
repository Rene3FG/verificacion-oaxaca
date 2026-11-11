"""X2-d: barrido periódico de sesiones vencidas.

La expiración es perezosa (se marca al llegar una petición con ese
identificador), así que sin barrido las filas vencidas seguían como
`activa` y cualquier conteo de sesiones activas sobreestimaba. El barrido
aplica los mismos dos criterios que `deps._resolver_sesion`: inactividad y
vida máxima."""

import asyncio
import datetime
import logging

from sqlalchemy import func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.workstation import StationSession

log = logging.getLogger(__name__)


def barrido_habilitado() -> bool:
    return settings.sesion_barrido_intervalo_s > 0 and (
        settings.sesion_inactividad_min > 0 or settings.sesion_duracion_max_h > 0
    )


async def barrer_sesiones_vencidas(db: AsyncSession) -> int:
    ahora = datetime.datetime.now(datetime.timezone.utc)
    condiciones = []
    if settings.sesion_inactividad_min > 0:
        limite = ahora - datetime.timedelta(minutes=settings.sesion_inactividad_min)
        condiciones.append(
            func.coalesce(StationSession.updated_at, StationSession.login_at, ahora) < limite
        )
    if settings.sesion_duracion_max_h > 0:
        limite = ahora - datetime.timedelta(hours=settings.sesion_duracion_max_h)
        condiciones.append(
            func.coalesce(StationSession.login_at, StationSession.created_at, ahora) < limite
        )
    if not condiciones:
        return 0
    res = await db.execute(
        update(StationSession)
        .where(
            StationSession.status == "activa",
            StationSession.logout_at.is_(None),
            or_(*condiciones),
        )
        .values(status="expirada", logout_at=ahora)
    )
    await db.commit()
    return res.rowcount or 0


async def bucle_barrido_sesiones() -> None:
    while True:
        try:
            async with SessionLocal() as db:
                n = await barrer_sesiones_vencidas(db)
            if n:
                log.info("barrido de sesiones: %d expiradas", n)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - el bucle debe sobrevivir a cualquier fallo
            log.exception("barrido de sesiones: vuelta fallida")
        await asyncio.sleep(settings.sesion_barrido_intervalo_s)
