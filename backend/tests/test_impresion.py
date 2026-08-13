from sqlalchemy import select

from app.models.enums import (
    EstadoPrintJob,
    EstadoVerificacion,
    ResultadoFinal,
    ResultadoInspeccionVisual,
    StationType,
)
from app.models.inspeccion_visual import InspeccionVisual
from app.models.print_job import PrintJob
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa


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


async def test_tipo_certificado_aprobacion(client, db_session):
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

    assert resp.status_code == 200
    assert resp.json()["certificado_tipo"] == "APROBACION"


async def test_tipo_certificado_rechazo_prueba(client, db_session):
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
    assert resp.json()["certificado_tipo"] == "RECHAZO_PRUEBA"


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
    assert resp.json()["certificado_tipo"] == "RECHAZO_VISUAL"


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
    db_session.add(expediente)
    await db_session.commit()

    resp = await client.get(
        f"/api/impresion/vista-previa/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")

    # La vista previa no debe tocar estado ni persistir certificado_tipo.
    await db_session.refresh(expediente)
    assert expediente.certificado_tipo is None
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


async def test_imprimir_exitoso_crea_print_job_y_transiciona_a_impreso(client, db_session):
    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ASIGNADO
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    expediente.folio_externo = "F-0001"
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
    assert print_job.tipo_documento == "APROBACION"

    await db_session.refresh(expediente)
    assert expediente.certificado_tipo == "APROBACION"


async def test_reintento_impresion_tras_fallo_no_pide_folio_nuevo(
    client, db_session, monkeypatch
):
    """HU-072 a HU-079: la impresora falla la primera vez (IMPRESION_FALLIDA),
    y el reintento debe reusar folio_externo e imprimir con éxito, dejando
    un único PrintJob con 2 intentos."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ASIGNADO
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    expediente.folio_externo = "F-0001"
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

    resp2 = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp2.status_code == 200
    assert resp2.json()["estado_expediente"] == EstadoVerificacion.IMPRESO.value
    assert resp2.json()["intentos"] == 2

    await db_session.refresh(expediente)
    assert expediente.folio_externo == "F-0001"

    print_jobs = (
        await db_session.execute(
            select(PrintJob).where(PrintJob.verificacion_id == expediente.id)
        )
    ).scalars().all()
    assert len(print_jobs) == 1
    assert print_jobs[0].intentos == 2
    assert print_jobs[0].estado == EstadoPrintJob.IMPRESO


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
    assert resp_cerrar.json()["estado_expediente"] == EstadoVerificacion.CERRADO.value

    resp_doble_cierre = await client.post(
        f"/api/impresion/cerrar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_doble_cierre.status_code == 409
