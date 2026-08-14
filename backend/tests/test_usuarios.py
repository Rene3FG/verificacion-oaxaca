from app.models.enums import StationType
from tests.conftest import crear_estacion, crear_sesion_activa, crear_sesion_supervisor, crear_usuario


async def test_listar_usuarios_sin_supervisor_responde_403(client, db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.get("/api/usuarios", headers={"X-Session-Id": str(sesion.id)})
    assert resp.status_code == 403


async def test_listar_usuarios_ordenados_por_username(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    await crear_usuario(db_session, username="zeta")
    await crear_usuario(db_session, username="alfa")
    await db_session.commit()

    resp = await client.get("/api/usuarios", headers={"X-Session-Id": str(sesion.id)})

    assert resp.status_code == 200
    usernames = [u["username"] for u in resp.json()]
    assert usernames == sorted(usernames)
    assert "alfa" in usernames and "zeta" in usernames
