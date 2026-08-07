from app.models.enums import EstadoVerificacion, StationType
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa


async def _sesion(db_session, *, station_type: StationType, line_id: int | None = 1, **kw):
    estacion = await crear_estacion(
        db_session, station_type=station_type, center_id="OAX-01", line_id=line_id, **kw
    )
    return await crear_sesion_activa(db_session, estacion=estacion)


async def test_pruebas_configurar_desde_captura_responde_403(client, db_session):
    sesion = await _sesion(db_session, station_type=StationType.CAPTURA)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.LISTO_PARA_PRUEBA
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/pruebas/configurar/{expediente.id}?tipo_prueba=DINAMICA",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_impresion_imprimir_desde_prueba_responde_403(client, db_session):
    sesion = await _sesion(db_session, station_type=StationType.PRUEBA)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        params={"print_job_id": "00000000-0000-0000-0000-000000000099"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_impresion_cola_desde_captura_responde_403(client, db_session):
    sesion = await _sesion(
        db_session,
        station_type=StationType.CAPTURA,
        line_id=None,
        is_centralized=True,
        allowed_line_ids=[1],
    )
    await db_session.commit()

    resp = await client.get(
        "/api/impresion/cola", headers={"X-Session-Id": str(sesion.id)}
    )
    assert resp.status_code == 403


async def test_folios_solicitar_desde_captura_responde_403(client, db_session):
    sesion = await _sesion(db_session, station_type=StationType.CAPTURA)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "APROBADO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_folios_solicitar_desde_impresion_no_es_403(client, db_session):
    """Confirma que el guard no bloquea a la estación correcta; el sistema
    externo de folios sigue siendo un stub que responde error, pero eso es
    un 200 con status de error, no un 403 de permisos."""

    sesion = await _sesion(
        db_session,
        station_type=StationType.IMPRESION,
        line_id=None,
        is_centralized=True,
        allowed_line_ids=[1],
    )
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "APROBADO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
