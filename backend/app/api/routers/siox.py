import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionContext, assert_linea_permitida, get_db, requiere_estacion
from app.core.config import settings
from app.models.enums import EstadoVerificacion, FuenteDatos, StationType
from app.models.integration_log import (
    IntegrationDirection,
    IntegrationLog,
    IntegrationStatus,
)
from app.models.siox_consulta import EstadoSioxConsulta, SioxConsulta
from app.models.vehiculo import Vehiculo
from app.models.verificacion import Verificacion
from app.schemas.siox import SioxConsultaRead
from app.services import state_machine
from app.services.siox_client import consultar_placa

router = APIRouter(prefix="/api/siox", tags=["siox"])

STATUS_MAP = {
    "EXITOSA": EstadoSioxConsulta.EXITOSA,
    "SIN_DATOS": EstadoSioxConsulta.SIN_DATOS,
    "ERROR": EstadoSioxConsulta.ERROR,
}

# HU-012: campos de la respuesta normalizada de SIOX que tienen columna
# propia en Vehiculo. estatus/version/motor no tienen columna y quedan solo
# en siox_consultas.response_normalized.
VEHICULO_FIELDS = {"niv", "marca", "linea", "modelo", "tipo_vehiculo"}


@router.post("/consultar/{expediente_id}")
async def consultar_siox(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(requiere_estacion(StationType.CAPTURA)),
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
        # HU-012: mapear la respuesta normalizada a los campos del vehículo
        # y marcar su origen, para que el resto del flujo (inspección,
        # impresión) sepa que estos datos vienen de SIOX y no de captura.
        vehiculo = await db.get(Vehiculo, verificacion.vehiculo_id)
        campos_actualizados = {
            campo: valor
            for campo, valor in (resultado.normalized or {}).items()
            if campo in VEHICULO_FIELDS and valor is not None
        }
        for campo, valor in campos_actualizados.items():
            setattr(vehiculo, campo, valor)
        vehiculo.fuente_datos = FuenteDatos.SIOX
        db.add(vehiculo)

        await state_machine.transition(
            db,
            verificacion,
            EstadoVerificacion.DATOS_SIOX_IMPORTADOS,
            usuario_id=session.user_id,
            modulo="captura",
            evento="datos_siox_importados",
            detalle={"campos_actualizados": sorted(campos_actualizados)},
        )
    # Si status es SIN_DATOS o ERROR, el operador debe usar
    # /api/siox/captura-manual/{expediente_id} (regla: nunca bloquear).

    await db.commit()
    return {"status": resultado.status, "estado_expediente": verificacion.estado}


@router.get("/consultas/{expediente_id}", response_model=list[SioxConsultaRead])
async def historial_consultas_siox(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(requiere_estacion(StationType.CAPTURA)),
    db: AsyncSession = Depends(get_db),
) -> list[SioxConsulta]:
    """HU-013: historial de intentos de consulta SIOX de un expediente, más
    reciente primero. No expone `response_raw` (ver SioxConsultaRead)."""

    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    assert_linea_permitida(session, verificacion.linea_id)

    result = await db.execute(
        select(SioxConsulta)
        .where(SioxConsulta.verificacion_id == expediente_id)
        .order_by(SioxConsulta.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/captura-manual/{expediente_id}")
async def captura_manual(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(requiere_estacion(StationType.CAPTURA)),
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
