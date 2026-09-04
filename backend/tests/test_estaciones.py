from app.models.enums import StationType
from tests.conftest import crear_estacion, crear_sesion_activa, crear_sesion_supervisor


async def test_actualizar_capacidad_dinamometro_sin_supervisor_responde_403(client, db_session):
    estacion = await crear_estacion(db_session, station_type=StationType.PRUEBA)
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.patch(
        f"/api/estaciones/{estacion.id}/capacidad-dinamometro",
        json={"capacidad_dinamometro_kg": 3500},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_actualizar_capacidad_dinamometro_en_estacion_de_captura_responde_422(
    client, db_session
):
    """Solo tiene sentido en estaciones PRUEBA — Captura/Impresión no
    tienen dinamómetro."""

    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA)
    sesion_supervisor = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.patch(
        f"/api/estaciones/{estacion.id}/capacidad-dinamometro",
        json={"capacidad_dinamometro_kg": 3500},
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 422


async def test_actualizar_capacidad_dinamometro_valor_no_positivo_responde_422(
    client, db_session
):
    estacion = await crear_estacion(db_session, station_type=StationType.PRUEBA)
    sesion_supervisor = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.patch(
        f"/api/estaciones/{estacion.id}/capacidad-dinamometro",
        json={"capacidad_dinamometro_kg": 0},
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 422


async def test_actualizar_capacidad_dinamometro_exitoso_y_null_la_limpia(client, db_session):
    estacion = await crear_estacion(db_session, station_type=StationType.PRUEBA)
    sesion_supervisor = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.patch(
        f"/api/estaciones/{estacion.id}/capacidad-dinamometro",
        json={"capacidad_dinamometro_kg": 3500},
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["capacidad_dinamometro_kg"] == 3500

    resp_null = await client.patch(
        f"/api/estaciones/{estacion.id}/capacidad-dinamometro",
        json={"capacidad_dinamometro_kg": None},
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp_null.status_code == 200
    assert resp_null.json()["capacidad_dinamometro_kg"] is None


async def test_listar_estaciones_sin_supervisor_responde_403(client, db_session):
    estacion = await crear_estacion(db_session, station_type=StationType.PRUEBA)
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.get("/api/estaciones", headers={"X-Session-Id": str(sesion.id)})
    assert resp.status_code == 403


async def test_listar_estaciones_filtra_por_centro_y_tipo(client, db_session):
    await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=2
    )
    await crear_estacion(db_session, station_type=StationType.CAPTURA, center_id="OAX-01")
    await crear_estacion(db_session, station_type=StationType.PRUEBA, center_id="OAX-02")
    sesion_supervisor = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.get(
        "/api/estaciones",
        params={"center_id": "OAX-01", "station_type": "prueba"},
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 200
    lineas = sorted(fila["line_id"] for fila in resp.json())
    assert lineas == [1, 2]
