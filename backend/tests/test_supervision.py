from app.models.enums import EstadoVerificacion, StationType
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa, crear_sesion_supervisor


async def test_monitor_sin_supervisor_responde_403(client, db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.get("/api/supervision/monitor", headers={"X-Session-Id": str(sesion.id)})
    assert resp.status_code == 403


async def test_monitor_incluye_todas_las_lineas_del_centro(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.CREADO
    )
    await crear_expediente(
        db_session, linea_id=2, centro_id="OAX-01", estado=EstadoVerificacion.LISTO_PARA_PRUEBA
    )
    await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-02", estado=EstadoVerificacion.CREADO
    )
    await db_session.commit()

    resp = await client.get("/api/supervision/monitor", headers={"X-Session-Id": str(sesion.id)})

    assert resp.status_code == 200
    body = resp.json()
    assert {e["linea_id"] for e in body} == {1, 2}
    assert all(e["centro_id"] == "OAX-01" for e in body)


async def test_monitor_excluye_cerrados_y_cancelados(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    activo = await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.CREADO
    )
    await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.CERRADO_APROBADO
    )
    await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.CERRADO_RECHAZADO
    )
    await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.CANCELADO
    )
    await db_session.commit()

    resp = await client.get("/api/supervision/monitor", headers={"X-Session-Id": str(sesion.id)})

    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    assert ids == {str(activo.id)}


async def test_bitacora_expediente_orden_cronologico(client, db_session):
    sesion_captura = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    estacion_captura = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1
    )
    sesion_operador = await crear_sesion_activa(db_session, estacion=estacion_captura)
    expediente = await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.CREADO
    )
    await db_session.commit()

    await client.post(
        f"/api/siox/captura-manual/{expediente.id}",
        headers={"X-Session-Id": str(sesion_operador.id)},
    )

    resp = await client.get(
        f"/api/supervision/expedientes/{expediente.id}/bitacora",
        headers={"X-Session-Id": str(sesion_captura.id)},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    assert body[0]["evento"] == "captura_manual"
    fechas = [e["created_at"] for e in body]
    assert fechas == sorted(fechas)


async def test_bitacora_de_otro_centro_responde_403(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    expediente_ajeno = await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-02", estado=EstadoVerificacion.CREADO
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/supervision/expedientes/{expediente_ajeno.id}/bitacora",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 403
