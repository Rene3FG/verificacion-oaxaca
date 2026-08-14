import uuid

from app.models.enums import StationType
from tests.conftest import crear_estacion, crear_permiso, crear_sesion_activa, crear_sesion_supervisor


async def _sesion_supervisor(db_session, *, center_id: str = "OAX-01"):
    return await crear_sesion_supervisor(db_session, center_id=center_id)


async def _sesion_operador(db_session, *, center_id: str = "OAX-01"):
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id=center_id, line_id=1
    )
    return await crear_sesion_activa(db_session, estacion=estacion)


async def test_listar_permisos_sin_supervisor_responde_403(client, db_session):
    sesion = await _sesion_operador(db_session)
    await db_session.commit()

    resp = await client.get("/api/permisos", headers={"X-Session-Id": str(sesion.id)})

    assert resp.status_code == 403


async def test_crear_permiso_exitoso(client, db_session):
    sesion = await _sesion_supervisor(db_session)
    nuevo_user_id = uuid.uuid4()
    await db_session.commit()

    resp = await client.post(
        "/api/permisos",
        json={
            "user_id": str(nuevo_user_id),
            "station_type": "prueba",
            "center_id": "OAX-01",
            "line_id": 1,
            "can_operate": True,
        },
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["user_id"] == str(nuevo_user_id)
    assert body["station_type"] == "prueba"
    assert body["can_operate"] is True
    assert body["can_supervise"] is False


async def test_crear_permiso_duplicado_responde_409(client, db_session):
    sesion = await _sesion_supervisor(db_session)
    nuevo_user_id = uuid.uuid4()
    await crear_permiso(
        db_session,
        user_id=nuevo_user_id,
        station_type=StationType.PRUEBA,
        center_id="OAX-01",
        line_id=1,
    )
    await db_session.commit()

    resp = await client.post(
        "/api/permisos",
        json={
            "user_id": str(nuevo_user_id),
            "station_type": "prueba",
            "center_id": "OAX-01",
            "line_id": 1,
        },
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 409


async def test_actualizar_permiso(client, db_session):
    sesion = await _sesion_supervisor(db_session)
    permiso = await crear_permiso(
        db_session,
        user_id=uuid.uuid4(),
        station_type=StationType.PRUEBA,
        center_id="OAX-01",
        line_id=1,
    )
    await db_session.commit()

    resp = await client.patch(
        f"/api/permisos/{permiso.id}",
        json={"can_operate": False, "can_supervise": True},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["can_operate"] is False
    assert body["can_supervise"] is True
    assert body["line_id"] == 1


async def test_eliminar_permiso(client, db_session):
    sesion = await _sesion_supervisor(db_session)
    permiso = await crear_permiso(
        db_session,
        user_id=uuid.uuid4(),
        station_type=StationType.PRUEBA,
        center_id="OAX-01",
        line_id=1,
    )
    await db_session.commit()

    resp = await client.delete(
        f"/api/permisos/{permiso.id}", headers={"X-Session-Id": str(sesion.id)}
    )
    assert resp.status_code == 204

    resp_listar = await client.get(
        "/api/permisos",
        params={"user_id": str(permiso.user_id)},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_listar.json() == []


async def test_listar_permisos_filtra_por_center_y_station_type(client, db_session):
    sesion = await _sesion_supervisor(db_session, center_id="OAX-01")
    await crear_permiso(
        db_session,
        user_id=uuid.uuid4(),
        station_type=StationType.PRUEBA,
        center_id="OAX-01",
        line_id=1,
    )
    await crear_permiso(
        db_session,
        user_id=uuid.uuid4(),
        station_type=StationType.IMPRESION,
        center_id="OAX-02",
        line_id=None,
    )
    await db_session.commit()

    resp = await client.get(
        "/api/permisos",
        params={"center_id": "OAX-01", "station_type": "prueba"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert all(p["center_id"] == "OAX-01" and p["station_type"] == "prueba" for p in body)
    assert len(body) >= 1
