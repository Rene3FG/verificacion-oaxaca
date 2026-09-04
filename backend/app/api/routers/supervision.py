import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import SessionContext, get_db, requiere_supervisor
from app.models.enums import EstadoVerificacion
from app.models.event_log import EventLog
from app.models.prorroga_semestre import ProrrogaSemestre
from app.models.verificacion import Verificacion
from app.schemas.event_log import EventLogRead
from app.schemas.verificacion import ExpedienteCompleto, ExpedienteRead
from app.services.proyeccion_certificado import calcular_semestre
from app.services.semestre import obtener_prorroga_activa

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
    hoy = datetime.datetime.now(datetime.timezone.utc).date()
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
    hoy = datetime.datetime.now(datetime.timezone.utc).date()
    return SemestreRead(
        semestre_actual=calcular_semestre(hoy, prorroga.fecha_final if prorroga else None),
        prorroga_activa=prorroga is not None,
        fecha_final_prorroga=prorroga.fecha_final if prorroga else None,
        motivo_prorroga=prorroga.motivo if prorroga else None,
    )
