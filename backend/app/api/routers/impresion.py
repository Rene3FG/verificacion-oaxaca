import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import SessionContext, assert_linea_permitida, get_current_session, get_db
from app.models.enums import EstadoPrintJob, EstadoVerificacion
from app.models.print_job import PrintJob
from app.models.verificacion import Verificacion
from app.schemas.verificacion import ExpedienteCompleto
from app.services import state_machine

router = APIRouter(prefix="/api/impresion", tags=["impresion"])


@router.get("/cola", response_model=list[ExpedienteCompleto])
async def cola_impresion(
    linea_id: int | None = None,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> list[Verificacion]:
    """Impresión es central: sin filtro recibe expedientes de TODAS las
    líneas que la estación tiene permitidas (`allowed_line_ids`), nunca de
    todas las líneas del sistema. El filtro `?linea_id=` solo puede
    estrechar ese conjunto, jamás ampliarlo: si pide una línea fuera de
    `allowed_line_ids` la cola simplemente sale vacía, nunca expone otra
    línea."""

    lineas_permitidas = session.lineas_visibles()
    lineas_query = {linea_id} & lineas_permitidas if linea_id is not None else lineas_permitidas

    query = select(Verificacion).options(selectinload(Verificacion.vehiculo)).where(
        Verificacion.estado.in_(
            [
                EstadoVerificacion.PENDIENTE_IMPRESION,
                EstadoVerificacion.FOLIO_SOLICITADO,
                EstadoVerificacion.FOLIO_ASIGNADO,
                EstadoVerificacion.IMPRESION_FALLIDA,
            ]
        ),
        Verificacion.linea_id.in_(lineas_query),
    )

    result = await db.execute(query.order_by(Verificacion.created_at))
    return list(result.scalars().all())


@router.post("/imprimir/{expediente_id}")
async def imprimir_certificado(
    expediente_id: uuid.UUID,
    print_job_id: uuid.UUID,
    session: SessionContext = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Regla de negocio #7: sin folio externo confirmado NO se imprime
    certificado definitivo. Regla #9: la impresión consulta el expediente
    directamente en BD, el operador no captura datos críticos a mano."""

    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    assert_linea_permitida(session, verificacion.linea_id)
    if verificacion.folio_externo is None:
        raise HTTPException(
            status_code=409,
            detail="No se puede imprimir: folio externo no confirmado",
        )

    print_job = await db.get(PrintJob, print_job_id)
    if print_job is None:
        raise HTTPException(status_code=404, detail="Print job no encontrado")

    # TODO: generar PDF real con WeasyPrint a partir del expediente completo
    # y manejar aquí el caso de impresora real fallando -> IMPRESION_FALLIDA
    # (print_job.estado = ERROR, intentos += 1, error_message).
    print_job.estado = EstadoPrintJob.IMPRESO
    print_job.printed_at = datetime.datetime.now(datetime.timezone.utc)

    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.IMPRESO,
        usuario_id=session.user_id,
        modulo="impresion",
        evento="certificado_impreso",
    )
    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.CERRADO,
        usuario_id=session.user_id,
        modulo="impresion",
        evento="expediente_cerrado",
    )
    await db.commit()
    return {"estado_expediente": verificacion.estado}
