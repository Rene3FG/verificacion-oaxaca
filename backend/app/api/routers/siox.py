import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionContext, assert_linea_permitida, get_current_session, get_db
from app.core.config import settings
from app.models.enums import EstadoVerificacion
from app.models.integration_log import (
    IntegrationDirection,
    IntegrationLog,
    IntegrationStatus,
)
from app.models.siox_consulta import EstadoSioxConsulta, SioxConsulta
from app.models.verificacion import Verificacion
from app.services import state_machine
from app.services.siox_client import consultar_placa

router = APIRouter(prefix="/api/siox", tags=["siox"])

STATUS_MAP = {
    "EXITOSA": EstadoSioxConsulta.EXITOSA,
    "SIN_DATOS": EstadoSioxConsulta.SIN_DATOS,
    "ERROR": EstadoSioxConsulta.ERROR,
}


@router.post("/consultar/{expediente_id}")
async def consultar_siox(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    assert_linea_permitida(session, verificacion.linea_id)

    resultado = await consultar_placa(verificacion.placa)

    db.add(
        SioxConsulta(
            verificacion_id=verificacion.id,
            placa=verificacion.placa,
            url_consulta=settings.siox_base_url,
            request_payload={"placa": verificacion.placa},
            response_raw=resultado.raw,
            response_normalized=resultado.normalized,
            status=STATUS_MAP[resultado.status],
            consultado_por=session.user_id,
        )
    )
    db.add(
        IntegrationLog(
            verificacion_id=verificacion.id,
            integration_name="SIOX",
            direction=IntegrationDirection.RESPONSE,
            payload=resultado.raw,
            status=IntegrationStatus.OK
            if resultado.status != "ERROR"
            else IntegrationStatus.ERROR,
            error_message=None if resultado.status != "ERROR" else "SIOX no respondió",
        )
    )

    if verificacion.estado == EstadoVerificacion.CREADO:
        await state_machine.transition(
            db,
            verificacion,
            EstadoVerificacion.DATOS_SIOX_CONSULTADOS,
            usuario_id=session.user_id,
            modulo="captura",
            evento="siox_consultado",
            detalle={"status": resultado.status},
        )

    if resultado.status == "EXITOSA":
        await state_machine.transition(
            db,
            verificacion,
            EstadoVerificacion.DATOS_SIOX_IMPORTADOS,
            usuario_id=session.user_id,
            modulo="captura",
            evento="datos_siox_importados",
        )
    # Si status es SIN_DATOS o ERROR, el operador debe usar
    # /api/siox/captura-manual/{expediente_id} (regla: nunca bloquear).

    await db.commit()
    return {"status": resultado.status, "estado_expediente": verificacion.estado}


@router.post("/captura-manual/{expediente_id}")
async def captura_manual(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Si SIOX no responde o faltan datos, captura manual asistida —
    nunca se bloquea el flujo (regla de negocio SIOX)."""

    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    assert_linea_permitida(session, verificacion.linea_id)

    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.DATOS_CAPTURADOS_MANUALMENTE,
        usuario_id=session.user_id,
        modulo="captura",
        evento="captura_manual",
    )
    await db.commit()
    return {"estado_expediente": verificacion.estado}
