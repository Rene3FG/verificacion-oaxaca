import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionContext, get_db, requiere_supervisor
from app.models.usuario import CatUsuario
from app.models.workstation import StationSession
from app.schemas.usuario import UsuarioCreate, UsuarioRead, UsuarioUpdate
from app.services.auth import hash_password

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])


@router.get("", response_model=list[UsuarioRead])
async def listar_usuarios(
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> list[CatUsuario]:
    """Incluye inactivos: Supervisor necesita verlos para reactivarlos."""

    result = await db.execute(select(CatUsuario).order_by(CatUsuario.username))
    return list(result.scalars().all())


@router.post("", response_model=UsuarioRead, status_code=201)
async def crear_usuario(
    payload: UsuarioCreate,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> CatUsuario:
    """Alta de usuario desde la app (antes solo por app/seed.py). Los
    permisos por estación se dan aparte, en /api/permisos (HU-121)."""

    existente = await db.execute(
        select(CatUsuario).where(CatUsuario.username == payload.username)
    )
    if existente.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese nombre de usuario.")

    usuario = CatUsuario(
        username=payload.username,
        password_hash=hash_password(payload.password),
        nombre_completo=payload.nombre_completo,
        is_active=True,
    )
    db.add(usuario)
    await db.commit()
    await db.refresh(usuario)
    return usuario


@router.patch("/{usuario_id}", response_model=UsuarioRead)
async def actualizar_usuario(
    usuario_id: uuid.UUID,
    payload: UsuarioUpdate,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> CatUsuario:
    """Editar nombre, restablecer contraseña o activar/desactivar. No hay
    DELETE a propósito: el usuario queda referenciado por sesiones y
    bitácora, se desactiva en su lugar."""

    usuario = await db.get(CatUsuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    cambios = payload.model_dump(exclude_unset=True)
    if cambios.get("is_active") is False and usuario.id == session.user_id:
        raise HTTPException(status_code=409, detail="No puedes desactivar tu propio usuario.")

    password = cambios.pop("password", None)
    if password is not None:
        usuario.password_hash = hash_password(password)
    for campo, valor in cambios.items():
        if valor is not None:
            setattr(usuario, campo, valor)

    if cambios.get("is_active") is False:
        # Desactivar cierra sus sesiones abiertas (además de que
        # get_current_session ya rechaza a usuarios inactivos).
        await db.execute(
            update(StationSession)
            .where(StationSession.user_id == usuario.id, StationSession.status == "activa")
            .values(status="cerrada", logout_at=datetime.datetime.now(datetime.timezone.utc))
        )

    await db.commit()
    await db.refresh(usuario)
    return usuario
