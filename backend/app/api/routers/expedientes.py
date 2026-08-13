import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    SessionContext,
    assert_linea_permitida,
    get_db,
    requiere_estacion,
    requiere_supervisor,
)
from app.models.enums import EstadoVerificacion, FuenteDatos, StationType
from app.models.event_log import EventLog
from app.models.vehiculo import Vehiculo
from app.models.verificacion import Verificacion
from app.schemas.vehiculo import VehiculoRead, VehiculoUpdate
from app.schemas.verificacion import ExpedienteCompleto, ExpedienteCreate, ExpedienteRead
from app.services import state_machine
from app.services.vehiculo import actualizar_datos_vehiculo

ESTADOS_NORMALIZABLES = {
    EstadoVerificacion.DATOS_SIOX_IMPORTADOS,
    EstadoVerificacion.DATOS_CAPTURADOS_MANUALMENTE,
}

router = APIRouter(prefix="/api/expedientes", tags=["expedientes"])


@router.post("", response_model=ExpedienteRead, status_code=201)
async def crear_expediente(
    payload: ExpedienteCreate,
    session: SessionContext = Depends(requiere_estacion(StationType.CAPTURA)),
    db: AsyncSession = Depends(get_db),
) -> Verificacion:
    """Regla de negocio #1: nada opera sin expediente. Se crea con la placa
    capturada; el vehículo asociado se resuelve/crea después vía SIOX o
    captura manual (ver /api/siox). centro_id/linea_id/operador_id salen de
    la sesión de la estación de Captura, nunca del payload. Solo una
    estación de tipo Captura puede abrir expedientes (HU-019)."""

    if session.center_id is None or session.line_id is None:
        raise HTTPException(
            status_code=400, detail="La sesión no tiene centro o línea asociada."
        )

    vehiculo = Vehiculo(placa=payload.placa, fuente_datos=FuenteDatos.MANUAL)
    db.add(vehiculo)
    await db.flush()

    verificacion = Verificacion(
        vehiculo_id=vehiculo.id,
        placa=payload.placa,
        centro_id=session.center_id,
        linea_id=session.line_id,
        operador_id=session.user_id,
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
            usuario_id=session.user_id,
            modulo="captura",
        )
    )
    await db.commit()
    await db.refresh(verificacion)
    return verificacion


@router.post("/{expediente_id}/normalizar", response_model=ExpedienteRead)
async def normalizar_expediente(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(requiere_estacion(StationType.CAPTURA)),
    db: AsyncSession = Depends(get_db),
) -> Verificacion:
    """Confirmación manual (decisión de negocio 2026-08-07): la normalización
    de los datos importados por SIOX o capturados a mano NO es automática —
    el operador de Captura revisa/corrige y confirma explícitamente antes de
    mandar el expediente a Inspección Visual. Sin este paso, el expediente
    se quedaba varado en DATOS_SIOX_IMPORTADOS/DATOS_CAPTURADOS_MANUALMENTE y
    /api/inspeccion era inalcanzable."""

    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    assert_linea_permitida(session, verificacion.linea_id)

    if verificacion.estado not in ESTADOS_NORMALIZABLES:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede normalizar un expediente en estado {verificacion.estado}",
        )

    # HU-017: combustible es obligatorio para normalizar — sin él, Prueba no
    # puede elegir tipo de prueba (gasolina->dinámica, diésel->opacidad).
    # Aquí también se escribe combustible_validado, que Prueba consume más
    # adelante y que hasta ahora ningún endpoint llenaba.
    vehiculo = await db.get(Vehiculo, verificacion.vehiculo_id)
    if not vehiculo.combustible:
        raise HTTPException(
            status_code=409,
            detail="El combustible del vehículo es obligatorio para normalizar.",
        )
    verificacion.combustible_validado = vehiculo.combustible
    db.add(verificacion)

    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.DATOS_NORMALIZADOS,
        usuario_id=session.user_id,
        modulo="captura",
        evento="datos_normalizados_confirmados",
    )
    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE,
        usuario_id=session.user_id,
        modulo="captura",
        evento="enviado_a_inspeccion_visual",
    )
    await db.commit()
    await db.refresh(verificacion)
    return verificacion


class ReasignarLineaRequest(BaseModel):
    nueva_linea_id: int
    motivo: str = Field(min_length=1)


@router.post("/{expediente_id}/reasignar-linea", response_model=ExpedienteRead)
async def reasignar_linea(
    expediente_id: uuid.UUID,
    payload: ReasignarLineaRequest,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> Verificacion:
    """HU-114: reasignar la línea de un expediente. Solo supervisor
    (requiere_supervisor, no atado a un tipo de estación física), motivo
    obligatorio, y bloqueada si ya hay resultado de prueba o folio
    asignado — en ese punto el expediente ya está demasiado avanzado para
    moverlo de línea sin invalidar trabajo hecho."""

    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    if session.center_id is not None and verificacion.centro_id != session.center_id:
        raise HTTPException(
            status_code=403,
            detail="No puedes reasignar expedientes de otro centro.",
        )
    if verificacion.resultado_final is not None:
        raise HTTPException(
            status_code=409,
            detail="No se puede reasignar: el expediente ya tiene resultado de prueba.",
        )
    if verificacion.folio_externo is not None:
        raise HTTPException(
            status_code=409,
            detail="No se puede reasignar: el expediente ya tiene folio asignado.",
        )
    if payload.nueva_linea_id == verificacion.linea_id:
        raise HTTPException(
            status_code=409, detail="El expediente ya está en esa línea."
        )

    linea_anterior = verificacion.linea_id
    verificacion.linea_id = payload.nueva_linea_id
    db.add(verificacion)
    db.add(
        EventLog(
            verificacion_id=verificacion.id,
            evento="linea_reasignada",
            estado_anterior=verificacion.estado,
            estado_nuevo=verificacion.estado,
            usuario_id=session.user_id,
            modulo="supervision",
            detalle_json={
                "linea_anterior": linea_anterior,
                "linea_nueva": payload.nueva_linea_id,
                "motivo": payload.motivo,
            },
        )
    )
    await db.commit()
    await db.refresh(verificacion)
    return verificacion


@router.patch("/{expediente_id}/vehiculo", response_model=VehiculoRead)
async def actualizar_vehiculo(
    expediente_id: uuid.UUID,
    payload: VehiculoUpdate,
    session: SessionContext = Depends(requiere_estacion(StationType.CAPTURA)),
    db: AsyncSession = Depends(get_db),
) -> Vehiculo:
    """HU-016: corregir/escribir los datos del vehículo (hoy solo se llenan
    desde SIOX). Campos opcionales: solo se tocan los presentes en el
    payload. Si el dato corregido venía de SIOX, fuente_datos pasa a
    CORREGIDO_OPERADOR (ver app.services.vehiculo)."""

    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    assert_linea_permitida(session, verificacion.linea_id)

    vehiculo = await db.get(Vehiculo, verificacion.vehiculo_id)
    await actualizar_datos_vehiculo(
        db,
        vehiculo,
        payload.model_dump(exclude_unset=True),
        verificacion_id=verificacion.id,
        usuario_id=session.user_id,
        modulo="captura",
        evento="datos_vehiculo_corregidos",
    )
    await db.commit()
    await db.refresh(vehiculo)
    return vehiculo


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
