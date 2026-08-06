from app.models.enums import EstadoVerificacion, StationType
from tests.conftest import crear_estacion, crear_sesion_activa


async def test_crear_expediente_hereda_centro_y_linea_de_la_sesion(client, db_session):
    """HU-019/HU-018: centro_id y linea_id nunca se aceptan del payload,
    salen de la sesión de la estación de Captura."""

    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=3
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.post(
        "/api/expedientes",
        json={"placa": "ABC123"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["placa"] == "ABC123"
    assert body["centro_id"] == "OAX-01"
    assert body["linea_id"] == 3
    assert body["estado"] == EstadoVerificacion.CREADO.value


async def test_crear_expediente_ignora_linea_del_payload(client, db_session):
    """Aunque el cliente mande linea_id en el body, ExpedienteCreate no lo
    acepta: solo cuenta lo que diga la sesión."""

    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=3
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.post(
        "/api/expedientes",
        json={"placa": "ABC123", "linea_id": 99, "centro_id": "OAX-99"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["linea_id"] == 3
    assert body["centro_id"] == "OAX-01"


async def test_crear_expediente_desde_estacion_de_prueba_responde_403(client, db_session):
    """HU-019: solo Captura abre expedientes; Prueba e Impresión no."""

    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.post(
        "/api/expedientes",
        json={"placa": "ABC123"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 403


async def test_crear_expediente_sin_session_id_responde_401(client, db_session):
    resp = await client.post("/api/expedientes", json={"placa": "ABC123"})
    assert resp.status_code in (401, 422)
