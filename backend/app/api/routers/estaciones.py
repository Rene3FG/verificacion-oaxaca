import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.access_event import AccessEvent
from app.models.enums import AccessEventResultado
from app.models.usuario import CatUsuario
from app.models.workstation import StationSession, UserStationPermission, Workstation
from app.schemas.estacion import StationSessionRead, WorkstationRead
from app.services.auth import verify_password

router = APIRouter(prefix="/api/estaciones", tags=["estaciones"])


@router.get("/{device_identifier}", response_model=WorkstationRead)
async def detectar_estacion(
    device_identifier: str, db: AsyncSession = Depends(get_db)
) -> Workstation:
    result = await db.execute(
        select(Workstation).where(
            Workstation.device_identifier == device_identifier,
            Workstation.is_active.is_(True),
        )
    )
    estacion = result.scalar_one_or_none()
    if estacion is None:
        raise HTTPException(
            status_code=404, detail="Esta computadora no está configurada como estación."
        )
    return estacion


class LoginRequest(BaseModel):
    """HU-119: sustituye el acceso anterior (un user_id sin contraseña que
    el cliente podía mandar libremente). Ahora la identidad se resuelve
    server-side por username/password contra cat_usuarios."""

    username: str
    password: str
    workstation_id: uuid.UUID
    ip_address: str | None = None
    device_fingerprint: str | None = None


@router.post("/login", response_model=StationSessionRead)
async def iniciar_sesion(
    payload: LoginRequest, db: AsyncSession = Depends(get_db)
) -> StationSession:
    estacion = await db.get(Workstation, payload.workstation_id)
    if estacion is None:
        raise HTTPException(status_code=404, detail="Estación no encontrada")

    usuario = (
        await db.execute(
            select(CatUsuario).where(CatUsuario.username == payload.username)
        )
    ).scalar_one_or_none()

    # Mismo mensaje genérico tanto si el usuario no existe como si la
    # contraseña es incorrecta — no revelar cuál de las dos falló.
    credenciales_validas = (
        usuario is not None
        and usuario.is_active
        and verify_password(payload.password, usuario.password_hash)
    )
    if not credenciales_validas:
        db.add(
            AccessEvent(
                user_id=usuario.id if usuario else None,
                workstation_id=estacion.id,
                station_type=estacion.station_type,
                center_id=estacion.center_id,
                line_id=estacion.line_id,
                resultado=AccessEventResultado.DENEGADO,
                motivo="Credenciales inválidas",
                ip_address=payload.ip_address,
            )
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

    permisos = await db.execute(
        select(UserStationPermission).where(
            UserStationPermission.user_id == usuario.id,
            UserStationPermission.station_type == estacion.station_type,
            UserStationPermission.center_id == estacion.center_id,
            UserStationPermission.can_operate.is_(True),
        )
    )
    # HU-001: line_id NULL en el permiso = "todas las líneas del centro"
    # (supervisor). Un permiso de línea específica solo sirve para esa línea.
    permiso_valido = next(
        (
            p
            for p in permisos.scalars().all()
            if p.line_id is None or p.line_id == estacion.line_id
        ),
        None,
    )

    if permiso_valido is None:
        db.add(
            AccessEvent(
                user_id=usuario.id,
                workstation_id=estacion.id,
                station_type=estacion.station_type,
                center_id=estacion.center_id,
                line_id=estacion.line_id,
                resultado=AccessEventResultado.DENEGADO,
                motivo="Sin permiso para operar esta estación/línea",
                ip_address=payload.ip_address,
            )
        )
        await db.commit()
        raise HTTPException(
            status_code=403, detail="No tienes permiso para operar esta estación."
        )

    sesion = StationSession(
        user_id=usuario.id,
        workstation_id=estacion.id,
        station_type=estacion.station_type,
        center_id=estacion.center_id,
        line_id=estacion.line_id,
        login_at=datetime.datetime.now(datetime.timezone.utc),
        ip_address=payload.ip_address,
        device_fingerprint=payload.device_fingerprint,
        status="activa",
    )
    db.add(sesion)
    await db.flush()

    db.add(
        AccessEvent(
            user_id=usuario.id,
            workstation_id=estacion.id,
            station_type=estacion.station_type,
            center_id=estacion.center_id,
            line_id=estacion.line_id,
            resultado=AccessEventResultado.PERMITIDO,
            session_id=sesion.id,
            ip_address=payload.ip_address,
        )
    )
    await db.commit()
    await db.refresh(sesion)
    return sesion


@router.post("/logout/{session_id}")
async def cerrar_sesion(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    sesion = await db.get(StationSession, session_id)
    if sesion is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    sesion.logout_at = datetime.datetime.now(datetime.timezone.utc)
    sesion.status = "cerrada"
    await db.commit()
    return {"status": "cerrada"}
