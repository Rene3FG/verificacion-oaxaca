import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.enums import EstadoFolioAssignment, EstadoFolioRequest, EstadoVerificacion
from app.models.folio_assignment import FolioAssignment
from app.models.folio_request import FolioRequest
from app.models.integration_log import (
    IntegrationDirection,
    IntegrationLog,
    IntegrationStatus,
)
from app.models.verificacion import Verificacion
from app.services import state_machine

router = APIRouter(prefix="/api/folios", tags=["folios"])


async def _consultar_sistema_externo_folios(payload: dict) -> dict:
    """PENDIENTE: integración real con el sistema externo de folios (no
    definido aún — ver 'Qué sucede con los folios' en el proyecto). El
    sistema de verificación NUNCA administra inventario de folios, solo
    solicita/recibe/asigna (regla de negocio #7)."""

    return {"folio": None, "external_reference_id": None, "status": "error"}


@router.post("/solicitar/{expediente_id}")
async def solicitar_folio(
    expediente_id: uuid.UUID,
    tipo_certificado: str,
    tipo_vehiculo: str | None = None,
    print_job_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Idempotente (regla #12): un expediente cerrado solo puede tener un
    folio activo por tipo de certificado. Antes de solicitar uno nuevo se
    reutiliza cualquier solicitud ASIGNADA previa para el mismo tipo."""

    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    existente = await db.execute(
        select(FolioRequest).where(
            FolioRequest.verificacion_id == expediente_id,
            FolioRequest.tipo_certificado == tipo_certificado,
            FolioRequest.status == EstadoFolioRequest.ASIGNADO,
        )
    )
    solicitud = existente.scalar_one_or_none()

    if solicitud is None:
        solicitud = FolioRequest(
            verificacion_id=expediente_id,
            print_job_id=print_job_id,
            tipo_certificado=tipo_certificado,
            tipo_vehiculo=tipo_vehiculo,
            request_payload={"tipo_certificado": tipo_certificado},
        )
        db.add(solicitud)
        await db.flush()

        await state_machine.transition(
            db,
            verificacion,
            EstadoVerificacion.FOLIO_SOLICITADO,
            usuario_id=None,
            modulo="folios",
            evento="folio_solicitado",
        )

        respuesta = await _consultar_sistema_externo_folios(solicitud.request_payload)
        db.add(
            IntegrationLog(
                verificacion_id=expediente_id,
                integration_name="sistema_folios",
                direction=IntegrationDirection.RESPONSE,
                payload=respuesta,
                status=IntegrationStatus.OK
                if respuesta["status"] == "asignado"
                else IntegrationStatus.ERROR,
                error_message=None
                if respuesta["status"] == "asignado"
                else "El sistema externo de folios no respondió",
            )
        )

        if respuesta["status"] == "asignado":
            solicitud.status = EstadoFolioRequest.ASIGNADO
            solicitud.response_payload = respuesta
            solicitud.folio_recibido = respuesta["folio"]
            solicitud.external_reference_id = respuesta["external_reference_id"]
            solicitud.completed_at = datetime.datetime.now(datetime.timezone.utc)

            db.add(
                FolioAssignment(
                    verificacion_id=expediente_id,
                    folio_request_id=solicitud.id,
                    folio=respuesta["folio"],
                    tipo_certificado=tipo_certificado,
                    estatus=EstadoFolioAssignment.ASIGNADO,
                )
            )
            verificacion.folio_externo = respuesta["folio"]
            verificacion.folio_asignado_at = datetime.datetime.now(datetime.timezone.utc)

            await state_machine.transition(
                db,
                verificacion,
                EstadoVerificacion.FOLIO_ASIGNADO,
                usuario_id=None,
                modulo="folios",
                evento="folio_asignado",
            )
        else:
            solicitud.status = EstadoFolioRequest.ERROR
            await state_machine.transition(
                db,
                verificacion,
                EstadoVerificacion.FOLIO_ERROR,
                usuario_id=None,
                modulo="folios",
                evento="folio_error",
            )

    await db.commit()
    return {
        "folio": solicitud.folio_recibido,
        "status": solicitud.status,
        "estado_expediente": verificacion.estado,
    }
