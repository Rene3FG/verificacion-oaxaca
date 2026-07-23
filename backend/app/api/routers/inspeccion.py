import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.enums import EstadoVerificacion, ResultadoInspeccionVisual
from app.models.inspeccion_visual import InspeccionVisual
from app.models.verificacion import Verificacion
from app.services import state_machine

router = APIRouter(prefix="/api/inspeccion", tags=["inspeccion"])


class InspeccionVisualCreate(BaseModel):
    resultado: ResultadoInspeccionVisual
    checklist_json: dict
    causales_rechazo: dict | None = None
    operador_id: uuid.UUID | None = None


@router.post("/{expediente_id}")
async def registrar_inspeccion(
    expediente_id: uuid.UUID,
    payload: InspeccionVisualCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    db.add(
        InspeccionVisual(
            verificacion_id=verificacion.id,
            resultado=payload.resultado,
            checklist_json=payload.checklist_json,
            causales_rechazo=payload.causales_rechazo,
            operador_id=payload.operador_id,
        )
    )

    nuevo_estado = (
        EstadoVerificacion.INSPECCION_VISUAL_APROBADA
        if payload.resultado == ResultadoInspeccionVisual.APROBADA
        else EstadoVerificacion.INSPECCION_VISUAL_RECHAZADA
    )
    await state_machine.transition(
        db,
        verificacion,
        nuevo_estado,
        usuario_id=payload.operador_id,
        modulo="visual",
        evento="inspeccion_visual_registrada",
        detalle={"resultado": payload.resultado},
    )

    if nuevo_estado == EstadoVerificacion.INSPECCION_VISUAL_RECHAZADA:
        # Regla de negocio #3: rechazo salta directo a Impresión Central.
        await state_machine.transition(
            db,
            verificacion,
            EstadoVerificacion.PENDIENTE_IMPRESION,
            usuario_id=payload.operador_id,
            modulo="visual",
            evento="rechazo_enviado_a_impresion",
        )

    await db.commit()
    return {"estado_expediente": verificacion.estado}
