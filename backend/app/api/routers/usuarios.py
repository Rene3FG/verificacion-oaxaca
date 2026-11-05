import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionContext, get_db, requiere_supervisor
from app.models.usuario import CatUsuario
from app.models.workstation import StationSession
from app.schemas.usuario import UsuarioCreate, UsuarioRead, UsuarioUpdate
from app.services.auth import hash_password, validar_politica_password
from app.services.auditoria_admin import registrar_evento_admin
from app.services.sesiones import cerrar_sesiones_de_usuario

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])


async def _assert_clave_tecnico_libre(
    db: AsyncSession, clave: str | None, *, excepto: uuid.UUID | None = None
) -> None:
    """409 antes del commit en vez de dejar que truene el UNIQUE como 500."""
    if clave is None:
        return
    q = select(CatUsuario.id).where(CatUsuario.clave_tecnico == clave)
    if excepto is not None:
        q = q.where(CatUsuario.id != excepto)
    if (await db.execute(q)).first() is not None:
        raise HTTPException(
            status_code=409, detail="Esa clave de técnico ya está asignada a otro usuario."
        )


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
    await _assert_clave_tecnico_libre(db, payload.clave_tecnico)

    usuario = CatUsuario(
        username=payload.username,
        password_hash=hash_password(payload.password),
        nombre_completo=payload.nombre_completo,
        is_active=True,
        clave_tecnico=payload.clave_tecnico,
    )
    db.add(usuario)
    await db.flush()
    registrar_evento_admin(
        db,
        session,
        "usuario_creado",
        {
            "usuario_afectado_id": usuario.id,
            "username": usuario.username,
            "clave_tecnico": usuario.clave_tecnico,
        },
    )
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

    campos_cambiados = sorted(k for k in cambios if k != "password")
    password = cambios.pop("password", None)
    if password is not None:
        if password.lower() == usuario.username.lower():
            raise HTTPException(
                status_code=422, detail="La contraseña no puede ser igual al usuario."
            )
        try:
            validar_politica_password(password, username=usuario.username)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        usuario.password_hash = hash_password(password)
    if "clave_tecnico" in cambios:
        # A diferencia del resto, null aquí SÍ significa "quitarla".
        clave = cambios.pop("clave_tecnico")
        await _assert_clave_tecnico_libre(db, clave, excepto=usuario.id)
        usuario.clave_tecnico = clave
    for campo, valor in cambios.items():
        if valor is not None:
            setattr(usuario, campo, valor)

    if password is not None:
        # X2-c: tras sospechar de un robo, cambiar la contraseña debe expulsar
        # a quien la estuviera usando.
        await cerrar_sesiones_de_usuario(db, usuario.id, excepto=session.session_id)
        registrar_evento_admin(
            db, session, "usuario_password_restablecida",
            {"usuario_afectado_id": usuario.id, "username": usuario.username},
        )
    if "is_active" in campos_cambiados and payload.is_active is not None:
        registrar_evento_admin(
            db, session,
            "usuario_activado" if payload.is_active else "usuario_desactivado",
            {"usuario_afectado_id": usuario.id, "username": usuario.username},
        )
    otros = [c for c in campos_cambiados if c != "is_active"]
    if otros:
        registrar_evento_admin(
            db, session, "usuario_editado",
            {
                "usuario_afectado_id": usuario.id,
                "username": usuario.username,
                "campos": otros,
                **({"clave_tecnico": usuario.clave_tecnico} if "clave_tecnico" in otros else {}),
            },
        )

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
