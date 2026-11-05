"""X2-b / X2-c: cortar las sesiones abiertas de un usuario cuando cambia
lo que puede hacer (permiso modificado o revocado) o cuando se restablece
su contraseña. Antes solo se hacía al desactivarlo."""

import datetime
import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workstation import StationSession


async def cerrar_sesiones_de_usuario(
    db: AsyncSession, user_id: uuid.UUID, *, excepto: uuid.UUID | None = None
) -> int:
    """Marca como cerradas las sesiones activas del usuario. `excepto` deja
    viva la sesión de quien hace el cambio (un supervisor que se edita a sí
    mismo no se expulsa a media operación). No hace commit."""

    q = (
        update(StationSession)
        .where(StationSession.user_id == user_id, StationSession.status == "activa")
        .values(status="cerrada", logout_at=datetime.datetime.now(datetime.timezone.utc))
    )
    if excepto is not None:
        q = q.where(StationSession.id != excepto)
    result = await db.execute(q)
    return result.rowcount or 0
