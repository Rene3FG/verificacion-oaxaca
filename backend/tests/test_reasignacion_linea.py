from app.models.enums import EstadoVerificacion, ResultadoFinal, StationType
from app.models.event_log import EventLog
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa, crear_sesion_supervisor


async def test_reasignar_linea_sin_supervisor_responde_403(client, db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    expediente = await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.LISTO_PARA_PRUEBA
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/expedientes/{expediente.id}/reasignar-linea",
        json={"nueva_linea_id": 2, "motivo": "línea 1 saturada"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 403


async def test_reasignar_linea_exitosa(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    expediente = await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.LISTO_PARA_PRUEBA
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/expedientes/{expediente.id}/reasignar-linea",
        json={"nueva_linea_id": 2, "motivo": "línea 1 saturada"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["linea_id"] == 2

    evento = (
        await db_session.execute(
            EventLog.__table__.select().where(
                EventLog.verificacion_id == expediente.id,
                EventLog.evento == "linea_reasignada",
            )
        )
    ).mappings().one()
    assert evento["detalle_json"]["linea_anterior"] == 1
    assert evento["detalle_json"]["linea_nueva"] == 2
    assert evento["detalle_json"]["motivo"] == "línea 1 saturada"


async def test_reasignar_linea_sin_motivo_responde_422(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    expediente = await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.LISTO_PARA_PRUEBA
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/expedientes/{expediente.id}/reasignar-linea",
        json={"nueva_linea_id": 2, "motivo": ""},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 422


async def test_reasignar_linea_con_resultado_final_responde_409(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    expediente = await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    db_session.add(expediente)
    await db_session.commit()

    resp = await client.post(
        f"/api/expedientes/{expediente.id}/reasignar-linea",
        json={"nueva_linea_id": 2, "motivo": "cambio de línea"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 409


async def test_reasignar_linea_con_folio_asignado_responde_409(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    expediente = await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.FOLIO_ASIGNADO
    )
    expediente.folio_externo = "F-0001"
    db_session.add(expediente)
    await db_session.commit()

    resp = await client.post(
        f"/api/expedientes/{expediente.id}/reasignar-linea",
        json={"nueva_linea_id": 2, "motivo": "cambio de línea"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 409


async def test_reasignar_linea_de_otro_centro_responde_403(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    expediente_ajeno = await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-02", estado=EstadoVerificacion.LISTO_PARA_PRUEBA
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/expedientes/{expediente_ajeno.id}/reasignar-linea",
        json={"nueva_linea_id": 2, "motivo": "cambio de línea"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 403
