from sqlalchemy import select

from app.models.enums import (
    EstadoPrintJob,
    EstadoVerificacion,
    ResultadoFinal,
    ResultadoInspeccionVisual,
    StationType,
)
from app.models.inspeccion_visual import InspeccionVisual
from app.models.print_attempt import PrintAttempt
from app.models.print_job import PrintJob
from tests.conftest import (
    crear_estacion,
    crear_expediente,
    crear_sesion_activa,
    crear_sesion_supervisor,
)


async def _sesion_impresion(db_session, *, allowed_line_ids=None):
    estacion = await crear_estacion(
        db_session,
        station_type=StationType.IMPRESION,
        center_id="OAX-01",
        line_id=None,
        is_centralized=True,
        allowed_line_ids=allowed_line_ids or [1],
    )
    return await crear_sesion_activa(db_session, estacion=estacion)


async def test_tipo_certificado_aprobado_requiere_seleccion_manual(client, db_session):
    """Handoff (confirmado 2026-08-24): no hay regla automática de
    elegibilidad para Particular/Doble Cero/Intensivo; sin que el Operador
    mande `tipo_certificado`, un aprobado no puede resolverse solo."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    db_session.add(expediente)
    await db_session.commit()

    resp = await client.post(
        f"/api/impresion/tipo-certificado/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 422


async def test_tipo_certificado_aprobado_con_seleccion_manual(client, db_session):
    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    db_session.add(expediente)
    await db_session.commit()

    resp = await client.post(
        f"/api/impresion/tipo-certificado/{expediente.id}",
        params={"tipo_certificado": "INTENSIVO"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["certificado_tipo"] == "INTENSIVO"


async def test_tipo_certificado_no_permite_rechazo_manual_en_aprobado(client, db_session):
    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    db_session.add(expediente)
    await db_session.commit()

    resp = await client.post(
        f"/api/impresion/tipo-certificado/{expediente.id}",
        params={"tipo_certificado": "RECHAZO"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 422


async def test_tipo_certificado_rechazo_prueba_se_infiere_solo(client, db_session):
    """RECHAZO es el único tipo posible en este camino — no requiere
    selección manual, y una selección manual distinta se ignora."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    expediente.resultado_final = ResultadoFinal.RECHAZADO
    db_session.add(expediente)
    await db_session.commit()

    resp = await client.post(
        f"/api/impresion/tipo-certificado/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["certificado_tipo"] == "RECHAZO"


async def test_tipo_certificado_rechazo_visual_sin_resultado_final(client, db_session):
    """Regla de negocio #3: el rechazo en Inspección Visual salta Prueba
    directo a Impresión, así que resultado_final nunca se llena para este
    camino — el tipo de certificado se infiere de InspeccionVisual."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    db_session.add(
        InspeccionVisual(
            verificacion_id=expediente.id,
            resultado=ResultadoInspeccionVisual.RECHAZADA,
            checklist_json={"luces": "mal"},
        )
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/impresion/tipo-certificado/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["certificado_tipo"] == "RECHAZO"


async def test_tipo_certificado_indeterminado_responde_409(client, db_session):
    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/impresion/tipo-certificado/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 409


async def test_vista_previa_sin_tipo_certificado_responde_409(client, db_session):
    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ASIGNADO
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    expediente.folio_externo = "F-0001"
    db_session.add(expediente)
    await db_session.commit()

    resp = await client.get(
        f"/api/impresion/vista-previa/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409


async def test_vista_previa_devuelve_pdf(client, db_session):
    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.FOLIO_ASIGNADO,
        combustible="GASOLINA",
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    expediente.folio_externo = "F-0001"
    expediente.certificado_tipo = "PARTICULAR"
    db_session.add(expediente)
    await db_session.commit()

    resp = await client.get(
        f"/api/impresion/vista-previa/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")

    # La vista previa no debe tocar estado ni el certificado_tipo ya fijado.
    await db_session.refresh(expediente)
    assert expediente.certificado_tipo == "PARTICULAR"
    assert expediente.estado == EstadoVerificacion.FOLIO_ASIGNADO


async def test_imprimir_sin_folio_responde_409(client, db_session):
    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ASIGNADO
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 409


async def test_imprimir_sin_tipo_certificado_responde_409(client, db_session):
    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ASIGNADO
    )
    expediente.folio_externo = "F-0001"
    db_session.add(expediente)
    await db_session.commit()

    resp = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409


async def test_imprimir_con_datos_obligatorios_faltantes_responde_409(client, db_session):
    """Sección 7 del handoff: propietario/domicilio, tarjeta de circulación,
    PBV y Tracción son opcionales al capturar pero obligatorios al imprimir
    (`app.services.certificado.campos_obligatorios_faltantes`)."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.FOLIO_ASIGNADO,
        datos_certificado_completos=False,
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    expediente.folio_externo = "F-0001"
    expediente.certificado_tipo = "PARTICULAR"
    db_session.add(expediente)
    await db_session.commit()

    resp = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 409
    detalle = resp.json()["detail"]
    assert "Tracción" in detalle
    assert "Peso bruto vehicular" in detalle
    assert "tarjeta de circulación" in detalle


async def test_imprimir_exitoso_crea_print_job_y_transiciona_a_impreso(client, db_session):
    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ASIGNADO
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    expediente.folio_externo = "F-0001"
    expediente.certificado_tipo = "PARTICULAR"
    db_session.add(expediente)
    await db_session.commit()

    resp = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["estado_expediente"] == EstadoVerificacion.IMPRESO.value
    assert resp.json()["intentos"] == 1

    print_job = (
        await db_session.execute(
            select(PrintJob).where(PrintJob.verificacion_id == expediente.id)
        )
    ).scalars().one()
    assert print_job.estado == EstadoPrintJob.IMPRESO
    assert print_job.tipo_documento == "PARTICULAR"

    await db_session.refresh(expediente)
    assert expediente.certificado_tipo == "PARTICULAR"
    # Regla 2 del frame "Cierre y reimpresión": el primer intento exitoso
    # fija hora_salida.
    assert expediente.hora_salida is not None


async def test_reintento_impresion_tras_fallo_no_pide_folio_nuevo(
    client, db_session, monkeypatch
):
    """HU-072 a HU-079: la impresora falla la primera vez (IMPRESION_FALLIDA),
    y el reintento (sección 3 del handoff: exclusivo de Supervisor, es un
    "reintento técnico") debe reusar folio_externo e imprimir con éxito,
    dejando un único PrintJob con 2 intentos."""

    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ASIGNADO
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    expediente.folio_externo = "F-0001"
    expediente.certificado_tipo = "PARTICULAR"
    db_session.add(expediente)
    await db_session.commit()

    resultados = iter([False, True])

    async def _impresora_falla_luego_exitosa(pdf_bytes: bytes) -> bool:
        return next(resultados)

    monkeypatch.setattr(
        "app.api.routers.impresion.imprimir_en_impresora", _impresora_falla_luego_exitosa
    )

    resp1 = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp1.status_code == 200
    assert resp1.json()["estado_expediente"] == EstadoVerificacion.IMPRESION_FALLIDA.value

    await db_session.refresh(expediente)
    # Regla 2 del frame "Cierre y reimpresión", supuesto elegido (pendiente
    # de confirmar con el cliente, ver CLAUDE.md): un intento fallido NO
    # cuenta como "primer clic" — hora_salida sigue nula hasta que un
    # intento tenga éxito de verdad.
    assert expediente.hora_salida is None

    resp2 = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp2.status_code == 200
    assert resp2.json()["estado_expediente"] == EstadoVerificacion.IMPRESO.value
    assert resp2.json()["intentos"] == 2

    await db_session.refresh(expediente)
    assert expediente.folio_externo == "F-0001"
    # El segundo intento (el primero EXITOSO) es el que fija hora_salida.
    assert expediente.hora_salida is not None

    print_jobs = (
        await db_session.execute(
            select(PrintJob).where(PrintJob.verificacion_id == expediente.id)
        )
    ).scalars().all()
    assert len(print_jobs) == 1
    assert print_jobs[0].intentos == 2
    assert print_jobs[0].estado == EstadoPrintJob.IMPRESO

    # Etapa 12: cada intento es su propia fila inmutable (idempotente bajo
    # reenvío de sync), no un contador mutado.
    intentos_registrados = (
        await db_session.execute(
            select(PrintAttempt)
            .where(PrintAttempt.print_job_id == print_jobs[0].id)
            .order_by(PrintAttempt.created_at)
        )
    ).scalars().all()
    assert len(intentos_registrados) == 2
    assert intentos_registrados[0].exitoso is False
    assert intentos_registrados[0].error_message == "La impresora no respondió."
    assert intentos_registrados[1].exitoso is True
    assert intentos_registrados[1].error_message is None


async def test_reintento_impresion_tras_fallo_sin_supervisor_responde_403(
    client, db_session, monkeypatch
):
    """Sección 3 del handoff: 'Reintento técnico posterior al primer
    Imprimir ... SOLO Supervisor puede ejecutarlo' — un operador de
    Impresión normal no puede reintentar tras una falla."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ASIGNADO
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    expediente.folio_externo = "F-0001"
    expediente.certificado_tipo = "PARTICULAR"
    db_session.add(expediente)
    await db_session.commit()

    async def _impresora_falla(pdf_bytes: bytes) -> bool:
        return False

    monkeypatch.setattr("app.api.routers.impresion.imprimir_en_impresora", _impresora_falla)

    resp1 = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp1.json()["estado_expediente"] == EstadoVerificacion.IMPRESION_FALLIDA.value

    resp2 = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp2.status_code == 403

    await db_session.refresh(expediente)
    assert expediente.folio_externo == "F-0001"

    print_jobs = (
        await db_session.execute(
            select(PrintJob).where(PrintJob.verificacion_id == expediente.id)
        )
    ).scalars().all()
    assert len(print_jobs) == 1
    assert print_jobs[0].intentos == 1
    assert print_jobs[0].estado == EstadoPrintJob.ERROR


async def test_cerrar_expediente_sin_condiciones_responde_409(client, db_session):
    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ASIGNADO
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/impresion/cerrar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 409
    assert "IMPRESO" in resp.json()["detail"] or "estado" in resp.json()["detail"]


async def test_cerrar_expediente_exitoso_tras_imprimir(client, db_session):
    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ASIGNADO
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    expediente.folio_externo = "F-0001"
    expediente.certificado_tipo = "PARTICULAR"
    db_session.add(expediente)
    await db_session.commit()

    resp_imprimir = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_imprimir.json()["estado_expediente"] == EstadoVerificacion.IMPRESO.value

    await db_session.refresh(expediente)
    hora_salida = expediente.hora_salida
    assert hora_salida is not None

    resp_cerrar = await client.post(
        f"/api/impresion/cerrar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_cerrar.status_code == 200
    assert resp_cerrar.json()["estado_expediente"] == EstadoVerificacion.CERRADO_APROBADO.value

    await db_session.refresh(expediente)
    # Regla 2 del frame "Cierre y reimpresión": el cierre no toca hora_salida.
    assert expediente.hora_salida == hora_salida

    resp_doble_cierre = await client.post(
        f"/api/impresion/cerrar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_doble_cierre.status_code == 409


async def test_cerrar_expediente_con_certificado_rechazo_llega_a_cerrado_rechazado(
    client, db_session
):
    """Revisión Figma 2026-08-24, sección 14 punto 3: el cierre de un
    certificado_tipo RECHAZO va a CERRADO_RECHAZADO, no CERRADO_APROBADO."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ASIGNADO
    )
    expediente.resultado_final = ResultadoFinal.RECHAZADO
    expediente.folio_externo = "F-0002"
    expediente.certificado_tipo = "RECHAZO"
    db_session.add(expediente)
    await db_session.commit()

    resp_imprimir = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_imprimir.json()["estado_expediente"] == EstadoVerificacion.IMPRESO.value

    resp_cerrar = await client.post(
        f"/api/impresion/cerrar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_cerrar.status_code == 200
    assert resp_cerrar.json()["estado_expediente"] == EstadoVerificacion.CERRADO_RECHAZADO.value
