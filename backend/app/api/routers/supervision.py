import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import SessionContext, get_db, requiere_supervisor
from app.models.enums import EstadoVerificacion, SyncStatus
from app.models.event_log import EventLog
from app.models.print_job import PrintJob
from app.models.prorroga_semestre import ProrrogaSemestre
from app.models.sync_outbox import SyncOutbox
from app.models.usuario import CatUsuario
from app.models.verificacion import Verificacion
from app.schemas.event_log import AuditoriaPagina, AuditoriaRead, EventLogRead
from app.schemas.verificacion import ExpedienteCompleto, ExpedienteRead
from app.services.proyeccion_certificado import calcular_semestre
from app.services.semestre import ZONA_OAXACA, hoy_oaxaca, obtener_prorroga_activa

router = APIRouter(prefix="/api/supervision", tags=["supervision"])

# Un expediente CERRADO_APROBADO/CERRADO_RECHAZADO/CANCELADO ya no es
# "piso" — no aparece en el monitor en vivo, aunque su bitácora siga
# consultable por separado.
ESTADOS_TERMINALES = {
    EstadoVerificacion.CERRADO_APROBADO,
    EstadoVerificacion.CERRADO_RECHAZADO,
    EstadoVerificacion.CANCELADO,
}


@router.get("/monitor", response_model=list[ExpedienteCompleto])
async def monitor_centro(
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> list[Verificacion]:
    """HU-111: todas las líneas del centro de la sesión del supervisor, a
    diferencia de las colas por estación (Captura/Prueba/Impresión), que
    solo ven su propia línea o sus allowed_line_ids."""

    if session.center_id is None:
        raise HTTPException(status_code=400, detail="La sesión no tiene centro asociado.")

    result = await db.execute(
        select(Verificacion)
        .options(selectinload(Verificacion.vehiculo))
        .where(
            Verificacion.centro_id == session.center_id,
            Verificacion.estado.not_in(ESTADOS_TERMINALES),
        )
        .order_by(Verificacion.linea_id, Verificacion.created_at)
    )
    return list(result.scalars().all())


@router.get("/expedientes/buscar", response_model=list[ExpedienteRead])
async def buscar_expedientes(
    placa: str,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> list[Verificacion]:
    """Punto de entrada para reimpresión por daño y corrección de tipo
    post-impresión (sección 3 del handoff, 2026-09-03): esas dos
    operaciones solo aplican en `IMPRESO`/`CERRADO_APROBADO`/
    `CERRADO_RECHAZADO`, que `GET /impresion/cola` excluye a propósito
    (ya no son "piso") y `GET /supervision/monitor` también excluye
    (`ESTADOS_TERMINALES`) — hasta ahora ninguna pantalla de Supervisor
    permitía abrir un expediente en esos estados. Sin restricción de
    `estado` aquí (a diferencia de monitor): el Supervisor necesita
    encontrar el expediente para decidir qué operación aplica, no al
    revés. Todas las líneas del centro de la sesión, igual que
    `monitor_centro` — no acotado por `lineas_visibles()` (esa
    restricción es para las colas por estación, no para Supervisor)."""

    if session.center_id is None:
        raise HTTPException(status_code=400, detail="La sesión no tiene centro asociado.")
    if not placa.strip():
        raise HTTPException(status_code=422, detail="Falta la placa a buscar.")

    result = await db.execute(
        select(Verificacion)
        .where(
            Verificacion.centro_id == session.center_id,
            Verificacion.placa.ilike(f"%{placa.strip()}%"),
        )
        .order_by(Verificacion.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/expedientes/{expediente_id}/bitacora", response_model=list[EventLogRead])
async def bitacora_expediente(
    expediente_id: uuid.UUID,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> list[EventLog]:
    """HU-117: línea de tiempo completa de un expediente — todos los
    módulos que lo tocaron (captura, siox, visual, obd, prueba, folios,
    impresión, supervisión), no solo el de quien consulta."""

    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    if session.center_id is not None and verificacion.centro_id != session.center_id:
        raise HTTPException(
            status_code=403, detail="No puedes ver expedientes de otro centro."
        )

    result = await db.execute(
        select(EventLog)
        .where(EventLog.verificacion_id == expediente_id)
        .order_by(EventLog.created_at)
    )
    return list(result.scalars().all())


@router.get("/auditoria", response_model=AuditoriaPagina)
async def auditoria_centro(
    desde: datetime.date | None = None,
    hasta: datetime.date | None = None,
    usuario_id: uuid.UUID | None = None,
    placa: str | None = None,
    modulo: str | None = None,
    limite: int = Query(100, ge=1, le=500),
    desplazamiento: int = Query(0, ge=0),
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> AuditoriaPagina:
    """N4 (Figma §12, pantalla 'Supervisión / Auditoría'): bitácora global
    del centro de la sesión, filtrable por fecha (inclusive en ambos
    extremos), usuario, placa/expediente y módulo. A diferencia de
    `bitacora_expediente`, no exige conocer el expediente de antemano.
    Más reciente primero. Acotada al centro del supervisor, igual que
    monitor/buscar."""

    if session.center_id is None:
        raise HTTPException(status_code=400, detail="La sesión no tiene centro asociado.")
    if desde and hasta and desde > hasta:
        raise HTTPException(status_code=422, detail="'desde' no puede ser posterior a 'hasta'.")

    filtros = [Verificacion.centro_id == session.center_id]
    if desde:
        filtros.append(
            EventLog.created_at
            >= datetime.datetime.combine(desde, datetime.time.min, tzinfo=ZONA_OAXACA)
        )
    if hasta:
        filtros.append(
            EventLog.created_at
            < datetime.datetime.combine(
                hasta + datetime.timedelta(days=1), datetime.time.min, tzinfo=ZONA_OAXACA
            )
        )
    if usuario_id:
        filtros.append(EventLog.usuario_id == usuario_id)
    if modulo and modulo.strip():
        filtros.append(EventLog.modulo == modulo.strip())
    if placa and placa.strip():
        filtros.append(Verificacion.placa.ilike(f"%{placa.strip()}%"))

    base = (
        select(EventLog, Verificacion.placa, CatUsuario.nombre_completo)
        .join(Verificacion, Verificacion.id == EventLog.verificacion_id)
        .outerjoin(CatUsuario, CatUsuario.id == EventLog.usuario_id)
        .where(*filtros)
    )
    total = await db.scalar(
        select(func.count())
        .select_from(EventLog)
        .join(Verificacion, Verificacion.id == EventLog.verificacion_id)
        .where(*filtros)
    )
    filas = await db.execute(
        base.order_by(EventLog.created_at.desc(), EventLog.id)
        .limit(limite)
        .offset(desplazamiento)
    )
    return AuditoriaPagina(
        total=total or 0,
        items=[
            AuditoriaRead(
                **EventLogRead.model_validate(ev).model_dump(),
                verificacion_id=ev.verificacion_id,
                placa=placa_exp,
                usuario_nombre=nombre,
            )
            for ev, placa_exp, nombre in filas.all()
        ],
    )


class SemestreRead(BaseModel):
    semestre_actual: int
    prorroga_activa: bool
    fecha_final_prorroga: datetime.date | None
    motivo_prorroga: str | None


@router.get("/semestre", response_model=SemestreRead)
async def consultar_semestre(
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> SemestreRead:
    """Pantalla 'Administración / Supervisión — Configuración de Semestre
    y prórroga' (sección 5 del handoff): `semestre_certificado` ("cálculo
    automático por fecha de verificación") y `prorroga_primer_periodo`
    ("Activa/Inactiva") — ambos se derivan aquí, no se guardan como
    estado aparte."""

    prorroga = await obtener_prorroga_activa(db)
    hoy = hoy_oaxaca()
    return SemestreRead(
        semestre_actual=calcular_semestre(hoy, prorroga.fecha_final if prorroga else None),
        prorroga_activa=prorroga is not None,
        fecha_final_prorroga=prorroga.fecha_final if prorroga else None,
        motivo_prorroga=prorroga.motivo if prorroga else None,
    )


class ProrrogaInput(BaseModel):
    fecha_final: datetime.date
    motivo: str


@router.post("/semestre/prorroga", response_model=SemestreRead)
async def configurar_prorroga(
    payload: ProrrogaInput,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> SemestreRead:
    """Solo un Supervisor autorizado puede definir la prórroga (sección 5:
    "debe auditarse motivo, fecha final, usuario y fecha/hora") — cada
    llamada crea una fila nueva (append-only, ver docstring de
    `ProrrogaSemestre`); no hay endpoint de "editar" una prórroga
    existente. Configurar `fecha_final` en el pasado es la forma de
    desactivar la prórroga vigente antes de tiempo."""

    if not payload.motivo.strip():
        raise HTTPException(status_code=422, detail="El motivo es obligatorio.")

    db.add(
        ProrrogaSemestre(
            fecha_final=payload.fecha_final,
            motivo=payload.motivo.strip(),
            usuario_id=session.user_id,
        )
    )
    await db.commit()

    prorroga = await obtener_prorroga_activa(db)
    hoy = hoy_oaxaca()
    return SemestreRead(
        semestre_actual=calcular_semestre(hoy, prorroga.fecha_final if prorroga else None),
        prorroga_activa=prorroga is not None,
        fecha_final_prorroga=prorroga.fecha_final if prorroga else None,
        motivo_prorroga=prorroga.motivo if prorroga else None,
    )


class IncidenciaRead(BaseModel):
    id: str
    tipo: str
    titulo: str
    origen: str
    expediente_id: uuid.UUID | None
    placa: str | None
    linea_id: int | None
    estado: str | None
    responsable: str | None
    ultimo_intento: datetime.datetime | None
    intentos: int
    mensaje_operativo: str
    mensaje_tecnico: str | None
    guia: str
    accion: str


# Fase 1 de la auditoría de Sebastián (2026-10-12, frame Figma #66:2950):
# solo los errores que hoy existen de verdad en el sistema. Ninguno vive en
# una tabla propia — se derivan del estado actual, así que "abierta" =
# "el expediente sigue en el estado de error" y se cierra sola al
# reintentar con éxito. SIOX caído no es incidencia: la regla es no
# bloquear (captura manual), y ERROR_INTEGRACION no lo asigna ningún
# endpoint. Equipo de prueba/OBD entran con el simulador de hardware.
_GUIAS = {
    "IMPRESION_FALLIDA": (
        "Impresión fallida con folio",
        "Impresión Central",
        "No se obtuvo un certificado físico válido. El folio sigue asignado al expediente "
        "y solo un Supervisor puede autorizar el reintento técnico.",
        "El reintento usa el mismo folio y el mismo trabajo de impresión: no pide folio nuevo "
        "ni cambia la Hora Salida. Si el papel se dañó, marque el folio como DAÑADO desde "
        "Impresión para que se asigne el siguiente.",
        "REINTENTAR_IMPRESION",
    ),
    "ERROR_INTEGRACION": (
        "Error del equipo de prueba",
        "Estación de Prueba",
        "El equipo de medición falló durante la prueba. No se generó resultado y el "
        "expediente espera el reintento.",
        "Revise el equipo (comunicación, calibración) y autorice el reintento desde la "
        "estación de Prueba: el expediente vuelve a la cola de su línea y se configura de nuevo.",
        "REINTENTAR_PRUEBA",
    ),
    "FOLIO_ERROR": (
        "Sin folio disponible",
        "Impresión Central",
        "No se pudo asignar folio al expediente. No se imprime certificado definitivo sin folio.",
        "Registre un lote de folios del tipo solicitado en Administración › Folios; después "
        "Impresión vuelve a solicitar el folio del expediente.",
        "REGISTRAR_LOTE",
    ),
    "SYNC_ERROR": (
        "Error de sincronización con el central",
        "Sincronización",
        "Un registro del expediente no se pudo enviar al servidor central. La operación local "
        "no se detiene; el registro queda en espera de reintento.",
        "Sincronizar ahora reintenta todos los pendientes en orden; el central deduplica por "
        "UUID, así que reintentar no duplica registros.",
        "SINCRONIZAR",
    ),
}


def _incidencia(tipo: str, **campos) -> IncidenciaRead:
    titulo, origen, operativo, guia, accion = _GUIAS[tipo]
    return IncidenciaRead(
        tipo=tipo,
        titulo=titulo,
        origen=origen,
        mensaje_operativo=operativo,
        guia=guia,
        accion=accion,
        **campos,
    )


@router.get("/incidencias", response_model=list[IncidenciaRead])
async def incidencias_centro(
    linea_id: int | None = None,
    origen: str | None = None,
    q: str | None = None,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> list[IncidenciaRead]:
    """Pestaña 'Errores y reintentos' (Figma #66:2950): incidencias abiertas
    del centro de la sesión, más reciente primero. Filtros: línea, origen
    (texto exacto de `origen`) y búsqueda libre por placa, expediente o
    mensaje."""

    if session.center_id is None:
        raise HTTPException(status_code=400, detail="La sesión no tiene centro asociado.")

    incidencias: list[IncidenciaRead] = []

    expedientes = (
        await db.execute(
            select(Verificacion).where(
                Verificacion.centro_id == session.center_id,
                Verificacion.estado.in_(
                    [
                        EstadoVerificacion.IMPRESION_FALLIDA,
                        EstadoVerificacion.FOLIO_ERROR,
                        EstadoVerificacion.ERROR_INTEGRACION,
                    ]
                ),
            )
        )
    ).scalars().all()
    for exp in expedientes:
        ultimo = (
            await db.execute(
                select(EventLog, CatUsuario.nombre_completo)
                .outerjoin(CatUsuario, CatUsuario.id == EventLog.usuario_id)
                .where(
                    EventLog.verificacion_id == exp.id,
                    EventLog.estado_nuevo == exp.estado,
                )
                .order_by(EventLog.created_at.desc())
                .limit(1)
            )
        ).first()
        evento, responsable = ultimo if ultimo else (None, None)
        detalle = (evento.detalle_json or {}) if evento else {}

        if exp.estado == EstadoVerificacion.ERROR_INTEGRACION:
            # El mismo estado lo usan SIOX y OBD; solo el error de equipo de
            # prueba es una incidencia de esta bandeja.
            if evento is None or evento.evento != "prueba_error_equipo":
                continue
            intentos = detalle.get("intento", 1)
            tecnico = " · ".join(
                x for x in (detalle.get("motivo"), detalle.get("mensaje_tecnico")) if x
            ) or None
        elif exp.estado == EstadoVerificacion.IMPRESION_FALLIDA:
            job = (
                await db.execute(select(PrintJob).where(PrintJob.verificacion_id == exp.id))
            ).scalars().first()
            intentos = job.intentos if job else detalle.get("intentos", 0)
            tecnico = " · ".join(
                x
                for x in (
                    "PRINT_FAILED",
                    f"folio={exp.folio_externo}" if exp.folio_externo else None,
                    job.error_message if job else None,
                )
                if x
            )
        else:
            intentos = 1
            tecnico = " · ".join(
                f"{k}={v}" for k, v in (("motivo", detalle.get("motivo")),
                                        ("tipo", detalle.get("tipo_certificado"))) if v
            ) or None

        incidencias.append(
            _incidencia(
                exp.estado.value,
                id=f"{exp.estado.value}:{exp.id}",
                expediente_id=exp.id,
                placa=exp.placa,
                linea_id=exp.linea_id,
                estado=exp.estado.value,
                responsable=responsable,
                ultimo_intento=evento.created_at if evento else exp.updated_at,
                intentos=intentos,
                mensaje_tecnico=tecnico,
            )
        )

    filas_sync = (
        await db.execute(select(SyncOutbox).where(SyncOutbox.sync_status == SyncStatus.ERROR))
    ).scalars().all()
    ids_sync = {
        fila.id: (
            fila.entity_uuid
            if fila.entity_type == "verificacion"
            else _uuid_o_none((fila.payload or {}).get("verificacion_id"))
        )
        for fila in filas_sync
    }
    exp_sync = {
        v.id: v
        for v in (
            await db.execute(
                select(Verificacion).where(
                    Verificacion.id.in_([x for x in ids_sync.values() if x]),
                    Verificacion.centro_id == session.center_id,
                )
            )
        ).scalars()
    }
    for fila in filas_sync:
        exp = exp_sync.get(ids_sync[fila.id])
        if exp is None:
            continue  # de otro centro (o sin expediente): no es de este supervisor
        respuesta = fila.server_response or {}
        incidencias.append(
            _incidencia(
                "SYNC_ERROR",
                id=f"SYNC_ERROR:{fila.id}",
                expediente_id=exp.id,
                placa=exp.placa,
                linea_id=exp.linea_id,
                estado=exp.estado.value,
                responsable=None,
                ultimo_intento=fila.last_attempt_at or fila.created_at,
                intentos=fila.attempts or 0,
                mensaje_tecnico=" · ".join(
                    x
                    for x in (
                        f"{fila.entity_type}.{fila.operation}",
                        str(respuesta.get("error") or respuesta.get("detail") or "") or None,
                    )
                    if x
                ),
            )
        )

    if linea_id is not None:
        incidencias = [i for i in incidencias if i.linea_id == linea_id]
    if origen:
        incidencias = [i for i in incidencias if i.origen == origen]
    if q and q.strip():
        texto = q.strip().lower()
        incidencias = [
            i
            for i in incidencias
            if texto in " ".join(
                str(x) for x in (i.placa, i.expediente_id, i.titulo, i.mensaje_operativo,
                                 i.mensaje_tecnico) if x
            ).lower()
        ]

    minimo = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    incidencias.sort(
        key=lambda i: i.ultimo_intento.replace(tzinfo=i.ultimo_intento.tzinfo or datetime.timezone.utc)
        if i.ultimo_intento
        else minimo,
        reverse=True,
    )
    return incidencias


def _uuid_o_none(valor) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(valor))
    except (TypeError, ValueError):
        return None
