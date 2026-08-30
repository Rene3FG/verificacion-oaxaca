import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionContext, assert_linea_permitida, get_db, requiere_estacion
from app.models.enums import (
    EstadoVerificacion,
    ResultadoInspeccionVisual,
    ResultadoItemInspeccion,
    StationType,
)
from app.models.inspeccion_visual import InspeccionVisual
from app.models.verificacion import Verificacion
from app.services import state_machine
from app.services.inspeccion_visual import (
    CHECKLIST_INSPECCION_VISUAL,
    ChecklistInvalido,
    evaluar_checklist,
)

router = APIRouter(prefix="/api/inspeccion", tags=["inspeccion"])


class InspeccionVisualCreate(BaseModel):
    """Sección 8 del handoff (revisión Figma 2026-08-24): el operador captura
    el resultado por punto (Bueno/Malo/No aplica); el resultado global
    APROBADA/RECHAZADA ya NO viene del cliente — lo determina el backend
    (cualquier punto MALO rechaza) y las causales son esos mismos puntos.
    `observaciones` es texto libre opcional, se conserva junto a las
    causales solo cuando hay rechazo."""

    checklist: dict[str, ResultadoItemInspeccion]
    observaciones: str | None = None


@router.get("/checklist")
async def catalogo_checklist(
    session: SessionContext = Depends(requiere_estacion(StationType.PRUEBA)),
) -> list[dict]:
    """Catálogo de los 8 puntos reales del checklist — el frontend lo
    renderiza desde aquí en vez de duplicar claves/etiquetas."""

    return [
        {"clave": clave, "etiqueta": etiqueta}
        for clave, etiqueta in CHECKLIST_INSPECCION_VISUAL.items()
    ]


@router.post("/{expediente_id}")
async def registrar_inspeccion(
    expediente_id: uuid.UUID,
    payload: InspeccionVisualCreate,
    session: SessionContext = Depends(requiere_estacion(StationType.PRUEBA)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    assert_linea_permitida(session, verificacion.centro_id, verificacion.linea_id)

    # Mismo patrón que pruebas.py/obd.py (2026-08-24): sin este guard, la
    # transición inválida tiraba TransitionNotAllowed sin manejar (500).
    if verificacion.estado != EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede registrar inspección visual en estado {verificacion.estado}",
        )

    try:
        resultado, causales = evaluar_checklist(payload.checklist)
    except ChecklistInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    causales_json = None
    if resultado == ResultadoInspeccionVisual.RECHAZADA:
        causales_json = {"items": causales}
        if payload.observaciones:
            causales_json["observaciones"] = payload.observaciones

    db.add(
        InspeccionVisual(
            verificacion_id=verificacion.id,
            resultado=resultado,
            checklist_json={clave: valor.value for clave, valor in payload.checklist.items()},
            causales_rechazo=causales_json,
            operador_id=session.user_id,
        )
    )

    nuevo_estado = (
        EstadoVerificacion.INSPECCION_VISUAL_APROBADA
        if resultado == ResultadoInspeccionVisual.APROBADA
        else EstadoVerificacion.INSPECCION_VISUAL_RECHAZADA
    )
    await state_machine.transition(
        db,
        verificacion,
        nuevo_estado,
        usuario_id=session.user_id,
        modulo="visual",
        evento="inspeccion_visual_registrada",
        detalle={"resultado": resultado, "causales": sorted(causales)},
    )

    if nuevo_estado == EstadoVerificacion.INSPECCION_VISUAL_RECHAZADA:
        # Regla de negocio #3: rechazo salta directo a Impresión Central,
        # a su propia cola (PENDIENTE_DE_IMPRESION_RECHAZO).
        await state_machine.transition(
            db,
            verificacion,
            EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO,
            usuario_id=session.user_id,
            modulo="visual",
            evento="rechazo_enviado_a_impresion",
        )

    await db.commit()
    return {
        "estado_expediente": verificacion.estado,
        "resultado": resultado,
        "causales_rechazo": causales,
    }
