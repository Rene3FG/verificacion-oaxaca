import uuid

from sqlalchemy import select

from app.models.access_event import AccessEvent
from app.models.enums import AccessEventResultado, StationType
from tests.conftest import crear_estacion, crear_permiso


async def test_login_permitido_con_linea_exacta(client, db_session):
    user_id = uuid.uuid4()
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    await crear_permiso(
        db_session, user_id=user_id, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={"user_id": str(user_id), "workstation_id": str(estacion.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["line_id"] == 1


async def test_login_denegado_por_linea_distinta(client, db_session):
    """HU-001: un permiso para línea 2 no debe abrir sesión en una estación
    de línea 1, aunque el tipo de estación y el centro coincidan."""

    user_id = uuid.uuid4()
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    await crear_permiso(
        db_session, user_id=user_id, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=2
    )
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={"user_id": str(user_id), "workstation_id": str(estacion.id)},
    )

    assert resp.status_code == 403


async def test_login_permitido_para_supervisor_con_line_id_null(client, db_session):
    """HU-001: line_id=NULL en el permiso significa 'todas las líneas del
    centro' (supervisor)."""

    user_id = uuid.uuid4()
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=3
    )
    await crear_permiso(
        db_session, user_id=user_id, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=None
    )
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={"user_id": str(user_id), "workstation_id": str(estacion.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["line_id"] == 3


async def test_login_permitido_registra_access_event(client, db_session):
    user_id = uuid.uuid4()
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-02", line_id=1
    )
    await crear_permiso(
        db_session, user_id=user_id, station_type=StationType.CAPTURA, center_id="OAX-02", line_id=1
    )
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={"user_id": str(user_id), "workstation_id": str(estacion.id)},
    )
    session_id = uuid.UUID(resp.json()["id"])

    eventos = (
        await db_session.execute(
            select(AccessEvent).where(AccessEvent.session_id == session_id)
        )
    ).scalars().all()

    assert len(eventos) == 1
    assert eventos[0].resultado == AccessEventResultado.PERMITIDO
    assert eventos[0].user_id == user_id


async def test_login_denegado_registra_access_event_sin_expediente(client, db_session):
    """HU-007: un login denegado se audita en access_events, que no exige
    verificacion_id (a diferencia de event_log)."""

    user_id = uuid.uuid4()
    estacion = await crear_estacion(
        db_session, station_type=StationType.IMPRESION, center_id="OAX-03", line_id=1
    )
    # Sin permiso creado -> debe ser denegado.
    await db_session.commit()

    resp = await client.post(
        "/api/estaciones/login",
        json={"user_id": str(user_id), "workstation_id": str(estacion.id)},
    )

    assert resp.status_code == 403

    eventos = (
        await db_session.execute(
            select(AccessEvent).where(AccessEvent.user_id == user_id)
        )
    ).scalars().all()

    assert len(eventos) == 1
    assert eventos[0].resultado == AccessEventResultado.DENEGADO
    assert eventos[0].session_id is None
