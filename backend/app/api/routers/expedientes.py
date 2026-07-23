import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.models.enums import EstadoVerificacion, FuenteDatos
from app.models.event_log import EventLog
from app.models.vehiculo import Vehiculo
from app.models.verificacion import Verificacion
from app.schemas.verificacion import ExpedienteCompleto, ExpedienteCreate, ExpedienteRead

router = APIRouter(prefix="/api/expedientes", tags=["expedientes"])


@router.post("", response_model=ExpedienteRead, status_code=201)
async def crear_expediente(
    payload: ExpedienteCreate, db: AsyncSession = Depends(get_db)
) -> Verificacion:
    """Regla de negocio #1: nada opera sin expediente. Se crea con la placa
    capturada; el vehículo asociado se resuelve/crea después vía SIOX o
    captura manual (ver /api/siox)."""

    vehiculo = Vehiculo(placa=payload.placa, fuente_datos=FuenteDatos.MANUAL)
    db.add(vehiculo)
    await db.flush()

    verificacion = Verificacion(
        vehiculo_id=vehiculo.id,
        placa=payload.placa,
        centro_id=payload.centro_id,
        linea_id=payload.linea_id,
        operador_id=payload.operador_id,
        estado=EstadoVerificacion.CREADO,
    )
    db.add(verificacion)
    await db.flush()

    # CREADO es el estado inicial; no pasa por state_machine.transition
    # (que valida transiciones ENTRE estados), solo se registra el evento.
    db.add(
        EventLog(
            verificacion_id=verificacion.id,
            evento="expediente_creado",
            estado_anterior=None,
            estado_nuevo=EstadoVerificacion.CREADO,
            usuario_id=payload.operador_id,
            modulo="captura",
        )
    )
    await db.commit()
    await db.refresh(verificacion)
    return verificacion


@router.get("/{expediente_id}", response_model=ExpedienteCompleto)
async def obtener_expediente(
    expediente_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Verificacion:
    result = await db.execute(
        select(Verificacion)
        .options(selectinload(Verificacion.vehiculo))
        .where(Verificacion.id == expediente_id)
    )
    verificacion = result.scalar_one_or_none()
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    return verificacion


@router.get("", response_model=list[ExpedienteRead])
async def listar_expedientes(
    centro_id: str | None = None,
    linea_id: int | None = None,
    estado: EstadoVerificacion | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Verificacion]:
    query = select(Verificacion)
    if centro_id is not None:
        query = query.where(Verificacion.centro_id == centro_id)
    if linea_id is not None:
        query = query.where(Verificacion.linea_id == linea_id)
    if estado is not None:
        query = query.where(Verificacion.estado == estado)
    result = await db.execute(query.order_by(Verificacion.created_at.desc()))
    return list(result.scalars().all())
