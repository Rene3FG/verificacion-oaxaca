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


async def test_crear_usuario_permite_iniciar_sesion_y_no_expone_password(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}

    resp = await client.post(
        "/api/usuarios",
        headers=h,
        json={"username": "nuevo.op", "password": "clave-segura-1", "nombre_completo": "Nuevo Op"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "nuevo.op" and body["is_active"] is True
    assert "password" not in body and "password_hash" not in body


async def test_crear_usuario_duplicado_responde_409(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await crear_usuario(db_session, username="repetido")
    await db_session.commit()

    resp = await client.post(
        "/api/usuarios",
        headers={"X-Session-Id": str(sup.id)},
        json={"username": "repetido", "password": "clave-segura-1", "nombre_completo": "X"},
    )
    assert resp.status_code == 409


async def test_crear_usuario_password_corta_responde_422(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()
    resp = await client.post(
        "/api/usuarios",
        headers={"X-Session-Id": str(sup.id)},
        json={"username": "abc", "password": "corta", "nombre_completo": "X"},
    )
    assert resp.status_code == 422


async def test_crear_usuario_sin_supervisor_responde_403(client, db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()
    resp = await client.post(
        "/api/usuarios",
        headers={"X-Session-Id": str(sesion.id)},
        json={"username": "abc", "password": "clave-segura-1", "nombre_completo": "X"},
    )
    assert resp.status_code == 403


async def test_actualizar_usuario_cambia_password_y_desactiva(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    objetivo = await crear_usuario(db_session, password="vieja-clave-1")
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}

    resp = await client.patch(
        f"/api/usuarios/{objetivo.id}",
        headers=h,
        json={"password": "nueva-clave-1", "is_active": False, "nombre_completo": "Renombrado"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    assert resp.json()["nombre_completo"] == "Renombrado"

    await db_session.refresh(objetivo)
    from app.services.auth import verify_password

    assert verify_password("nueva-clave-1", objetivo.password_hash)
    assert not verify_password("vieja-clave-1", objetivo.password_hash)


async def test_supervisor_no_puede_desactivarse_a_si_mismo(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()
    resp = await client.patch(
        f"/api/usuarios/{sup.user_id}",
        headers={"X-Session-Id": str(sup.id)},
        json={"is_active": False},
    )
    assert resp.status_code == 409


async def test_actualizar_usuario_inexistente_responde_404(client, db_session):
    import uuid

    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()
    resp = await client.patch(
        f"/api/usuarios/{uuid.uuid4()}",
        headers={"X-Session-Id": str(sup.id)},
        json={"nombre_completo": "X"},
    )
    assert resp.status_code == 404
