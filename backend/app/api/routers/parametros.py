from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionContext, get_db, requiere_supervisor
from app.models.catalogos import CatParametroSistema
from app.schemas.parametro import ParametroRead, ParametroUpdate
from app.services.parametros import DEFAULTS, DESCRIPCIONES, validar_valor

router = APIRouter(prefix="/api/parametros", tags=["parametros"])


@router.get("", response_model=list[ParametroRead])
async def listar_parametros(
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> list[ParametroRead]:
    """Solo expone las claves conocidas del sistema (`DEFAULTS`) — no admite
    dar de alta claves nuevas desde el panel, eso requiere decisión de
    producto (ver CLAUDE.md). Las que aún no tienen fila propia se muestran
    con su valor por defecto y `origen="default"`."""

    filas = (await db.execute(select(CatParametroSistema))).scalars().all()
    por_clave = {fila.clave: fila for fila in filas}

    resultado = []
    for clave, valor_default in DEFAULTS.items():
        fila = por_clave.get(clave)
        resultado.append(
            ParametroRead(
                clave=clave,
                valor=fila.valor if fila is not None else valor_default,
                descripcion=DESCRIPCIONES.get(clave, ""),
                origen="catalogo" if fila is not None else "default",
            )
        )
    return resultado


@router.patch("/{clave}", response_model=ParametroRead)
async def actualizar_parametro(
    clave: str,
    payload: ParametroUpdate,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> ParametroRead:
    if clave not in DEFAULTS:
        raise HTTPException(
            status_code=404,
            detail=f"'{clave}' no es un parámetro de sistema conocido.",
        )

    error = validar_valor(clave, payload.valor)
    if error is not None:
        raise HTTPException(status_code=422, detail=error)

    result = await db.execute(
        select(CatParametroSistema).where(CatParametroSistema.clave == clave)
    )
    fila = result.scalar_one_or_none()
    if fila is not None:
        fila.valor = payload.valor
    else:
        fila = CatParametroSistema(
            clave=clave, valor=payload.valor, descripcion=DESCRIPCIONES.get(clave)
        )
        db.add(fila)

    await db.commit()

    return ParametroRead(
        clave=clave,
        valor=payload.valor,
        descripcion=DESCRIPCIONES.get(clave, ""),
        origen="catalogo",
    )
