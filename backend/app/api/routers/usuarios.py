from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionContext, get_db, requiere_supervisor
from app.models.usuario import CatUsuario
from app.schemas.usuario import UsuarioRead

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])


@router.get("", response_model=list[UsuarioRead])
async def listar_usuarios(
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> list[CatUsuario]:
    """Solo lectura, para poblar el selector de usuario al dar de alta un
    permiso (HU-121) — cat_usuarios no tiene su propio CRUD todavía, solo
    se siembra por app/seed.py."""

    result = await db.execute(select(CatUsuario).order_by(CatUsuario.username))
    return list(result.scalars().all())
