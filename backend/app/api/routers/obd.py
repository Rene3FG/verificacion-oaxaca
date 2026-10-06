import datetime
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
from app.services.parametros import get_parametro, obd_aplica

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

    # HU-029: el motivo explica la decisión con las mismas 4 condiciones de
    # `obd_aplica` (regla #4), en el orden en que se evalúan.
    modelo_minimo = int(await get_parametro(db, "obd_modelo_minimo"))
    if verificacion.estado != EstadoVerificacion.INSPECCION_VISUAL_APROBADA:
        motivo = "La inspección visual no está aprobada."
    elif vehiculo.tipo_vehiculo.lower() != "vehiculo":
        motivo = f"El tipo de unidad ({vehiculo.tipo_vehiculo}) no es vehículo."
    elif vehiculo.combustible.lower() != "gasolina":
        motivo = f"El combustible ({vehiculo.combustible}) no es gasolina."
    elif vehiculo.modelo < modelo_minimo:
        motivo = f"Modelo {vehiculo.modelo} anterior al mínimo configurado ({modelo_minimo})."
    else:
        motivo = (
            f"Vehículo a gasolina, modelo {vehiculo.modelo} (≥ {modelo_minimo}), "
            "inspección visual aprobada."
        )

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
        detalle={"aplica": aplica, "motivo": motivo},
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
    return {"aplica": aplica, "motivo": motivo, "estado_expediente": verificacion.estado}


class ObdResultadoInput(BaseModel):
    """HU-033/082: `sin_comunicacion=true` registra el intento fallido
    (resultado ERROR, con el mensaje técnico como evidencia) en lugar de un
    resultado del vehículo."""

    resultado: ResultadoPruebaEnum
    codigos_error: dict | None = None
    datos_raw: dict | None = None
    equipo_id: uuid.UUID | None = None
    sin_comunicacion: bool = False
    mensaje_tecnico: str | None = None


async def _fila_obd(db: AsyncSession, verificacion_id: uuid.UUID) -> ResultadoObdSbd | None:
    return (
        await db.execute(
            select(ResultadoObdSbd)
            .where(ResultadoObdSbd.verificacion_id == verificacion_id)
            .order_by(ResultadoObdSbd.created_at.desc())
        )
    ).scalars().first()


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

    if verificacion.estado != EstadoVerificacion.OBD_PENDIENTE:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No se puede solicitar OBD: el expediente está en estado "
                f"{verificacion.estado}, no OBD_PENDIENTE."
            ),
        )

    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.OBD_SOLICITADO,
        usuario_id=session.user_id,
        modulo="obd",
        evento="obd_solicitado",
    )
    fila = await _fila_obd(db, verificacion.id)
    if fila is not None:
        fila.solicitado_at = datetime.datetime.now(datetime.timezone.utc)
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

    if verificacion.estado != EstadoVerificacion.OBD_SOLICITADO:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No se puede guardar el resultado OBD: el expediente está "
                f"en estado {verificacion.estado}, no OBD_SOLICITADO."
            ),
        )

    # HU-032: el resultado vive en la fila de resultados_obd_sbd creada al
    # evaluar (antes solo quedaba en la bitácora y la fila seguía sin
    # resultado, códigos ni hora de recepción).
    resultado = ResultadoPruebaEnum.ERROR if payload.sin_comunicacion else payload.resultado
    datos_raw = dict(payload.datos_raw or {})
    if payload.sin_comunicacion:
        datos_raw.update(sin_comunicacion=True, mensaje_tecnico=payload.mensaje_tecnico)
    fila = await _fila_obd(db, verificacion.id)
    if fila is None:
        fila = ResultadoObdSbd(verificacion_id=verificacion.id, aplica=True)
        db.add(fila)
    fila.resultado = resultado
    fila.codigos_error = payload.codigos_error
    fila.datos_raw = datos_raw or None
    fila.equipo_id = payload.equipo_id
    fila.operador_id = session.user_id
    fila.recibido_at = datetime.datetime.now(datetime.timezone.utc)

    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.OBD_RECIBIDO,
        usuario_id=session.user_id,
        modulo="obd",
        evento="obd_sin_comunicacion" if payload.sin_comunicacion else "obd_resultado_guardado",
        detalle={
            "resultado": resultado,
            "sin_comunicacion": payload.sin_comunicacion,
            "mensaje_tecnico": payload.mensaje_tecnico,
        },
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
