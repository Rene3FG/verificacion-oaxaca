import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import SessionContext, assert_linea_permitida, get_db, requiere_estacion
from app.models.enums import EstadoPrintJob, EstadoVerificacion, StationType, TipoCertificado
from app.models.print_attempt import PrintAttempt
from app.models.print_job import PrintJob
from app.models.vehiculo import Vehiculo
from app.models.verificacion import Verificacion
from app.schemas.verificacion import ExpedienteCompleto
from app.services import state_machine
from app.services.certificado import (
    TipoCertificadoIndeterminado,
    TipoCertificadoRequiereSeleccionManual,
    determinar_tipo_certificado,
    generar_pdf_certificado,
)
from app.services.impresora import imprimir as imprimir_en_impresora

router = APIRouter(prefix="/api/impresion", tags=["impresion"])

# HU-072 a HU-079: desde estos dos estados se puede (re)intentar imprimir
# sin volver a solicitar folio (folio_externo ya vive en la fila de
# Verificacion, independiente del estado).
ESTADOS_IMPRIMIBLES = {EstadoVerificacion.FOLIO_ASIGNADO, EstadoVerificacion.IMPRESION_FALLIDA}


@router.get("/cola", response_model=list[ExpedienteCompleto])
async def cola_impresion(
    linea_id: int | None = None,
    session: SessionContext = Depends(requiere_estacion(StationType.IMPRESION)),
    db: AsyncSession = Depends(get_db),
) -> list[Verificacion]:
    """Impresión es central: sin filtro recibe expedientes de TODAS las
    líneas que la estación tiene permitidas (`allowed_line_ids`), nunca de
    todas las líneas del sistema. El filtro `?linea_id=` solo puede
    estrechar ese conjunto, jamás ampliarlo: si pide una línea fuera de
    `allowed_line_ids` la cola simplemente sale vacía, nunca expone otra
    línea.

    También se acota por `centro_id` de la sesión: el número de línea es
    local a cada centro (ver docstring de `assert_linea_permitida`), y una
    estación centralizada solo pertenece a un centro."""

    lineas_permitidas = session.lineas_visibles()
    lineas_query = {linea_id} & lineas_permitidas if linea_id is not None else lineas_permitidas

    query = select(Verificacion).options(selectinload(Verificacion.vehiculo)).where(
        Verificacion.estado.in_(
            [
                EstadoVerificacion.PENDIENTE_IMPRESION,
                EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO,
                EstadoVerificacion.FOLIO_SOLICITADO,
                EstadoVerificacion.FOLIO_ASIGNADO,
                EstadoVerificacion.IMPRESION_FALLIDA,
            ]
        ),
        Verificacion.centro_id == session.center_id,
        Verificacion.linea_id.in_(lineas_query),
    )

    result = await db.execute(query.order_by(Verificacion.created_at))
    return list(result.scalars().all())


async def _obtener_expediente_y_vehiculo(
    db: AsyncSession, session: SessionContext, expediente_id: uuid.UUID
) -> tuple[Verificacion, Vehiculo]:
    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    assert_linea_permitida(session, verificacion.centro_id, verificacion.linea_id)
    vehiculo = await db.get(Vehiculo, verificacion.vehiculo_id)
    return verificacion, vehiculo


@router.post("/tipo-certificado/{expediente_id}")
async def calcular_tipo_certificado(
    expediente_id: uuid.UUID,
    tipo_certificado: TipoCertificado | None = None,
    session: SessionContext = Depends(requiere_estacion(StationType.IMPRESION)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """HU-061: determina certificado_tipo (ver app.services.certificado) y
    lo persiste en el expediente. Un resultado RECHAZADO se infiere solo;
    uno APROBADO requiere que el Operador mande `tipo_certificado`
    (Particular/Doble Cero/Intensivo) — no hay regla de elegibilidad
    automática todavía (Developer Handoff, confirmado 2026-08-24)."""

    verificacion, _ = await _obtener_expediente_y_vehiculo(db, session, expediente_id)
    try:
        tipo = await determinar_tipo_certificado(db, verificacion, tipo_certificado)
    except TipoCertificadoRequiereSeleccionManual as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TipoCertificadoIndeterminado as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    verificacion.certificado_tipo = tipo.value
    db.add(verificacion)
    await db.commit()
    return {"certificado_tipo": tipo.value}


@router.get("/vista-previa/{expediente_id}")
async def vista_previa_certificado(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(requiere_estacion(StationType.IMPRESION)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """HU-062: genera el PDF y lo devuelve para previsualizar, sin tocar
    estado ni crear un PrintJob — no es la impresión definitiva. Requiere
    que `certificado_tipo` ya se haya calculado/seleccionado antes (ya no
    se infiere aquí: un aprobado no tiene un único tipo posible)."""

    verificacion, vehiculo = await _obtener_expediente_y_vehiculo(db, session, expediente_id)
    if verificacion.certificado_tipo is None:
        raise HTTPException(
            status_code=409,
            detail="Primero debe calcularse/seleccionarse el tipo de certificado.",
        )

    pdf_bytes = generar_pdf_certificado(verificacion, vehiculo, verificacion.certificado_tipo)
    return Response(content=pdf_bytes, media_type="application/pdf")


@router.post("/imprimir/{expediente_id}")
async def imprimir_certificado(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(requiere_estacion(StationType.IMPRESION)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Regla de negocio #7: sin folio externo confirmado NO se imprime
    certificado definitivo. Regla #9: la impresión consulta el expediente
    directamente en BD, el operador no captura datos críticos a mano.

    FOLIO_ASIGNADO, IMPRESO y CERRADO_APROBADO/CERRADO_RECHAZADO son estados
    distintos (HU-072 a HU-079): esta operación solo llega hasta IMPRESO (o
    IMPRESION_FALLIDA si la impresora falla). Cerrar el expediente es un
    paso aparte, ver /cerrar. Reintentar desde IMPRESION_FALLIDA no vuelve
    a pedir folio."""

    verificacion, vehiculo = await _obtener_expediente_y_vehiculo(db, session, expediente_id)
    if verificacion.folio_externo is None:
        raise HTTPException(
            status_code=409,
            detail="No se puede imprimir: folio externo no confirmado",
        )
    if verificacion.estado not in ESTADOS_IMPRIMIBLES:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede imprimir un expediente en estado {verificacion.estado}",
        )

    if verificacion.estado == EstadoVerificacion.IMPRESION_FALLIDA:
        await state_machine.transition(
            db,
            verificacion,
            EstadoVerificacion.FOLIO_ASIGNADO,
            usuario_id=session.user_id,
            modulo="impresion",
            evento="reintento_impresion_sin_nuevo_folio",
        )

    if verificacion.certificado_tipo is None:
        raise HTTPException(
            status_code=409,
            detail="Primero debe calcularse/seleccionarse el tipo de certificado.",
        )

    print_job = (
        await db.execute(
            select(PrintJob).where(PrintJob.verificacion_id == expediente_id)
        )
    ).scalars().first()
    if print_job is None:
        print_job = PrintJob(
            verificacion_id=expediente_id,
            tipo_documento=verificacion.certificado_tipo,
            folio_externo=verificacion.folio_externo,
        )
        db.add(print_job)
        await db.flush()

    pdf_bytes = generar_pdf_certificado(verificacion, vehiculo, verificacion.certificado_tipo)
    exito = await imprimir_en_impresora(pdf_bytes)

    # Etapa 12: un intento es su propia fila inmutable (PrintAttempt), no un
    # contador mutado — ver docstring de app.models.print_attempt.
    # print_job.intentos se recalcula por conteo, nunca se incrementa: es
    # una caché idempotente bajo reenvío de sync.
    db.add(
        PrintAttempt(
            print_job_id=print_job.id,
            verificacion_id=verificacion.id,
            exitoso=exito,
            error_message=None if exito else "La impresora no respondió.",
        )
    )
    await db.flush()
    print_job.intentos = (
        await db.execute(
            select(func.count())
            .select_from(PrintAttempt)
            .where(PrintAttempt.print_job_id == print_job.id)
        )
    ).scalar_one()

    if exito:
        print_job.estado = EstadoPrintJob.IMPRESO
        print_job.printed_at = datetime.datetime.now(datetime.timezone.utc)
        print_job.error_message = None
        await state_machine.transition(
            db,
            verificacion,
            EstadoVerificacion.IMPRESO,
            usuario_id=session.user_id,
            modulo="impresion",
            evento="certificado_impreso",
        )
    else:
        print_job.estado = EstadoPrintJob.ERROR
        print_job.error_message = "La impresora no respondió."
        await state_machine.transition(
            db,
            verificacion,
            EstadoVerificacion.IMPRESION_FALLIDA,
            usuario_id=session.user_id,
            modulo="impresion",
            evento="impresion_fallida",
            detalle={"intentos": print_job.intentos},
        )

    db.add(print_job)
    await db.commit()
    return {"estado_expediente": verificacion.estado, "intentos": print_job.intentos}


# HU-072 a HU-079: condiciones propuestas para cerrar el expediente, a falta
# del documento de diseño del proyecto (no está en el repo — ver nota en
# app.services.certificado). Confirmar/corregir contra el diseño real.
def _condiciones_de_cierre_incumplidas(
    verificacion: Verificacion, print_job: PrintJob | None
) -> list[str]:
    incumplidas = []
    if verificacion.estado != EstadoVerificacion.IMPRESO:
        incumplidas.append(f"el expediente está en estado {verificacion.estado}, no IMPRESO")
    if verificacion.folio_externo is None:
        incumplidas.append("no tiene folio externo confirmado")
    if verificacion.certificado_tipo is None:
        incumplidas.append("no tiene certificado_tipo determinado")
    if print_job is None or print_job.estado != EstadoPrintJob.IMPRESO:
        incumplidas.append("no tiene un print job en estado IMPRESO")
    if verificacion.cerrado_at is not None:
        incumplidas.append("ya está cerrado")
    return incumplidas


@router.post("/cerrar/{expediente_id}")
async def cerrar_expediente(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(requiere_estacion(StationType.IMPRESION)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    verificacion, _ = await _obtener_expediente_y_vehiculo(db, session, expediente_id)

    print_job = (
        await db.execute(
            select(PrintJob).where(PrintJob.verificacion_id == expediente_id)
        )
    ).scalars().first()

    incumplidas = _condiciones_de_cierre_incumplidas(verificacion, print_job)
    if incumplidas:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede cerrar el expediente: {'; '.join(incumplidas)}.",
        )

    # certificado_tipo ya es obligatorio para llegar hasta aquí (ver
    # _condiciones_de_cierre_incumplidas) y RECHAZO es el único tipo posible
    # para un expediente rechazado (app.services.certificado) — mismo dato
    # que ya distingue la cola de impresión (PENDIENTE_IMPRESION vs
    # PENDIENTE_DE_IMPRESION_RECHAZO), reusado aquí para el cierre.
    nuevo_estado = (
        EstadoVerificacion.CERRADO_RECHAZADO
        if verificacion.certificado_tipo == TipoCertificado.RECHAZO.value
        else EstadoVerificacion.CERRADO_APROBADO
    )
    await state_machine.transition(
        db,
        verificacion,
        nuevo_estado,
        usuario_id=session.user_id,
        modulo="impresion",
        evento="expediente_cerrado",
    )
    await db.commit()
    return {"estado_expediente": verificacion.estado}
