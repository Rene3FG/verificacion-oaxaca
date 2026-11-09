"""Pendientes de backend del reporte de coordinación de Sebas (2026-11-05):
X2-e (sesión huérfana), desbloqueo por supervisor, X6-b (cambio propio y
must_change_password), X6-c (usuario sin mayúsculas), GET público de la
estación reducido y permisos con usuario inexistente."""

import uuid

from sqlalchemy import select

from app.core.config import settings
from app.models.access_event import AccessEvent
from app.models.enums import AccessEventResultado, StationType
from app.models.event_log import EventLog
from app.models.usuario import CatUsuario
from app.models.workstation import StationSession, Workstation
from tests.conftest import (
    crear_estacion,
    crear_permiso,
    crear_sesion_activa,
    crear_sesion_supervisor,
    crear_usuario,
)

PASS = "clave-de-prueba"


async def _operador(db_session, username="opx", password=PASS):
    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1)
    usuario = await crear_usuario(db_session, username=username, password=password)
    await crear_permiso(
        db_session, user_id=usuario.id, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1
    )
    await db_session.commit()
    return estacion, usuario


async def _login(client, estacion, username, password=PASS):
    return await client.post(
        "/api/estaciones/login",
        json={"username": username, "password": password, "workstation_id": str(estacion.id)},
    )


# ------------------------------------------------------------- X2-e


async def test_sesion_de_usuario_inexistente_responde_401(client, db_session):
    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA)
    sesion = StationSession(
        user_id=uuid.uuid4(),
        workstation_id=estacion.id,
        station_type=estacion.station_type,
        center_id=estacion.center_id,
        line_id=estacion.line_id,
        status="activa",
    )
    db_session.add(sesion)
    await db_session.commit()

    resp = await client.get("/api/sync/estado", headers={"X-Session-Id": str(sesion.id)})
    assert resp.status_code == 401


# ------------------------------------------------------------- estación pública


async def test_deteccion_publica_no_expone_datos_internos(client, db_session):
    estacion = await crear_estacion(db_session, station_type=StationType.PRUEBA, capacidad_dinamometro_kg=3500)
    estacion.device_identifier = f"DEV-{uuid.uuid4().hex[:6]}"
    await db_session.commit()

    resp = await client.get(f"/api/estaciones/{estacion.device_identifier}")
    assert resp.status_code == 200
    datos = resp.json()
    assert set(datos) == {"id", "name", "station_type", "center_id", "line_id", "allowed_line_ids"}


# ------------------------------------------------------------- desbloqueo


async def _bloquear(client, estacion, username):
    for _ in range(settings.login_max_intentos):
        assert (await _login(client, estacion, username, "incorrecta-1")).status_code == 401
    assert (await _login(client, estacion, username)).status_code == 429


async def test_supervisor_desbloquea_y_el_login_vuelve_a_funcionar(client, db_session):
    estacion, usuario = await _operador(db_session, "bloqueado1")
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()
    await _bloquear(client, estacion, "bloqueado1")

    resp = await client.post(
        f"/api/usuarios/{usuario.id}/desbloquear", headers={"X-Session-Id": str(sup.id)}
    )
    assert resp.status_code == 204

    assert (await _login(client, estacion, "bloqueado1")).status_code == 200
    ev = (
        await db_session.execute(
            select(AccessEvent).where(
                AccessEvent.user_id == usuario.id,
                AccessEvent.resultado == AccessEventResultado.DESBLOQUEO,
            )
        )
    ).scalar_one()
    assert ev.session_id == sup.id
    admin = (
        await db_session.execute(select(EventLog).where(EventLog.evento == "usuario_desbloqueado"))
    ).scalars().all()
    assert len(admin) == 1


async def test_desbloquear_sin_supervisor_403_e_inexistente_404(client, db_session):
    estacion, usuario = await _operador(db_session, "bloqueado2")
    sesion = await crear_sesion_activa(db_session, estacion=estacion, user_id=usuario.id)
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.post(
        f"/api/usuarios/{usuario.id}/desbloquear", headers={"X-Session-Id": str(sesion.id)}
    )
    assert resp.status_code == 403
    resp = await client.post(
        f"/api/usuarios/{uuid.uuid4()}/desbloquear", headers={"X-Session-Id": str(sup.id)}
    )
    assert resp.status_code == 404


# ------------------------------------------------------------- X6-b


async def _alta_por_supervisor(client, db_session, username="nuevo1", password="Tr3n-azul-88"):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()
    resp = await client.post(
        "/api/usuarios",
        headers={"X-Session-Id": str(sup.id)},
        json={"username": username, "password": password, "nombre_completo": "N"},
    )
    assert resp.status_code == 201
    assert resp.json()["must_change_password"] is True
    usuario_id = uuid.UUID(resp.json()["id"])
    await crear_permiso(
        db_session, user_id=usuario_id, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1
    )
    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1)
    await db_session.commit()
    return sup, usuario_id, estacion


async def test_usuario_nuevo_solo_puede_cambiar_su_contrasena(client, db_session):
    _, usuario_id, estacion = await _alta_por_supervisor(client, db_session)

    login = await _login(client, estacion, "nuevo1", "Tr3n-azul-88")
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True
    h = {"X-Session-Id": login.json()["id"]}

    assert (await client.get("/api/sync/estado", headers=h)).status_code == 403

    mal = await client.post(
        "/api/usuarios/me/password", headers=h,
        json={"password_actual": "otra-cosa-1", "password_nueva": "CafeLluvia42"},
    )
    assert mal.status_code == 422
    igual = await client.post(
        "/api/usuarios/me/password", headers=h,
        json={"password_actual": "Tr3n-azul-88", "password_nueva": "Tr3n-azul-88"},
    )
    assert igual.status_code == 422
    debil = await client.post(
        "/api/usuarios/me/password", headers=h,
        json={"password_actual": "Tr3n-azul-88", "password_nueva": "Password123"},
    )
    assert debil.status_code == 422

    ok = await client.post(
        "/api/usuarios/me/password", headers=h,
        json={"password_actual": "Tr3n-azul-88", "password_nueva": "CafeLluvia42"},
    )
    assert ok.status_code == 204
    assert (await client.get("/api/sync/estado", headers=h)).status_code == 200

    usuario = await db_session.get(CatUsuario, usuario_id)
    await db_session.refresh(usuario)
    assert usuario.must_change_password is False
    assert (await _login(client, estacion, "nuevo1", "CafeLluvia42")).status_code == 200


async def test_logout_permitido_con_cambio_pendiente(client, db_session):
    _, _, estacion = await _alta_por_supervisor(client, db_session, "nuevo2")
    login = await _login(client, estacion, "nuevo2", "Tr3n-azul-88")
    sid = login.json()["id"]
    resp = await client.post(f"/api/estaciones/logout/{sid}", headers={"X-Session-Id": sid})
    assert resp.status_code == 200


async def test_restablecer_ajena_activa_el_cambio_y_propia_no(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    otro = await crear_usuario(db_session, username="victima1")
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}

    assert (await client.patch(f"/api/usuarios/{otro.id}", headers=h, json={"password": "CafeLluvia42"})).status_code == 200
    await db_session.refresh(otro)
    assert otro.must_change_password is True

    resp = await client.patch(f"/api/usuarios/{sup.user_id}", headers=h, json={"password": "x9k2m7p4"})
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is False


# ------------------------------------------------------------- X6-c


async def test_login_no_distingue_mayusculas(client, db_session):
    estacion, _ = await _operador(db_session, "mixto")
    assert (await _login(client, estacion, "MIXTO")).status_code == 200
    assert (await _login(client, estacion, " Mixto ")).status_code == 200


async def test_alta_rechaza_usuario_que_solo_difiere_en_mayusculas(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await crear_usuario(db_session, username="admin7")
    await db_session.commit()
    resp = await client.post(
        "/api/usuarios",
        headers={"X-Session-Id": str(sup.id)},
        json={"username": "ADMIN7", "password": "CafeLluvia42", "nombre_completo": "A"},
    )
    assert resp.status_code == 409
