from sqlalchemy import select

from app.models.access_event import AccessEvent
from app.models.enums import AccessEventResultado, StationType
from tests.conftest import crear_estacion, crear_permiso, crear_usuario


async def test_login_permitido_con_linea_exacta(client, db_session):
    usuario = await crear_usuario(db_session, password="clave123")
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    await crear_permiso(
        db_session,
        user_id=usuario.id,
        station_type=StationType.PRUEBA,
        center_id="OAX-01",
        line_id=1,
    )
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={
            "username": usuario.username,
            "password": "clave123",
            "workstation_id": str(estacion.id),
        },
    )

    assert resp.status_code == 200
    assert resp.json()["line_id"] == 1
    assert resp.json()["user_id"] == str(usuario.id)


async def test_login_denegado_por_contrasena_incorrecta(client, db_session):
    usuario = await crear_usuario(db_session, password="clave-correcta")
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    await crear_permiso(
        db_session,
        user_id=usuario.id,
        station_type=StationType.PRUEBA,
        center_id="OAX-01",
        line_id=1,
    )
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={
            "username": usuario.username,
            "password": "clave-incorrecta",
            "workstation_id": str(estacion.id),
        },
    )

    assert resp.status_code == 401


async def test_login_denegado_usuario_inexistente(client, db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={
            "username": "no-existe",
            "password": "lo-que-sea",
            "workstation_id": str(estacion.id),
        },
    )

    assert resp.status_code == 401


async def test_login_denegado_usuario_inactivo(client, db_session):
    usuario = await crear_usuario(db_session, password="clave123", is_active=False)
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    await crear_permiso(
        db_session,
        user_id=usuario.id,
        station_type=StationType.PRUEBA,
        center_id="OAX-01",
        line_id=1,
    )
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={
            "username": usuario.username,
            "password": "clave123",
            "workstation_id": str(estacion.id),
        },
    )

    assert resp.status_code == 401


async def test_login_denegado_por_linea_distinta(client, db_session):
    """HU-001: un permiso para línea 2 no debe abrir sesión en una estación
    de línea 1, aunque el tipo de estación y el centro coincidan."""

    usuario = await crear_usuario(db_session, password="clave123")
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    await crear_permiso(
        db_session,
        user_id=usuario.id,
        station_type=StationType.PRUEBA,
        center_id="OAX-01",
        line_id=2,
    )
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={
            "username": usuario.username,
            "password": "clave123",
            "workstation_id": str(estacion.id),
        },
    )

    assert resp.status_code == 403


async def test_login_permitido_para_supervisor_con_line_id_null(client, db_session):
    """HU-001: line_id=NULL en el permiso significa 'todas las líneas del
    centro' (supervisor)."""

    usuario = await crear_usuario(db_session, password="clave123")
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=3
    )
    await crear_permiso(
        db_session,
        user_id=usuario.id,
        station_type=StationType.PRUEBA,
        center_id="OAX-01",
        line_id=None,
    )
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={
            "username": usuario.username,
            "password": "clave123",
            "workstation_id": str(estacion.id),
        },
    )

    assert resp.status_code == 200
    assert resp.json()["line_id"] == 3


async def test_login_permitido_registra_access_event(client, db_session):
    usuario = await crear_usuario(db_session, password="clave123")
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-02", line_id=1
    )
    await crear_permiso(
        db_session,
        user_id=usuario.id,
        station_type=StationType.CAPTURA,
        center_id="OAX-02",
        line_id=1,
    )
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={
            "username": usuario.username,
            "password": "clave123",
            "workstation_id": str(estacion.id),
        },
    )
    session_id = resp.json()["id"]

    eventos = (
        await db_session.execute(
            select(AccessEvent).where(AccessEvent.session_id == session_id)
        )
    ).scalars().all()

    assert len(eventos) == 1
    assert eventos[0].resultado == AccessEventResultado.PERMITIDO
    assert eventos[0].user_id == usuario.id


async def test_login_expone_can_supervise_del_permiso_usado(client, db_session):
    """El frontend usa can_supervise (no viene de StationSession, se
    calcula del UserStationPermission que autorizó el login) para
    mostrar/ocultar la pantalla de Supervisor."""

    supervisor = await crear_usuario(db_session, password="clave123")
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-04", line_id=1
    )
    await crear_permiso(
        db_session,
        user_id=supervisor.id,
        station_type=StationType.CAPTURA,
        center_id="OAX-04",
        line_id=None,
        can_supervise=True,
    )
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={
            "username": supervisor.username,
            "password": "clave123",
            "workstation_id": str(estacion.id),
        },
    )

    assert resp.status_code == 200
    assert resp.json()["can_supervise"] is True


async def test_login_can_supervise_false_para_operador_normal(client, db_session):
    operador = await crear_usuario(db_session, password="clave123")
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-04", line_id=1
    )
    await crear_permiso(
        db_session,
        user_id=operador.id,
        station_type=StationType.CAPTURA,
        center_id="OAX-04",
        line_id=1,
    )
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={
            "username": operador.username,
            "password": "clave123",
            "workstation_id": str(estacion.id),
        },
    )

    assert resp.status_code == 200
    assert resp.json()["can_supervise"] is False


async def test_login_denegado_registra_access_event_sin_expediente(client, db_session):
    """HU-007: un login denegado se audita en access_events, que no exige
    verificacion_id (a diferencia de event_log)."""

    usuario = await crear_usuario(db_session, password="clave123")
    estacion = await crear_estacion(
        db_session, station_type=StationType.IMPRESION, center_id="OAX-03", line_id=1
    )
    # Sin permiso creado -> debe ser denegado.
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={
            "username": usuario.username,
            "password": "clave123",
            "workstation_id": str(estacion.id),
        },
    )

    assert resp.status_code == 403

    eventos = (
        await db_session.execute(
            select(AccessEvent).where(AccessEvent.user_id == usuario.id)
        )
    ).scalars().all()

    assert len(eventos) == 1
    assert eventos[0].resultado == AccessEventResultado.DENEGADO
    assert eventos[0].session_id is None
