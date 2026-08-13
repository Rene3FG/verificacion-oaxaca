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
