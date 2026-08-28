import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    SessionContext,
    assert_linea_permitida,
    es_supervisor,
    get_db,
    requiere_estacion,
    requiere_supervisor,
)
from app.models.enums import EstadoFolio, EstadoPrintJob, EstadoVerificacion, StationType, TipoCertificado
from app.models.event_log import EventLog
from app.models.folio import Folio
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
from app.services.folio_inventario import SinFolioDisponible, asignar_siguiente_folio
from app.services.impresora import imprimir as imprimir_en_impresora
from app.services.sync import registrar_evento_con_sync

router = APIRouter(prefix="/api/impresion", tags=["impresion"])

# HU-072 a HU-079: desde estos dos estados se puede (re)intentar imprimir
# sin volver a solicitar folio (folio_externo ya vive en la fila de
# Verificacion, independiente del estado).
ESTADOS_IMPRIMIBLES = {EstadoVerificacion.FOLIO_ASIGNADO, EstadoVerificacion.IMPRESION_FALLIDA}

# Sección 3 del handoff (revisión Figma 2026-08-24): estados en los que ya
# existe un certificado físico impreso — la única condición bajo la cual
# aplican "reimpresión por daño" y "corrección de tipo después de
# imprimir". IMPRESION_FALLIDA queda fuera a propósito: ahí la impresora
# nunca produjo nada físico, así que es un reintento técnico, no una
# reimpresión (ver `imprimir_certificado`).
ESTADOS_CON_CERTIFICADO_IMPRESO = {
    EstadoVerificacion.IMPRESO,
    EstadoVerificacion.CERRADO_APROBADO,
    EstadoVerificacion.CERRADO_RECHAZADO,
}


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
                EstadoVerificacion.FOLIO_ERROR,
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


async def _folio_actual(db: AsyncSession, verificacion: Verificacion) -> Folio | None:
    """El folio del inventario local que corresponde a
    `verificacion.folio_externo` en este momento — nunca ambiguo: cada vez
    que un folio se reemplaza (dañado/invalidado), `folio_externo` pasa a
    apuntar al string del folio nuevo, así que el string ya no matchea la
    fila vieja."""

    if verificacion.folio_externo is None:
        return None
    return (
        await db.execute(
            select(Folio).where(
                Folio.verificacion_id == verificacion.id,
                Folio.folio == verificacion.folio_externo,
            )
        )
    ).scalars().first()


async def _imprimir_y_registrar(
    db: AsyncSession,
    verificacion: Verificacion,
    vehiculo: Vehiculo,
    folio: Folio | None,
    print_job: PrintJob,
) -> bool:
    """Genera el PDF y lo envía a la impresora física, registra el intento
    (`PrintAttempt`, fila inmutable — ver Etapa 12) y, si tuvo éxito, marca
    el folio usado como IMPRESO. Compartido por el primer clic en Imprimir
    y por las dos rutas de reimpresión posteriores (daño físico, corrección
    de tipo) — la mecánica de "generar → enviar → registrar intento" es
    idéntica en los tres casos, solo cambia qué folio/tipo se imprime."""

    pdf_bytes = generar_pdf_certificado(verificacion, vehiculo, verificacion.certificado_tipo)
    exito = await imprimir_en_impresora(pdf_bytes)

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
        # `folio` puede ser None: algunas fixtures/pruebas más antiguas al
        # camino de folios reales asignan `folio_externo` como string suelto
        # sin crear la fila de inventario correspondiente. No es un caso a
        # bloquear — solo no hay estatus de folio que actualizar.
        if folio is not None:
            folio.estatus = EstadoFolio.IMPRESO
            db.add(folio)
        print_job.estado = EstadoPrintJob.IMPRESO
        print_job.printed_at = datetime.datetime.now(datetime.timezone.utc)
        print_job.error_message = None
    else:
        print_job.estado = EstadoPrintJob.ERROR
        print_job.error_message = "La impresora no respondió."

    db.add(print_job)
    return exito


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
    automática todavía (Developer Handoff, confirmado 2026-08-24).

    Sección 3 del handoff: además de la selección inicial
    (PENDIENTE_IMPRESION/FOLIO_ERROR), este mismo endpoint cubre la
    "corrección de tipo ANTES de imprimir" con el expediente ya en
    FOLIO_ASIGNADO — el folio previamente asignado se libera (vuelve a
    DISPONIBLE, no se marca dañado, no cuenta como reimpresión) y se
    asigna atómicamente el siguiente folio disponible del nuevo tipo. Una
    vez impreso, la corrección de tipo es una operación distinta y
    exclusiva de Supervisor — ver `corregir_tipo_certificado_post_impresion`."""

    verificacion, _ = await _obtener_expediente_y_vehiculo(db, session, expediente_id)
    if verificacion.estado in ESTADOS_CON_CERTIFICADO_IMPRESO:
        raise HTTPException(
            status_code=409,
            detail=(
                "El expediente ya tiene un certificado impreso; corrija el tipo "
                "desde /tipo-certificado-post-impresion (exclusivo de Supervisor)."
            ),
        )

    try:
        tipo = await determinar_tipo_certificado(db, verificacion, tipo_certificado)
    except TipoCertificadoRequiereSeleccionManual as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TipoCertificadoIndeterminado as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    tipo_anterior = verificacion.certificado_tipo
    if verificacion.estado == EstadoVerificacion.FOLIO_ASIGNADO and tipo.value != tipo_anterior:
        folio_actual = await _folio_actual(db, verificacion)
        if folio_actual is None or folio_actual.estatus != EstadoFolio.ASIGNADO:
            raise HTTPException(
                status_code=409,
                detail="El folio actual del expediente no está en un estado corregible.",
            )
        try:
            folio_nuevo = await asignar_siguiente_folio(db, tipo, expediente_id)
        except SinFolioDisponible as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        folio_actual.estatus = EstadoFolio.DISPONIBLE
        folio_actual.verificacion_id = None
        folio_actual.asignado_at = None
        db.add(folio_actual)

        verificacion.folio_externo = folio_nuevo.folio
        verificacion.folio_asignado_at = folio_nuevo.asignado_at

        await registrar_evento_con_sync(
            db,
            EventLog(
                verificacion_id=verificacion.id,
                evento="tipo_certificado_corregido_antes_de_imprimir",
                estado_anterior=verificacion.estado,
                estado_nuevo=verificacion.estado,
                usuario_id=session.user_id,
                modulo="impresion",
                detalle_json={
                    "tipo_anterior": tipo_anterior,
                    "tipo_nuevo": tipo.value,
                    "folio_liberado": folio_actual.folio,
                    "folio_nuevo": folio_nuevo.folio,
                },
            ),
            verificacion=verificacion,
        )

    verificacion.certificado_tipo = tipo.value
    db.add(verificacion)
    await db.commit()
    return {"certificado_tipo": tipo.value, "folio_externo": verificacion.folio_externo}


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
    paso aparte, ver /cerrar.

    Sección 3 del handoff: el primer clic lo puede hacer cualquier operador
    de Impresión, pero un "reintento técnico" desde IMPRESION_FALLIDA
    (la impresora ya falló una vez) es exclusivo de Supervisor. Reintentar
    no vuelve a pedir folio — mismo folio y mismo `PrintJob`, cuya
    `created_at` es la "Hora Salida" del handoff: se fija una sola vez, al
    crearse este `PrintJob` en el primer clic, y ningún camino posterior
    (reintento, reimpresión, cierre) la modifica."""

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
        if not await es_supervisor(session, db):
            raise HTTPException(
                status_code=403,
                detail="Reintentar un certificado tras una impresión fallida requiere Supervisor.",
            )
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

    folio = await _folio_actual(db, verificacion)
    exito = await _imprimir_y_registrar(db, verificacion, vehiculo, folio, print_job)

    if exito:
        await state_machine.transition(
            db,
            verificacion,
            EstadoVerificacion.IMPRESO,
            usuario_id=session.user_id,
            modulo="impresion",
            evento="certificado_impreso",
        )
    else:
        await state_machine.transition(
            db,
            verificacion,
            EstadoVerificacion.IMPRESION_FALLIDA,
            usuario_id=session.user_id,
            modulo="impresion",
            evento="impresion_fallida",
            detalle={"intentos": print_job.intentos},
        )

    await db.commit()
    return {"estado_expediente": verificacion.estado, "intentos": print_job.intentos}


@router.post("/folio/marcar-danado/{expediente_id}")
async def marcar_folio_danado(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(requiere_estacion(StationType.IMPRESION)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Sección 3 del handoff: antes del primer clic en Imprimir, el
    Operador de Impresión puede marcar el folio físico asignado como
    DAÑADO/NO DISPONIBLE si está defectuoso — sin Supervisor, sin motivo,
    y sin que cuente como reimpresión (nada se ha impreso todavía). El
    sistema toma atómicamente el siguiente folio disponible del mismo
    tipo; si el inventario de ese tipo también está agotado, el expediente
    cae a FOLIO_ERROR, igual que una solicitud de folio sin inventario."""

    verificacion, _ = await _obtener_expediente_y_vehiculo(db, session, expediente_id)
    if verificacion.estado != EstadoVerificacion.FOLIO_ASIGNADO:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede marcar el folio dañado en estado {verificacion.estado}",
        )

    folio_actual = await _folio_actual(db, verificacion)
    if folio_actual is None or folio_actual.estatus != EstadoFolio.ASIGNADO:
        raise HTTPException(
            status_code=409,
            detail="El expediente no tiene un folio asignado en un estado corregible.",
        )

    tipo_certificado = folio_actual.tipo_certificado
    folio_actual.estatus = EstadoFolio.DANADO
    folio_actual.danado_at = datetime.datetime.now(datetime.timezone.utc)
    db.add(folio_actual)

    try:
        folio_nuevo = await asignar_siguiente_folio(db, tipo_certificado, expediente_id)
    except SinFolioDisponible as exc:
        await state_machine.transition(
            db,
            verificacion,
            EstadoVerificacion.FOLIO_ERROR,
            usuario_id=session.user_id,
            modulo="impresion",
            evento="folio_danado_sin_reemplazo",
            detalle={"folio_danado": folio_actual.folio, "tipo_certificado": tipo_certificado.value},
        )
        await db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    folio_actual.reemplazado_por_folio_id = folio_nuevo.id
    verificacion.folio_externo = folio_nuevo.folio
    verificacion.folio_asignado_at = folio_nuevo.asignado_at
    db.add(verificacion)

    await registrar_evento_con_sync(
        db,
        EventLog(
            verificacion_id=verificacion.id,
            evento="folio_marcado_danado",
            estado_anterior=verificacion.estado,
            estado_nuevo=verificacion.estado,
            usuario_id=session.user_id,
            modulo="impresion",
            detalle_json={"folio_danado": folio_actual.folio, "folio_nuevo": folio_nuevo.folio},
        ),
        verificacion=verificacion,
    )

    await db.commit()
    return {"folio_danado": folio_actual.folio, "folio_externo": verificacion.folio_externo}


class ReimpresionPorDanoRequest(BaseModel):
    motivo: str = Field(min_length=1)


@router.post("/folio/reimprimir-por-dano/{expediente_id}")
async def reimprimir_por_dano(
    expediente_id: uuid.UUID,
    payload: ReimpresionPorDanoRequest,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Sección 3 del handoff: el certificado físico ya se imprimió al
    menos una vez (IMPRESO o ya CERRADO_*) y resultó dañado. Exclusivo de
    Supervisor, motivo obligatorio; usa el siguiente folio disponible del
    mismo tipo y conserva Hora Salida (`PrintJob.created_at`, fijada en el
    primer clic en Imprimir y nunca reescrita aquí). El estado del
    expediente no cambia: si ya estaba CERRADO_*, sigue cerrado; si estaba
    IMPRESO sin cerrar, sigue pendiente de que el operador confirme
    /cerrar con el nuevo certificado en mano."""

    verificacion, vehiculo = await _obtener_expediente_y_vehiculo(db, session, expediente_id)
    if verificacion.estado not in ESTADOS_CON_CERTIFICADO_IMPRESO:
        raise HTTPException(
            status_code=409,
            detail=f"No hay certificado impreso que reimprimir en estado {verificacion.estado}",
        )

    print_job = (
        await db.execute(select(PrintJob).where(PrintJob.verificacion_id == expediente_id))
    ).scalars().first()
    if print_job is None:
        raise HTTPException(status_code=409, detail="El expediente no tiene un trabajo de impresión previo.")

    folio_actual = await _folio_actual(db, verificacion)
    if folio_actual is None:
        raise HTTPException(status_code=409, detail="El expediente no tiene folio asignado.")

    if folio_actual.estatus == EstadoFolio.IMPRESO:
        try:
            folio_nuevo = await asignar_siguiente_folio(db, folio_actual.tipo_certificado, expediente_id)
        except SinFolioDisponible as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        folio_actual.estatus = EstadoFolio.DANADO
        folio_actual.danado_at = datetime.datetime.now(datetime.timezone.utc)
        folio_actual.motivo_danado = payload.motivo
        folio_actual.reemplazado_por_folio_id = folio_nuevo.id
        db.add(folio_actual)

        verificacion.folio_externo = folio_nuevo.folio
        verificacion.folio_asignado_at = folio_nuevo.asignado_at
        db.add(verificacion)

        await registrar_evento_con_sync(
            db,
            EventLog(
                verificacion_id=verificacion.id,
                evento="folio_marcado_danado_reimpresion",
                estado_anterior=verificacion.estado,
                estado_nuevo=verificacion.estado,
                usuario_id=session.user_id,
                modulo="impresion",
                detalle_json={
                    "motivo": payload.motivo,
                    "folio_danado": folio_actual.folio,
                    "folio_nuevo": folio_nuevo.folio,
                },
            ),
            verificacion=verificacion,
        )
        folio_para_imprimir = folio_nuevo
    elif folio_actual.estatus == EstadoFolio.ASIGNADO:
        # Reimpresión ya autorizada en una llamada previa (el canje de
        # folio ya ocurrió); esta es solo el reintento técnico del envío
        # físico a la impresora, no una nueva decisión de reimpresión.
        folio_para_imprimir = folio_actual
    else:
        raise HTTPException(
            status_code=409,
            detail=f"El folio actual está en estado {folio_actual.estatus.value}, no es reimprimible.",
        )

    exito = await _imprimir_y_registrar(db, verificacion, vehiculo, folio_para_imprimir, print_job)
    await db.commit()
    return {
        "folio": folio_para_imprimir.folio,
        "impreso": exito,
        "estado_expediente": verificacion.estado,
    }


@router.post("/tipo-certificado-post-impresion/{expediente_id}")
async def corregir_tipo_certificado_post_impresion(
    expediente_id: uuid.UUID,
    nuevo_tipo: TipoCertificado,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Sección 3 del handoff: el tipo equivocado se detectó DESPUÉS de
    imprimir. Exclusivo de Supervisor, SIN motivo obligatorio (la propia
    acción de corrección identifica la causa). El folio usado pasa a
    INVALIDADO (no DAÑADO — el papel no está defectuoso, el tipo lo
    estaba); se asigna un folio nuevo del tipo correcto, se reimprime y se
    conserva Hora Salida. RECHAZO sigue sin admitir corrección manual: se
    infiere solo, nunca por selección del operador."""

    verificacion, vehiculo = await _obtener_expediente_y_vehiculo(db, session, expediente_id)
    if verificacion.estado not in ESTADOS_CON_CERTIFICADO_IMPRESO:
        raise HTTPException(
            status_code=409,
            detail=f"No hay certificado impreso que corregir en estado {verificacion.estado}",
        )
    if nuevo_tipo == TipoCertificado.RECHAZO or verificacion.certificado_tipo == TipoCertificado.RECHAZO.value:
        raise HTTPException(
            status_code=409,
            detail="RECHAZO no admite corrección manual de tipo: se infiere solo.",
        )

    print_job = (
        await db.execute(select(PrintJob).where(PrintJob.verificacion_id == expediente_id))
    ).scalars().first()
    if print_job is None:
        raise HTTPException(status_code=409, detail="El expediente no tiene un trabajo de impresión previo.")

    folio_actual = await _folio_actual(db, verificacion)
    if folio_actual is None:
        raise HTTPException(status_code=409, detail="El expediente no tiene folio asignado.")

    tipo_anterior = verificacion.certificado_tipo

    if folio_actual.estatus == EstadoFolio.IMPRESO:
        if nuevo_tipo.value == tipo_anterior:
            raise HTTPException(status_code=409, detail="El expediente ya tiene ese tipo de certificado.")

        try:
            folio_nuevo = await asignar_siguiente_folio(db, nuevo_tipo, expediente_id)
        except SinFolioDisponible as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        folio_actual.estatus = EstadoFolio.INVALIDADO
        folio_actual.invalidado_at = datetime.datetime.now(datetime.timezone.utc)
        folio_actual.motivo_invalidacion = "Corrección de tipo de certificado después de imprimir"
        folio_actual.reemplazado_por_folio_id = folio_nuevo.id
        db.add(folio_actual)

        verificacion.certificado_tipo = nuevo_tipo.value
        verificacion.folio_externo = folio_nuevo.folio
        verificacion.folio_asignado_at = folio_nuevo.asignado_at
        db.add(verificacion)

        await registrar_evento_con_sync(
            db,
            EventLog(
                verificacion_id=verificacion.id,
                evento="tipo_certificado_corregido_despues_de_imprimir",
                estado_anterior=verificacion.estado,
                estado_nuevo=verificacion.estado,
                usuario_id=session.user_id,
                modulo="impresion",
                detalle_json={
                    "tipo_anterior": tipo_anterior,
                    "tipo_nuevo": nuevo_tipo.value,
                    "folio_invalidado": folio_actual.folio,
                    "folio_nuevo": folio_nuevo.folio,
                },
            ),
            verificacion=verificacion,
        )
        folio_para_imprimir = folio_nuevo
    elif folio_actual.estatus == EstadoFolio.ASIGNADO:
        # Corrección ya autorizada en una llamada previa (certificado_tipo
        # y folio ya se cambiaron); esta es solo el reintento técnico del
        # envío físico a la impresora.
        folio_para_imprimir = folio_actual
    else:
        raise HTTPException(
            status_code=409,
            detail=f"El folio actual está en estado {folio_actual.estatus.value}, no es corregible.",
        )

    exito = await _imprimir_y_registrar(db, verificacion, vehiculo, folio_para_imprimir, print_job)
    await db.commit()
    return {
        "certificado_tipo": verificacion.certificado_tipo,
        "folio": folio_para_imprimir.folio,
        "impreso": exito,
        "estado_expediente": verificacion.estado,
    }


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
