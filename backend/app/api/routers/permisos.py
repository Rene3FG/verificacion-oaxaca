import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionContext, get_db, requiere_supervisor
from app.models.enums import StationType
from app.models.usuario import CatUsuario
from app.models.workstation import UserStationPermission
from app.schemas.permiso import PermisoCreate, PermisoRead, PermisoUpdate
from app.services.auditoria_admin import registrar_evento_admin
from app.services.sesiones import cerrar_sesiones_de_usuario


def _foto_permiso(p: UserStationPermission) -> dict:
    return {
        "permiso_id": p.id,
        "usuario_afectado_id": p.user_id,
        "station_type": p.station_type,
        "center_id": p.center_id,
        "line_id": p.line_id,
        "can_operate": p.can_operate,
        "can_supervise": p.can_supervise,
    }

router = APIRouter(prefix="/api/permisos", tags=["permisos"])


@router.get("", response_model=list[PermisoRead])
async def listar_permisos(
    user_id: uuid.UUID | None = None,
    center_id: str | None = None,
    station_type: StationType | None = None,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> list[UserStationPermission]:
    query = select(UserStationPermission)
    if user_id is not None:
        query = query.where(UserStationPermission.user_id == user_id)
    if center_id is not None:
        query = query.where(UserStationPermission.center_id == center_id)
    if station_type is not None:
        query = query.where(UserStationPermission.station_type == station_type)

    result = await db.execute(query.order_by(UserStationPermission.created_at))
    return list(result.scalars().all())


@router.post("", response_model=PermisoRead, status_code=201)
async def crear_permiso(
    payload: PermisoCreate,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> UserStationPermission:
    """HU-121: administrar user_station_permissions desde la aplicación en
    vez de por base de datos directa. Evita duplicar la misma combinación
    (user_id, station_type, center_id, line_id)."""

    # La tabla no tiene FK a cat_usuarios: sin esto se aceptaba un user_id
    # inexistente.
    if await db.get(CatUsuario, payload.user_id) is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    existente = await db.execute(
        select(UserStationPermission).where(
            UserStationPermission.user_id == payload.user_id,
            UserStationPermission.station_type == payload.station_type,
            UserStationPermission.center_id == payload.center_id,
            UserStationPermission.line_id == payload.line_id,
        )
    )
    if existente.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="Ya existe un permiso para ese usuario, estación y línea.",
        )

    permiso = UserStationPermission(**payload.model_dump())
    db.add(permiso)
    await db.flush()
    registrar_evento_admin(db, session, "permiso_otorgado", _foto_permiso(permiso))
    await db.commit()
    await db.refresh(permiso)
    return permiso


@router.patch("/{permiso_id}", response_model=PermisoRead)
async def actualizar_permiso(
    permiso_id: uuid.UUID,
    payload: PermisoUpdate,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> UserStationPermission:
    permiso = await db.get(UserStationPermission, permiso_id)
    if permiso is None:
        raise HTTPException(status_code=404, detail="Permiso no encontrado")

    antes = _foto_permiso(permiso)
    for campo, valor in payload.model_dump(exclude_unset=True).items():
        setattr(permiso, campo, valor)
    despues = _foto_permiso(permiso)
    cambios = {k: {"antes": antes[k], "despues": despues[k]} for k in antes if antes[k] != despues[k]}
    if cambios:
        # X2-b: la sesión abierta no debe conservar privilegios que ya no tiene.
        await cerrar_sesiones_de_usuario(db, permiso.user_id, excepto=session.session_id)
        registrar_evento_admin(
            db, session, "permiso_modificado",
            {"permiso_id": permiso.id, "usuario_afectado_id": permiso.user_id, "cambios": cambios},
        )

    db.add(permiso)
    await db.commit()
    await db.refresh(permiso)
    return permiso


@router.delete("/{permiso_id}", status_code=204)
async def eliminar_permiso(
    permiso_id: uuid.UUID,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> None:
    permiso = await db.get(UserStationPermission, permiso_id)
    if permiso is None:
        raise HTTPException(status_code=404, detail="Permiso no encontrado")
    registrar_evento_admin(db, session, "permiso_revocado", _foto_permiso(permiso))
    await cerrar_sesiones_de_usuario(db, permiso.user_id, excepto=session.session_id)
    await db.delete(permiso)
    await db.commit()
