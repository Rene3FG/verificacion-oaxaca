import uuid

from app.models.enums import StationType
from app.models.workstation import StationSession
from tests.conftest import crear_estacion, crear_sesion_activa, crear_sesion_supervisor


async def test_logout_sin_sesion_valida_responde_401(client, db_session):
    """Hallazgo de la revisión del PR #1: antes bastaba con el UUID en la
    URL, sin ninguna autenticación — cualquiera podía cerrarle la sesión a
    otro operador."""

    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA)
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.post(
        f"/api/estaciones/logout/{sesion.id}", headers={"X-Session-Id": str(uuid.uuid4())}
    )
    assert resp.status_code == 401

    await db_session.refresh(sesion)
    assert sesion.status == "activa"


async def test_logout_de_sesion_ajena_responde_403(client, db_session):
    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA)
    propia = await crear_sesion_activa(db_session, estacion=estacion)
    otra_estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA, line_id=2)
    ajena = await crear_sesion_activa(db_session, estacion=otra_estacion)
    await db_session.commit()

    resp = await client.post(
        f"/api/estaciones/logout/{ajena.id}", headers={"X-Session-Id": str(propia.id)}
    )
    assert resp.status_code == 403

    await db_session.refresh(ajena)
    assert ajena.status == "activa"


async def test_logout_de_la_propia_sesion_la_cierra(client, db_session):
    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA)
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.post(
        f"/api/estaciones/logout/{sesion.id}", headers={"X-Session-Id": str(sesion.id)}
    )
    assert resp.status_code == 200

    cerrada = await db_session.get(StationSession, sesion.id)
    assert cerrada.status == "cerrada"
    assert cerrada.logout_at is not None


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


async def test_crear_estacion_y_duplicados(client, db_session):
    from tests.conftest import crear_sesion_supervisor

    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}
    body = {
        "name": "PRUEBA-CRUD-01",
        "station_type": "prueba",
        "center_id": "OAX-01",
        "line_id": 2,
        "device_identifier": "DEV-CRUD-01",
    }

    resp = await client.post("/api/estaciones", headers=h, json=body)
    assert resp.status_code == 201
    assert resp.json()["is_active"] is True
    assert resp.json()["device_identifier"] == "DEV-CRUD-01"

    assert (await client.post("/api/estaciones", headers=h, json=body)).status_code == 409
    otro = {**body, "name": "PRUEBA-CRUD-02"}
    assert (await client.post("/api/estaciones", headers=h, json=otro)).status_code == 409


async def test_actualizar_y_desactivar_estacion(client, db_session):
    from tests.conftest import crear_sesion_supervisor

    sup = await crear_sesion_supervisor(db_session)
    est = await crear_estacion(db_session, station_type=StationType.PRUEBA, line_id=1)
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}

    resp = await client.patch(
        f"/api/estaciones/{est.id}", headers=h, json={"line_id": 3, "is_active": False}
    )
    assert resp.status_code == 200
    assert resp.json()["line_id"] == 3 and resp.json()["is_active"] is False

    lista = await client.get("/api/estaciones", headers=h)
    assert str(est.id) not in [e["id"] for e in lista.json()]


async def test_crear_estacion_sin_supervisor_responde_403(client, db_session):
    from tests.conftest import crear_sesion_activa

    est = await crear_estacion(db_session, station_type=StationType.CAPTURA)
    sesion = await crear_sesion_activa(db_session, estacion=est)
    await db_session.commit()
    resp = await client.post(
        "/api/estaciones",
        headers={"X-Session-Id": str(sesion.id)},
        json={"name": "X", "station_type": "captura", "center_id": "OAX-01"},
    )
    assert resp.status_code == 403
