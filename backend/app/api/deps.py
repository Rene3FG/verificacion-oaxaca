import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.enums import StationType
from app.models.workstation import StationSession, UserStationPermission, Workstation

__all__ = [
    "get_db",
    "get_current_session",
    "SessionContext",
    "assert_linea_permitida",
    "requiere_estacion",
    "requiere_supervisor",
    "es_supervisor",
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


def requiere_estacion(*tipos: StationType):
    """Dependencia que restringe un endpoint a uno o más tipos de estación
    (p.ej. Captura, o Captura+Prueba). Reemplaza a `get_current_session` en
    la firma del router: una estación de un tipo no listado recibe 403 en
    vez de poder operar flujos que no le corresponden."""

    async def checker(
        session: SessionContext = Depends(get_current_session),
    ) -> SessionContext:
        if session.station_type not in tipos:
            nombres = ", ".join(tipo.value for tipo in tipos)
            raise HTTPException(
                status_code=403,
                detail=f"Esta operación requiere una estación de tipo {nombres}.",
            )
        return session

    return checker


async def es_supervisor(session: SessionContext, db: AsyncSession) -> bool:
    """Variante que no lanza 403 — para endpoints donde el requisito de
    supervisor depende de una condición que solo se conoce a mitad del
    handler (p.ej. reimpresión.py: el primer clic en Imprimir lo puede
    hacer cualquier operador de Impresión, pero un reintento técnico
    posterior exige Supervisor). `requiere_supervisor` reusa esta misma
    consulta cuando el requisito es incondicional."""

    permiso = await db.execute(
        select(UserStationPermission).where(
            UserStationPermission.user_id == session.user_id,
            UserStationPermission.can_supervise.is_(True),
        )
    )
    return permiso.scalars().first() is not None


async def requiere_supervisor(
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> SessionContext:
    """HU-121: administración de permisos (y HU-114, reasignación de línea)
    no están atadas a un tipo de estación física como Captura/Prueba/
    Impresión — cualquier estación puede tener sesión abierta un usuario
    con rol de supervisor. Se valida contra UserStationPermission.can_supervise
    del usuario de la sesión, sin importar en qué estación física inició."""

    if not await es_supervisor(session, db):
        raise HTTPException(
            status_code=403, detail="Esta operación requiere permiso de supervisor."
        )
    return session


def assert_linea_permitida(session: SessionContext, centro_id: str, linea_id: int) -> None:
    """HU-008: operar un expediente de otra línea responde 403.

    Los números de línea son locales a cada centro (Centro Reforma y otro
    centro pueden tener, cada uno, su propia "línea 1"), igual que
    `Workstation.center_id`/`Verificacion.centro_id` ya lo modelan. Antes
    esta función solo comparaba `linea_id`, así que una sesión del centro A
    podía operar el expediente de la "línea 1" del centro B con el mismo
    número de línea — el 403 de "otra línea" nunca se disparaba porque
    nunca se miraba el centro. `session.center_id` viene de
    `Workstation.center_id` (columna NOT NULL) en cada login real, así que
    en la práctica nunca es None; si lo fuera, se falla cerrado (403) en
    vez de asumir acceso."""

    if session.center_id != centro_id or linea_id not in session.lineas_visibles():
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado. Este expediente pertenece a otra línea.",
        )
