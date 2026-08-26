import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionContext, assert_linea_permitida, get_db, requiere_estacion, requiere_supervisor
from app.models.enums import EstadoFolio, EstadoVerificacion, StationType, TipoCertificado
from app.models.folio import Folio
from app.models.verificacion import Verificacion
from app.services import state_machine
from app.services.folio_inventario import RangoDeFolioInvalido, SinFolioDisponible, asignar_siguiente_folio, registrar_lote

router = APIRouter(prefix="/api/folios", tags=["folios"])

# Estados desde los que state_machine permite entrar a FOLIO_SOLICITADO (ver
# ALLOWED_TRANSITIONS). Pedir un folio fuera de estos estados —p.ej. un
# segundo tipo de certificado mientras ya hay uno FOLIO_ASIGNADO— antes
# tiraba un TransitionNotAllowed sin manejar (500); ahora es un 409 claro.
ESTADOS_SOLICITABLES = {
    EstadoVerificacion.PENDIENTE_IMPRESION,
    EstadoVerificacion.FOLIO_ERROR,
}


@router.post("/lotes")
async def registrar_lote_folios(
    tipo_certificado: TipoCertificado,
    folio_inicio: str,
    folio_fin: str,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Alta masiva por rango (Developer Handoff regla crítica #6: el
    Superadmin registra folios por lote; ese rol de plataforma no existe
    todavía en este sistema — se protege con `requiere_supervisor` como
    aproximación temporal, ver CLAUDE.md)."""

    try:
        lote, folios_str = await registrar_lote(
            db,
            tipo_certificado=tipo_certificado,
            folio_inicio=folio_inicio,
            folio_fin=folio_fin,
            registrado_por=session.user_id,
        )
    except RangoDeFolioInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await db.commit()
    return {"lote_id": str(lote.id), "tipo_certificado": tipo_certificado.value, "cantidad": len(folios_str)}


@router.get("/inventario")
async def inventario_folios(
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Conteo de folios por tipo y estatus, para la pantalla de
    Administración/Supervisión (handoff: 'error Sin folio disponible
    significa que la lista local de ese tipo se agotó')."""

    filas = (
        await db.execute(
            select(Folio.tipo_certificado, Folio.estatus, func.count())
            .group_by(Folio.tipo_certificado, Folio.estatus)
        )
    ).all()

    resumen: dict[str, dict[str, int]] = {tipo.value: {} for tipo in TipoCertificado}
    for tipo_certificado, estatus, cantidad in filas:
        resumen[tipo_certificado.value][estatus.value] = cantidad

    return [
        {
            "tipo_certificado": tipo,
            "disponibles": conteos.get(EstadoFolio.DISPONIBLE.value, 0),
            "asignados": conteos.get(EstadoFolio.ASIGNADO.value, 0),
            "impresos": conteos.get(EstadoFolio.IMPRESO.value, 0),
            "danados": conteos.get(EstadoFolio.DANADO.value, 0),
            "invalidados": conteos.get(EstadoFolio.INVALIDADO.value, 0),
        }
        for tipo, conteos in resumen.items()
    ]


@router.post("/solicitar/{expediente_id}")
async def solicitar_folio(
    expediente_id: uuid.UUID,
    tipo_certificado: TipoCertificado,
    session: SessionContext = Depends(requiere_estacion(StationType.IMPRESION)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Regla crítica #6 del handoff: los folios NO vienen de un sistema
    externo — este backend ES el inventario. Idempotente (regla #12): un
    expediente reutiliza cualquier folio ya asignado/impreso del mismo tipo
    en vez de tomar uno nuevo del inventario en cada reintento."""

    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    assert_linea_permitida(session, verificacion.centro_id, verificacion.linea_id)

    folio_existente = (
        await db.execute(
            select(Folio).where(
                Folio.verificacion_id == expediente_id,
                Folio.tipo_certificado == tipo_certificado,
                Folio.estatus.in_([EstadoFolio.ASIGNADO, EstadoFolio.IMPRESO]),
            )
        )
    ).scalars().first()

    if folio_existente is None and verificacion.estado not in ESTADOS_SOLICITABLES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No se puede solicitar folio '{tipo_certificado.value}' con el "
                f"expediente en estado {verificacion.estado}."
            ),
        )

    if folio_existente is not None:
        return {
            "folio": folio_existente.folio,
            "estado_expediente": verificacion.estado,
        }

    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.FOLIO_SOLICITADO,
        usuario_id=session.user_id,
        modulo="folios",
        evento="folio_solicitado",
        detalle={"tipo_certificado": tipo_certificado.value},
    )

    try:
        folio = await asignar_siguiente_folio(db, tipo_certificado, expediente_id)
    except SinFolioDisponible as exc:
        await state_machine.transition(
            db,
            verificacion,
            EstadoVerificacion.FOLIO_ERROR,
            usuario_id=session.user_id,
            modulo="folios",
            evento="folio_error",
            detalle={"motivo": "sin_folio_disponible", "tipo_certificado": tipo_certificado.value},
        )
        await db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    verificacion.folio_externo = folio.folio
    verificacion.folio_asignado_at = folio.asignado_at
    db.add(verificacion)

    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.FOLIO_ASIGNADO,
        usuario_id=session.user_id,
        modulo="folios",
        evento="folio_asignado",
        detalle={"folio": folio.folio, "tipo_certificado": tipo_certificado.value},
    )

    await db.commit()
    return {"folio": folio.folio, "estado_expediente": verificacion.estado}
