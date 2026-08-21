import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import SessionContext, assert_linea_permitida, get_db, requiere_estacion
from app.models.enums import EstadoVerificacion, ResultadoPruebaEnum, StationType
from app.models.resultado_obd_sbd import ResultadoObdSbd
from app.models.verificacion import Verificacion
from app.services import state_machine
from app.services.parametros import obd_aplica

router = APIRouter(prefix="/api/obd", tags=["obd"])


@router.post("/evaluar/{expediente_id}")
async def evaluar_obd(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(requiere_estacion(StationType.PRUEBA)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Regla de negocio #4: determina si OBD/SBD aplica, según parámetro
    configurable obd_modelo_minimo (nunca hardcodeado)."""

    result = await db.execute(
        select(Verificacion)
        .options(selectinload(Verificacion.vehiculo))
        .where(Verificacion.id == expediente_id)
    )
    verificacion = result.scalar_one_or_none()
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    assert_linea_permitida(session, verificacion.centro_id, verificacion.linea_id)

    vehiculo = verificacion.vehiculo
    if vehiculo.tipo_vehiculo is None or vehiculo.combustible is None or vehiculo.modelo is None:
        raise HTTPException(
            status_code=422,
            detail="El vehículo no tiene tipo_vehiculo, combustible o modelo — normalice el expediente antes de evaluar OBD.",
        )

    aplica = await obd_aplica(
        db,
        inspeccion_aprobada=verificacion.estado
        == EstadoVerificacion.INSPECCION_VISUAL_APROBADA,
        tipo_vehiculo=vehiculo.tipo_vehiculo,
        combustible=vehiculo.combustible,
        modelo=vehiculo.modelo,
    )

    verificacion.combustible_validado = vehiculo.combustible

    db.add(
        ResultadoObdSbd(verificacion_id=verificacion.id, aplica=aplica)
    )

    nuevo_estado = (
        EstadoVerificacion.OBD_PENDIENTE if aplica else EstadoVerificacion.OBD_NO_APLICA
    )
    await state_machine.transition(
        db,
        verificacion,
        nuevo_estado,
        usuario_id=session.user_id,
        modulo="obd",
        evento="obd_evaluado",
        detalle={"aplica": aplica},
    )

    if not aplica:
        # Regla #6: si no aplica se registra el evento y continúa; no es error.
        await state_machine.transition(
            db,
            verificacion,
            EstadoVerificacion.LISTO_PARA_PRUEBA,
            usuario_id=session.user_id,
            modulo="obd",
            evento="obd_no_aplica_continua",
        )

    await db.commit()
    return {"aplica": aplica, "estado_expediente": verificacion.estado}


class ObdResultadoInput(BaseModel):
    resultado: ResultadoPruebaEnum
    codigos_error: dict | None = None
    datos_raw: dict | None = None
    equipo_id: uuid.UUID | None = None


@router.post("/solicitar/{expediente_id}")
async def solicitar_obd(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(requiere_estacion(StationType.PRUEBA)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    assert_linea_permitida(session, verificacion.centro_id, verificacion.linea_id)

    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.OBD_SOLICITADO,
        usuario_id=session.user_id,
        modulo="obd",
        evento="obd_solicitado",
    )
    await db.commit()
    return {"estado_expediente": verificacion.estado}


@router.post("/resultado/{expediente_id}")
async def guardar_resultado_obd(
    expediente_id: uuid.UUID,
    payload: ObdResultadoInput,
    session: SessionContext = Depends(requiere_estacion(StationType.PRUEBA)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    assert_linea_permitida(session, verificacion.centro_id, verificacion.linea_id)

    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.OBD_RECIBIDO,
        usuario_id=session.user_id,
        modulo="obd",
        evento="obd_resultado_guardado",
        detalle={"resultado": payload.resultado},
    )
    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.LISTO_PARA_PRUEBA,
        usuario_id=session.user_id,
        modulo="obd",
        evento="enviado_a_prueba",
    )
    await db.commit()
    return {"estado_expediente": verificacion.estado}
