"""F4: catálogo de equipos físicos por estación de Prueba (Administración /
Parámetros y catálogos / Equipos). Exclusivo de Supervisor, mismo criterio
que el resto de catálogos. Sin DELETE: los resultados lo referencian."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionContext, get_db, requiere_supervisor
from app.models.enums import StationType
from app.models.equipo import Equipo
from app.models.workstation import Workstation
from app.services.equipos import TIPOS_EQUIPO

router = APIRouter(prefix="/api/equipos", tags=["equipos"])


def _validar_tipo(valor: str | None) -> str | None:
    if valor is not None and valor not in TIPOS_EQUIPO:
        raise ValueError(f"tipo debe ser uno de: {', '.join(TIPOS_EQUIPO)}")
    return valor


def _validar_serie(valor: str | None) -> str | None:
    if valor is not None:
        valor = valor.strip()
        if not valor:
            raise ValueError("numero_serie no puede estar vacío")
    return valor


class EquipoCreate(BaseModel):
    workstation_id: uuid.UUID
    tipo: str
    marca: str | None = None
    modelo: str | None = None
    numero_serie: str

    _tipo = field_validator("tipo")(_validar_tipo)
    _serie = field_validator("numero_serie")(_validar_serie)


class EquipoUpdate(BaseModel):
    tipo: str | None = None
    marca: str | None = None
    modelo: str | None = None
    numero_serie: str | None = None
    is_active: bool | None = None

    _tipo = field_validator("tipo")(_validar_tipo)
    _serie = field_validator("numero_serie")(_validar_serie)


class EquipoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workstation_id: uuid.UUID
    tipo: str
    marca: str | None
    modelo: str | None
    numero_serie: str
    is_active: bool


async def _estacion_de_prueba_del_centro(
    db: AsyncSession, session: SessionContext, workstation_id: uuid.UUID
) -> Workstation:
    estacion = await db.get(Workstation, workstation_id)
    if estacion is None or estacion.center_id != session.center_id:
        raise HTTPException(status_code=404, detail="Estación no encontrada")
    if estacion.station_type != StationType.PRUEBA:
        raise HTTPException(
            status_code=422, detail="Los equipos solo se registran en estaciones de tipo PRUEBA."
        )
    return estacion


async def _validar_serie_unica(
    db: AsyncSession, numero_serie: str | None, excluir: uuid.UUID | None
) -> None:
    if numero_serie is None:
        return
    query = select(Equipo.id).where(Equipo.numero_serie == numero_serie)
    if excluir is not None:
        query = query.where(Equipo.id != excluir)
    if (await db.execute(query)).first() is not None:
        raise HTTPException(status_code=409, detail="Ya existe un equipo con ese número de serie.")


@router.get("/tipos")
async def listar_tipos(session: SessionContext = Depends(requiere_supervisor)) -> list[str]:
    return list(TIPOS_EQUIPO)


@router.get("", response_model=list[EquipoRead])
async def listar_equipos(
    workstation_id: uuid.UUID | None = None,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> list[Equipo]:
    """Equipos (activos e inactivos) de las estaciones del centro de la sesión."""

    query = (
        select(Equipo)
        .join(Workstation, Workstation.id == Equipo.workstation_id)
        .where(Workstation.center_id == session.center_id)
    )
    if workstation_id is not None:
        query = query.where(Equipo.workstation_id == workstation_id)
    result = await db.execute(query.order_by(Workstation.line_id, Equipo.tipo))
    return list(result.scalars().all())


@router.post("", response_model=EquipoRead, status_code=201)
async def crear_equipo(
    payload: EquipoCreate,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> Equipo:
    await _estacion_de_prueba_del_centro(db, session, payload.workstation_id)
    await _validar_serie_unica(db, payload.numero_serie, excluir=None)
    equipo = Equipo(**payload.model_dump(), is_active=True)
    db.add(equipo)
    await db.commit()
    await db.refresh(equipo)
    return equipo


@router.patch("/{equipo_id}", response_model=EquipoRead)
async def actualizar_equipo(
    equipo_id: uuid.UUID,
    payload: EquipoUpdate,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> Equipo:
    equipo = await db.get(Equipo, equipo_id)
    if equipo is None:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    await _estacion_de_prueba_del_centro(db, session, equipo.workstation_id)

    cambios = payload.model_dump(exclude_unset=True)
    await _validar_serie_unica(db, cambios.get("numero_serie"), excluir=equipo.id)
    for campo, valor in cambios.items():
        if valor is None and campo in ("tipo", "numero_serie", "is_active"):
            continue
        setattr(equipo, campo, valor)
    await db.commit()
    await db.refresh(equipo)
    return equipo
