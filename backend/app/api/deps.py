import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.enums import StationType
from app.models.workstation import StationSession, Workstation

__all__ = [
    "get_db",
    "get_current_session",
    "SessionContext",
    "assert_linea_permitida",
    "requiere_estacion",
]


@dataclass
class SessionContext:
    """Identidad resuelta server-side a partir de `X-Session-Id`. Ningún
    router debe volver a pedir `linea_id` ni `usuario_id` al cliente: ambos
    salen de aquí, nunca del payload de la petición."""

    session_id: uuid.UUID
    user_id: uuid.UUID
    workstation_id: uuid.UUID
    station_type: StationType
    center_id: str | None
    line_id: int | None
    is_centralized: bool
    allowed_line_ids: list[int] | None

    def lineas_visibles(self) -> set[int]:
        """Líneas que esta sesión puede ver/operar."""
        if self.is_centralized:
            return set(self.allowed_line_ids) if self.allowed_line_ids else set()
        return {self.line_id} if self.line_id is not None else set()


async def get_current_session(
    x_session_id: Annotated[uuid.UUID, Header(alias="X-Session-Id")],
    db: AsyncSession = Depends(get_db),
) -> SessionContext:
    sesion = await db.get(StationSession, x_session_id)
    if sesion is None or sesion.status != "activa" or sesion.logout_at is not None:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada.")

    estacion = await db.get(Workstation, sesion.workstation_id)
    if estacion is None or not estacion.is_active:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada.")

    return SessionContext(
        session_id=sesion.id,
        user_id=sesion.user_id,
        workstation_id=sesion.workstation_id,
        station_type=sesion.station_type,
        center_id=sesion.center_id,
        line_id=sesion.line_id,
        is_centralized=estacion.is_centralized,
        allowed_line_ids=estacion.allowed_line_ids,
    )


def requiere_estacion(tipo: StationType):
    """Dependencia que restringe un endpoint a un tipo de estación
    (p.ej. Captura). Reemplaza a `get_current_session` en la firma del
    router: una estación de Prueba o Impresión recibe 403 en vez de poder
    operar flujos que no le corresponden."""

    async def checker(
        session: SessionContext = Depends(get_current_session),
    ) -> SessionContext:
        if session.station_type != tipo:
            raise HTTPException(
                status_code=403,
                detail=f"Esta operación requiere una estación de tipo {tipo.value}.",
            )
        return session

    return checker


def assert_linea_permitida(session: SessionContext, linea_id: int) -> None:
    """HU-008: operar un expediente de otra línea responde 403."""
    if linea_id not in session.lineas_visibles():
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado. Este expediente pertenece a otra línea.",
        )
