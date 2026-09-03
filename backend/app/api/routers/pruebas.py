import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pydantic import ValidationError

from app.api.deps import (
    SessionContext,
    assert_linea_permitida,
    get_db,
    requiere_estacion,
    requiere_supervisor,
)
from app.models.enums import (
    EstadoVerificacion,
    FaseLectura,
    MetodoPrueba,
    ResultadoFinal,
    ResultadoPruebaEnum,
    StationType,
    TipoPrueba,
)
from app.models.event_log import EventLog
from app.models.limite_emision import LimiteEmision
from app.models.resultado_prueba import ResultadoPrueba
from app.models.vehiculo import Vehiculo
from app.models.verificacion import Verificacion
from app.schemas.prueba import (
    MetodoSinMapeo,
    NormalizedPayloadDiesel,
    NormalizedPayloadGasolina,
    metodo_de,
)
from app.schemas.verificacion import ExpedienteCompleto
from app.services import state_machine
from app.services.evaluacion_prueba import LimitesNoConfigurados, evaluar_diesel, evaluar_gasolina

router = APIRouter(prefix="/api/pruebas", tags=["pruebas"])


async def _obtener_expediente_de_la_linea(
    db: AsyncSession, session: SessionContext, expediente_id: uuid.UUID
) -> Verificacion:
    verificacion = await db.get(Verificacion, expediente_id)
    if verificacion is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    assert_linea_permitida(session, verificacion.centro_id, verificacion.linea_id)
    return verificacion


@router.get("/cola", response_model=list[ExpedienteCompleto])
async def cola_prueba(
    session: SessionContext = Depends(requiere_estacion(StationType.PRUEBA)),
    db: AsyncSession = Depends(get_db),
) -> list[Verificacion]:
    """La estación de Prueba solo ve expedientes de su línea (regla del
    modelo de estaciones). La línea sale de la sesión, nunca de la URL: antes
    una estación de línea 1 podía pedir la cola de la línea 2 cambiando
    /api/pruebas/cola/2 por la dirección.

    El número de línea es local a cada centro (ver docstring de
    `assert_linea_permitida`): sin filtrar también por `centro_id`, una
    estación de línea 1 del centro A vería expedientes de la línea 1 del
    centro B."""

    if session.line_id is None:
        raise HTTPException(status_code=400, detail="La sesión no tiene línea asociada.")

    result = await db.execute(
        select(Verificacion)
        .options(selectinload(Verificacion.vehiculo))
        .where(
            Verificacion.centro_id == session.center_id,
            Verificacion.linea_id == session.line_id,
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
    session: SessionContext = Depends(requiere_estacion(StationType.PRUEBA)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Regla de negocio #5/#9: gasolina -> dinámica por default, cambiable a
    estática con auditoría; diésel -> opacidad, sin cambio permitido."""

    verificacion = await _obtener_expediente_de_la_linea(db, session, expediente_id)

    if verificacion.estado != EstadoVerificacion.LISTO_PARA_PRUEBA:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No se puede configurar la prueba: el expediente está en "
                f"estado {verificacion.estado}, no LISTO_PARA_PRUEBA."
            ),
        )

    es_gasolina = (verificacion.combustible_validado or "").upper() == "GASOLINA"
    tipo_default = TipoPrueba.DINAMICA if es_gasolina else TipoPrueba.OPACIDAD

    if tipo_prueba != tipo_default:
        if not es_gasolina:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Un vehículo que no es a gasolina solo admite prueba de "
                    "OPACIDAD; no se permite cambiar el tipo de prueba."
                ),
            )
        if tipo_prueba != TipoPrueba.ESTATICA:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Un vehículo a gasolina solo puede cambiar de DINAMICA a "
                    f"ESTATICA, no a {tipo_prueba}."
                ),
            )
        if not cambio_manual or not motivo:
            raise HTTPException(
                status_code=409,
                detail="El cambio de dinámica a estática requiere cambio_manual=true y un motivo.",
            )

    verificacion.tipo_prueba_final = tipo_prueba
    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.PRUEBA_CONFIGURADA,
        usuario_id=session.user_id,
        modulo="prueba",
        evento="prueba_configurada",
        detalle={"tipo_prueba": tipo_prueba, "cambio_manual": cambio_manual},
    )

    if cambio_manual:
        # Cambio de gasolina dinámica a estática debe auditarse (regla #9).
        db.add(
            _cambio_tipo_prueba_event(verificacion.id, session.user_id, motivo, tipo_prueba)
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
    session: SessionContext = Depends(requiere_estacion(StationType.PRUEBA)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    verificacion = await _obtener_expediente_de_la_linea(db, session, expediente_id)

    if verificacion.estado != EstadoVerificacion.PRUEBA_CONFIGURADA:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No se puede iniciar la prueba: el expediente está en "
                f"estado {verificacion.estado}, no PRUEBA_CONFIGURADA."
            ),
        )

    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.PRUEBA_EN_PROCESO,
        usuario_id=session.user_id,
        modulo="prueba",
        evento="prueba_iniciada",
    )
    await db.commit()
    return {"estado_expediente": verificacion.estado}


class ResultadoPruebaInput(BaseModel):
    """'Certificate Result Projection Contract v1' (sección 4): el operador
    ya no elige `resultado` — lo calcula el servidor comparando
    `normalized_payload` contra `LimiteEmision` (ver
    app.services.evaluacion_prueba). El shape exacto de
    `normalized_payload` depende del método (ver app.schemas.prueba)."""

    normalized_payload: dict
    equipo_id: uuid.UUID | None = None


@router.post("/resultado/{expediente_id}")
async def guardar_resultado_prueba(
    expediente_id: uuid.UUID,
    payload: ResultadoPruebaInput,
    session: SessionContext = Depends(requiere_estacion(StationType.PRUEBA)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    verificacion = await _obtener_expediente_de_la_linea(db, session, expediente_id)

    if verificacion.estado != EstadoVerificacion.PRUEBA_EN_PROCESO:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No se puede guardar el resultado: el expediente está en "
                f"estado {verificacion.estado}, no PRUEBA_EN_PROCESO."
            ),
        )

    # HU-017: combustible es obligatorio; Captura lo garantiza al normalizar
    # (ver expedientes.normalizar_expediente), pero Prueba también lo
    # rechaza en vez de guardar un resultado con combustible vacío.
    if not verificacion.combustible_validado:
        raise HTTPException(
            status_code=409,
            detail="El expediente no tiene combustible validado.",
        )

    try:
        metodo = metodo_de(verificacion.tipo_prueba_final)
    except MetodoSinMapeo as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        vehiculo = await db.get(Vehiculo, verificacion.vehiculo_id)
        anio_modelo = vehiculo.modelo if vehiculo is not None else None
        if metodo == MetodoPrueba.DIESEL_OPACITY:
            peso_bruto_kg = vehiculo.peso_bruto_vehicular_kg if vehiculo is not None else None
            payload_validado = NormalizedPayloadDiesel.model_validate(payload.normalized_payload)
            resultado, limits_applied, excedidos = await evaluar_diesel(
                db, metodo, payload_validado, peso_bruto_kg
            )
        else:
            payload_validado = NormalizedPayloadGasolina.model_validate(payload.normalized_payload)
            resultado, limits_applied, excedidos = await evaluar_gasolina(
                db, metodo, payload_validado, anio_modelo
            )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except LimitesNoConfigurados as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    db.add(
        ResultadoPrueba(
            verificacion_id=verificacion.id,
            tipo_prueba=verificacion.tipo_prueba_final,
            combustible=verificacion.combustible_validado,
            resultado=resultado,
            valores_medidos_json=payload_validado.model_dump(),
            limites_aplicados_json=limits_applied,
            equipo_id=payload.equipo_id,
            linea_id=verificacion.linea_id,
            operador_id=session.user_id,
            started_at=datetime.datetime.now(datetime.timezone.utc),
            finished_at=datetime.datetime.now(datetime.timezone.utc),
        )
    )

    verificacion.resultado_final = (
        ResultadoFinal.APROBADO
        if resultado == ResultadoPruebaEnum.APROBADO
        else ResultadoFinal.RECHAZADO
    )

    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.PRUEBA_FINALIZADA,
        usuario_id=session.user_id,
        modulo="prueba",
        evento="resultado_prueba_guardado",
        detalle={"resultado": resultado, "causales": excedidos} if excedidos else {"resultado": resultado},
    )
    await state_machine.transition(
        db,
        verificacion,
        EstadoVerificacion.PENDIENTE_IMPRESION
        if verificacion.resultado_final == ResultadoFinal.APROBADO
        else EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO,
        usuario_id=session.user_id,
        modulo="prueba",
        evento="enviado_a_impresion",
    )
    await db.commit()
    return {"estado_expediente": verificacion.estado}


class LimiteEmisionInput(BaseModel):
    metodo: MetodoPrueba
    fase: FaseLectura | None = None
    parametro: str
    valor_maximo: float
    # NULL = sin acotar por ese lado (ver docstring de LimiteEmision).
    # anio_modelo_* solo tiene sentido para gasolina (NOM-041, por
    # año-modelo); peso_bruto_*_kg solo para diésel (NOM-045, por peso
    # bruto vehicular) — cada norma usa un solo eje, ver validación abajo.
    anio_modelo_desde: int | None = None
    anio_modelo_hasta: int | None = None
    peso_bruto_desde_kg: float | None = None
    peso_bruto_hasta_kg: float | None = None


@router.get("/limites-emision")
async def listar_limites_emision(
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> list[LimiteEmisionInput]:
    """Catálogo configurable que consume `app.services.evaluacion_prueba`.
    Los valores reales de NOM-041 (gasolina) ya están cargados (ver
    `app/seed_limites_nom041.py`); NOM-045 (diésel) sigue vacío a
    propósito (ver docstring de `LimiteEmision`)."""

    filas = (await db.execute(select(LimiteEmision))).scalars().all()
    return [
        LimiteEmisionInput(
            metodo=fila.metodo,
            fase=fila.fase,
            parametro=fila.parametro,
            valor_maximo=fila.valor_maximo,
            anio_modelo_desde=fila.anio_modelo_desde,
            anio_modelo_hasta=fila.anio_modelo_hasta,
            peso_bruto_desde_kg=fila.peso_bruto_desde_kg,
            peso_bruto_hasta_kg=fila.peso_bruto_hasta_kg,
        )
        for fila in filas
    ]


@router.post("/limites-emision")
async def cargar_limite_emision(
    payload: LimiteEmisionInput,
    session: SessionContext = Depends(requiere_supervisor),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Alta o actualización (upsert por
    metodo+fase+parametro+anio_modelo_desde+anio_modelo_hasta) de un límite
    de emisión. Exclusivo de Supervisor, mismo criterio que
    `POST /api/folios/lotes` — el rol de plataforma/Superadmin que el
    handoff describe para catálogos no existe todavía en este sistema."""

    if payload.metodo == MetodoPrueba.DIESEL_OPACITY and payload.fase is not None:
        raise HTTPException(
            status_code=422, detail="DIESEL_OPACITY no tiene fases; omitir `fase`."
        )
    if payload.metodo != MetodoPrueba.DIESEL_OPACITY and payload.fase is None:
        raise HTTPException(
            status_code=422, detail=f"{payload.metodo.value} requiere `fase` (RALENTI/CRUCERO)."
        )
    if (
        payload.anio_modelo_desde is not None
        and payload.anio_modelo_hasta is not None
        and payload.anio_modelo_desde > payload.anio_modelo_hasta
    ):
        raise HTTPException(
            status_code=422, detail="anio_modelo_desde no puede ser mayor que anio_modelo_hasta."
        )
    if (
        payload.peso_bruto_desde_kg is not None
        and payload.peso_bruto_hasta_kg is not None
        and payload.peso_bruto_desde_kg > payload.peso_bruto_hasta_kg
    ):
        raise HTTPException(
            status_code=422,
            detail="peso_bruto_desde_kg no puede ser mayor que peso_bruto_hasta_kg.",
        )
    # Cada norma estratifica por un solo eje (ver docstring de
    # LimiteEmision): NOM-041 gasolina por año-modelo, NOM-045 diésel por
    # peso bruto. Mezclar ambos en una fila sería un dato sin sentido.
    if payload.metodo == MetodoPrueba.DIESEL_OPACITY and (
        payload.anio_modelo_desde is not None or payload.anio_modelo_hasta is not None
    ):
        raise HTTPException(
            status_code=422,
            detail="DIESEL_OPACITY no estratifica por año-modelo; usar peso_bruto_desde_kg/hasta_kg.",
        )
    if payload.metodo != MetodoPrueba.DIESEL_OPACITY and (
        payload.peso_bruto_desde_kg is not None or payload.peso_bruto_hasta_kg is not None
    ):
        raise HTTPException(
            status_code=422,
            detail=f"{payload.metodo.value} no estratifica por peso bruto; usar anio_modelo_desde/hasta.",
        )

    existente = (
        await db.execute(
            select(LimiteEmision).where(
                LimiteEmision.metodo == payload.metodo,
                LimiteEmision.fase == payload.fase,
                LimiteEmision.parametro == payload.parametro,
                LimiteEmision.anio_modelo_desde == payload.anio_modelo_desde,
                LimiteEmision.anio_modelo_hasta == payload.anio_modelo_hasta,
                LimiteEmision.peso_bruto_desde_kg == payload.peso_bruto_desde_kg,
                LimiteEmision.peso_bruto_hasta_kg == payload.peso_bruto_hasta_kg,
            )
        )
    ).scalars().first()

    if existente is not None:
        existente.valor_maximo = payload.valor_maximo
        db.add(existente)
    else:
        db.add(
            LimiteEmision(
                metodo=payload.metodo,
                fase=payload.fase,
                parametro=payload.parametro,
                valor_maximo=payload.valor_maximo,
                anio_modelo_desde=payload.anio_modelo_desde,
                anio_modelo_hasta=payload.anio_modelo_hasta,
                peso_bruto_desde_kg=payload.peso_bruto_desde_kg,
                peso_bruto_hasta_kg=payload.peso_bruto_hasta_kg,
            )
        )

    await db.commit()
    return {
        "metodo": payload.metodo,
        "fase": payload.fase,
        "parametro": payload.parametro,
        "anio_modelo_desde": payload.anio_modelo_desde,
        "anio_modelo_hasta": payload.anio_modelo_hasta,
        "peso_bruto_desde_kg": payload.peso_bruto_desde_kg,
        "peso_bruto_hasta_kg": payload.peso_bruto_hasta_kg,
    }
