import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.models.enums import EstadoVerificacion, ResultadoFinal, ResultadoPruebaEnum, TipoPrueba
from app.models.event_log import EventLog
from app.models.resultado_prueba import ResultadoPrueba
from app.models.verificacion import Verificacion
from app.schemas.verificacion import ExpedienteCompleto
from app.services import state_machine

router = APIRouter(prefix="/api/pruebas", tags=["pruebas"])


@router.get("/cola/{linea_id}", response_model=list[ExpedienteCompleto])
async def cola_prueba(linea_id: int, db: AsyncSession = Depends(get_db)) -> list[Verificacion]:
    """La estación de Prueba solo ve expedientes de su línea (regla del
    modelo de estaciones)."""

    result = await db.execute(
        select(Verificacion)
        .options(selectinload(Verificacion.vehiculo))
        .where(
            Verificacion.linea_id == linea_id,
            Verificacion.estado == EstadoVerificacion.LISTO_PARA_PRUEBA,
        )
        .order_by(Verificacion.created_at)
    )
    return list(result.scalars().all())


@router.post("/configurar/{expediente_id}")
async def configurar_prueba(
    expediente_id: uuid.UUID,
    tipo_prueba: TipoPrueba,
    cambio_manual: bool = False,
    motivo: str | None = None,
    usuario_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Regla de negocio #5/#9: gasolina -> dinámica por default, cambiable a
    estática con auditoría; diésel -> opacidad, sin cambio permitido."""

    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    verificacion.tipo_prueba_final = tipo_prueba
    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.PRUEBA_CONFIGURADA,
        usuario_id=usuario_id,
        modulo="prueba",
        evento="prueba_configurada",
        detalle={"tipo_prueba": tipo_prueba, "cambio_manual": cambio_manual},
    )

    if cambio_manual:
        # Cambio de gasolina dinámica a estática debe auditarse (regla #9).
        db.add(
            _cambio_tipo_prueba_event(verificacion.id, usuario_id, motivo, tipo_prueba)
        )

    await db.commit()
    return {"estado_expediente": verificacion.estado}


def _cambio_tipo_prueba_event(verificacion_id, usuario_id, motivo, tipo_prueba):
    return EventLog(
        verificacion_id=verificacion_id,
        evento="cambio_tipo_prueba_dinamica_a_estatica",
        estado_anterior=None,
        estado_nuevo=None,
        usuario_id=usuario_id,
        modulo="prueba",
        detalle_json={"motivo": motivo, "tipo_prueba": tipo_prueba},
    )


@router.post("/iniciar/{expediente_id}")
async def iniciar_prueba(
    expediente_id: uuid.UUID,
    usuario_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.PRUEBA_EN_PROCESO,
        usuario_id=usuario_id,
        modulo="prueba",
        evento="prueba_iniciada",
    )
    await db.commit()
    return {"estado_expediente": verificacion.estado}


class ResultadoPruebaInput(BaseModel):
    resultado: ResultadoPruebaEnum
    valores_medidos_json: dict
    limites_aplicados_json: dict | None = None
    equipo_id: uuid.UUID | None = None
    operador_id: uuid.UUID | None = None


@router.post("/resultado/{expediente_id}")
async def guardar_resultado_prueba(
    expediente_id: uuid.UUID,
    payload: ResultadoPruebaInput,
    db: AsyncSession = Depends(get_db),
) -> dict:
    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")

    db.add(
        ResultadoPrueba(
            verificacion_id=verificacion.id,
            tipo_prueba=verificacion.tipo_prueba_final,
            combustible=verificacion.combustible_validado or "",
            resultado=payload.resultado,
            valores_medidos_json=payload.valores_medidos_json,
            limites_aplicados_json=payload.limites_aplicados_json,
            equipo_id=payload.equipo_id,
            linea_id=verificacion.linea_id,
            operador_id=payload.operador_id,
            started_at=datetime.datetime.now(datetime.timezone.utc),
            finished_at=datetime.datetime.now(datetime.timezone.utc),
        )
    )

    verificacion.resultado_final = (
        ResultadoFinal.APROBADO
        if payload.resultado == ResultadoPruebaEnum.APROBADO
        else ResultadoFinal.RECHAZADO
    )

    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.PRUEBA_FINALIZADA,
        usuario_id=payload.operador_id,
        modulo="prueba",
        evento="resultado_prueba_guardado",
        detalle={"resultado": payload.resultado},
    )
    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.PENDIENTE_IMPRESION,
        usuario_id=payload.operador_id,
        modulo="prueba",
        evento="enviado_a_impresion",
    )
    await db.commit()
    return {"estado_expediente": verificacion.estado}
