from sqlalchemy import select

from app.models.resultado_obd_sbd import ResultadoObdSbd
from app.models.enums import EstadoVerificacion, StationType
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa


async def _sesion_prueba(db_session, *, line_id: int = 1):
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=line_id
    )
    return await crear_sesion_activa(db_session, estacion=estacion)


async def test_evaluar_obd_lee_datos_del_vehiculo_y_escribe_combustible_validado(
    client, db_session
):
    """El endpoint no acepta tipo_vehiculo/combustible/modelo del caller;
    los lee del Vehiculo ya normalizado. Al evaluar, escribe combustible_validado
    en la Verificacion para que pruebas.py lo tenga disponible."""

    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.INSPECCION_VISUAL_APROBADA,
        tipo_vehiculo="vehiculo",
        combustible="gasolina",
        modelo=2020,
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/obd/evaluar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["aplica"] is True

    await db_session.refresh(expediente)
    assert expediente.combustible_validado == "gasolina"
    assert expediente.estado == EstadoVerificacion.OBD_PENDIENTE


async def test_evaluar_obd_sin_datos_vehiculo_responde_422(client, db_session):
    """Si el vehículo no tiene tipo_vehiculo/combustible/modelo, el endpoint
    rechaza con 422 en lugar de evaluar con datos None."""

    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.INSPECCION_VISUAL_APROBADA,
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/obd/evaluar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 422


async def test_evaluar_obd_no_aplica_combustible_validado_igual(client, db_session):
    """Aunque OBD no aplique (vehículo diésel), combustible_validado se escribe
    de todas formas para que el resultado de prueba quede bien registrado."""

    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.INSPECCION_VISUAL_APROBADA,
        tipo_vehiculo="vehiculo",
        combustible="diesel",
        modelo=2020,
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/obd/evaluar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["aplica"] is False

    await db_session.refresh(expediente)
    assert expediente.combustible_validado == "diesel"
    assert expediente.estado == EstadoVerificacion.LISTO_PARA_PRUEBA


async def test_solicitar_obd_sin_evaluar_responde_409(client, db_session):
    """Antes tiraba un TransitionNotAllowed sin manejar (500): no se puede
    solicitar OBD sin haberlo evaluado primero (OBD_PENDIENTE)."""

    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.INSPECCION_VISUAL_APROBADA,
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/obd/solicitar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409

    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.INSPECCION_VISUAL_APROBADA


async def test_guardar_resultado_obd_sin_solicitar_responde_409(client, db_session):
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.OBD_PENDIENTE,
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/obd/resultado/{expediente.id}",
        json={"resultado": "APROBADO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409

    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.OBD_PENDIENTE


async def test_solicitar_y_guardar_resultado_obd_camino_completo(client, db_session):
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.OBD_PENDIENTE,
    )
    await db_session.commit()

    resp_solicitar = await client.post(
        f"/api/obd/solicitar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_solicitar.status_code == 200
    assert resp_solicitar.json()["estado_expediente"] == EstadoVerificacion.OBD_SOLICITADO.value

    resp_resultado = await client.post(
        f"/api/obd/resultado/{expediente.id}",
        json={"resultado": "APROBADO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_resultado.status_code == 200
    assert resp_resultado.json()["estado_expediente"] == EstadoVerificacion.LISTO_PARA_PRUEBA.value


async def test_evaluar_obd_desde_estacion_captura_responde_403(client, db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.INSPECCION_VISUAL_APROBADA,
        tipo_vehiculo="vehiculo",
        combustible="gasolina",
        modelo=2020,
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/obd/evaluar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_evaluar_obd_expediente_otra_linea_responde_403(client, db_session):
    sesion = await _sesion_prueba(db_session, line_id=1)
    expediente = await crear_expediente(
        db_session,
        linea_id=2,
        estado=EstadoVerificacion.INSPECCION_VISUAL_APROBADA,
        tipo_vehiculo="vehiculo",
        combustible="gasolina",
        modelo=2020,
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/obd/evaluar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def _flujo_obd_hasta_solicitado(client, db_session):
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.INSPECCION_VISUAL_APROBADA,
        tipo_vehiculo="vehiculo",
        combustible="gasolina",
        modelo=2020,
    )
    await db_session.commit()
    h = {"X-Session-Id": str(sesion.id)}
    resp = await client.post(f"/api/obd/evaluar/{expediente.id}", headers=h)
    await client.post(f"/api/obd/solicitar/{expediente.id}", headers=h)
    return h, expediente, resp.json()


async def _fila(db_session, expediente):
    return (await db_session.execute(
        select(ResultadoObdSbd).where(ResultadoObdSbd.verificacion_id == expediente.id)
    )).scalars().one()


async def test_resultado_obd_se_guarda_en_la_tabla_con_codigos(client, db_session):
    """HU-032 (bug corregido 2026-10-05): el resultado y los códigos se
    guardan en resultados_obd_sbd, no solo en la bitácora."""

    h, expediente, evaluacion = await _flujo_obd_hasta_solicitado(client, db_session)
    assert "2020" in evaluacion["motivo"]  # HU-029

    resp = await client.post(
        f"/api/obd/resultado/{expediente.id}",
        json={"resultado": "RECHAZADO", "codigos_error": {"P0420": "Catalizador"}},
        headers=h,
    )
    assert resp.status_code == 200
    fila = await _fila(db_session, expediente)
    await db_session.refresh(fila)
    assert fila.resultado.value == "RECHAZADO"
    assert fila.codigos_error == {"P0420": "Catalizador"}
    assert fila.solicitado_at is not None and fila.recibido_at is not None


async def test_obd_sin_comunicacion_queda_como_error_con_evidencia(client, db_session):
    """HU-033/082: sin comunicación se registra como ERROR con mensaje técnico."""

    h, expediente, _ = await _flujo_obd_hasta_solicitado(client, db_session)
    resp = await client.post(
        f"/api/obd/resultado/{expediente.id}",
        json={"resultado": "APROBADO", "sin_comunicacion": True, "mensaje_tecnico": "Sin respuesta del conector"},
        headers=h,
    )
    assert resp.status_code == 200
    fila = await _fila(db_session, expediente)
    await db_session.refresh(fila)
    assert fila.resultado.value == "ERROR"
    assert fila.datos_raw == {"sin_comunicacion": True, "mensaje_tecnico": "Sin respuesta del conector"}


async def test_evaluar_obd_explica_por_que_no_aplica(client, db_session):
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.INSPECCION_VISUAL_APROBADA,
        tipo_vehiculo="vehiculo", combustible="diesel", modelo=2020,
    )
    await db_session.commit()
    resp = await client.post(
        f"/api/obd/evaluar/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )
    assert resp.json()["aplica"] is False
    assert "diesel" in resp.json()["motivo"]
