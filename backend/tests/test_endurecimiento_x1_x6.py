"""Auditoría de seguridad 2026-11-04 (docs/AUDITORIA_SEGURIDAD_X1_X7.md),
parte de backend: X1-a/c/e (login), X2-a/b/c (sesiones), X4-d (/docs),
X5-b (seed) y X6-a (contraseñas)."""

import datetime
import uuid
import subprocess
import sys
import os

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.access_event import AccessEvent
from app.models.enums import StationType
from app.models.workstation import StationSession
from app.services.auth import validar_politica_password
from tests.conftest import (
    crear_estacion,
    crear_permiso,
    crear_sesion_activa,
    crear_sesion_supervisor,
    crear_usuario,
)

# ---------------------------------------------------------------- X6-a


@pytest.mark.parametrize(
    "password",
    ["Password123", "Oaxaca2026", "Abcd1234", "Verificentro1", "12345678a",
     "Operador2026", "Admin2026", "P4ssw0rd2026", "MiOaxaca99", "xVerificacion9"],
)
def test_politica_rechaza_las_contrasenas_que_la_auditoria_vio_aceptadas(password):
    with pytest.raises(ValueError):
        validar_politica_password(password)


@pytest.mark.parametrize("password", ["clave-segura-1", "Tr3n-azul-88", "CafeLluvia42", "x9k2m7p4"])
def test_politica_sigue_aceptando_contrasenas_razonables(password):
    validar_politica_password(password)


def test_politica_rechaza_contrasena_que_contiene_el_usuario():
    with pytest.raises(ValueError):
        validar_politica_password("xx-juanperez-77", username="juanperez")


async def test_alta_rechaza_contrasena_que_contiene_el_usuario(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.post(
        "/api/usuarios",
        headers={"X-Session-Id": str(sup.id)},
        json={"username": "mariag", "password": "mariag-2026x", "nombre_completo": "M"},
    )
    assert resp.status_code == 422


async def test_restablecer_aplica_la_politica_con_el_usuario(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    usuario = await crear_usuario(db_session, username="pedrox")
    await db_session.commit()

    resp = await client.patch(
        f"/api/usuarios/{usuario.id}",
        headers={"X-Session-Id": str(sup.id)},
        json={"password": "pedrox-segura-9"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------- X1


async def _estacion_login(db_session):
    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1)
    await db_session.commit()
    return estacion


async def _login(client, estacion, username, password="incorrecta-1", ip=None, body_ip=None):
    headers = {"X-Real-IP": ip} if ip else {}
    body = {"username": username, "password": password, "workstation_id": str(estacion.id)}
    if body_ip:
        body["ip_address"] = body_ip
    return await client.post("/api/estaciones/login", json=body, headers=headers)


async def test_ip_de_la_bitacora_sale_de_la_conexion_y_no_del_cuerpo(client, db_session):
    estacion = await _estacion_login(db_session)

    resp = await _login(client, estacion, "nadie", ip="10.0.0.7", body_ip="1.2.3.4")
    assert resp.status_code == 401

    ev = (await db_session.execute(select(AccessEvent).order_by(AccessEvent.created_at.desc()))).scalars().first()
    assert ev.ip_address == "10.0.0.7"


async def test_spraying_desde_una_ip_se_corta_aunque_los_usuarios_no_existan(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "login_max_intentos_ip", 4)
    estacion = await _estacion_login(db_session)

    for i in range(4):
        assert (await _login(client, estacion, f"fantasma{i}", ip="10.9.9.9")).status_code == 401

    resp = await _login(client, estacion, "otro-mas", ip="10.9.9.9")
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0

    # Otra máquina no queda afectada
    assert (await _login(client, estacion, "otro-mas", ip="10.9.9.10")).status_code == 401


async def test_tope_por_ip_apagado_con_cero(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "login_max_intentos_ip", 0)
    monkeypatch.setattr(settings, "login_max_intentos", 0)
    estacion = await _estacion_login(db_session)

    for i in range(6):
        assert (await _login(client, estacion, f"x{i}", ip="10.1.1.1")).status_code == 401


# ---------------------------------------------------------------- X2


async def test_sesion_expira_por_vida_maxima_aunque_tenga_actividad(client, db_session):
    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1)
    usuario = await crear_usuario(db_session, username="maraton")
    sesion = await crear_sesion_activa(db_session, estacion=estacion, user_id=usuario.id)
    ahora = datetime.datetime.now(datetime.timezone.utc)
    sesion.login_at = ahora - datetime.timedelta(hours=settings.sesion_duracion_max_h, minutes=1)
    sesion.updated_at = ahora  # actividad reciente: no es por inactividad
    await db_session.commit()

    # Cualquier ruta con sesión sirve; el UUID no existe, pero la sesión se
    # resuelve antes que el expediente.
    resp = await client.get(f"/api/expedientes/{uuid.uuid4()}", headers={"X-Session-Id": str(sesion.id)})
    assert resp.status_code == 401
    await db_session.refresh(sesion)
    assert sesion.status == "expirada"


async def _sesion_operador(db_session, username):
    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1)
    usuario = await crear_usuario(db_session, username=username)
    permiso = await crear_permiso(
        db_session, user_id=usuario.id, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion, user_id=usuario.id)
    return usuario, permiso, sesion


async def test_revocar_permiso_cierra_las_sesiones_del_usuario(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    _, permiso, sesion = await _sesion_operador(db_session, "revocado")
    await db_session.commit()

    resp = await client.delete(f"/api/permisos/{permiso.id}", headers={"X-Session-Id": str(sup.id)})
    assert resp.status_code == 204

    await db_session.refresh(sesion)
    assert sesion.status == "cerrada"
    # La del supervisor que hizo el cambio sigue viva
    await db_session.refresh(sup)
    assert sup.status == "activa"


async def test_modificar_permiso_cierra_sesiones_solo_si_hubo_cambio(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    _, permiso, sesion = await _sesion_operador(db_session, "modificado")
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}

    await client.patch(f"/api/permisos/{permiso.id}", headers=h, json={"can_operate": True})
    await db_session.refresh(sesion)
    assert sesion.status == "activa"

    await client.patch(f"/api/permisos/{permiso.id}", headers=h, json={"can_operate": False})
    await db_session.refresh(sesion)
    assert sesion.status == "cerrada"


async def test_restablecer_contrasena_cierra_las_sesiones_del_usuario(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    usuario, _, sesion = await _sesion_operador(db_session, "robado")
    await db_session.commit()

    resp = await client.patch(
        f"/api/usuarios/{usuario.id}", headers={"X-Session-Id": str(sup.id)}, json={"password": "Nueva-clave-77"}
    )
    assert resp.status_code == 200
    await db_session.refresh(sesion)
    assert sesion.status == "cerrada"


async def test_editar_solo_el_nombre_no_cierra_sesiones(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    usuario, _, sesion = await _sesion_operador(db_session, "renombrado")
    await db_session.commit()

    await client.patch(
        f"/api/usuarios/{usuario.id}", headers={"X-Session-Id": str(sup.id)}, json={"nombre_completo": "Otro"}
    )
    await db_session.refresh(sesion)
    assert sesion.status == "activa"


# ---------------------------------------------------------------- X4-d / X5-b


def _correr(codigo: str, app_env: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "APP_ENV": app_env}
    return subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env, capture_output=True, text=True, timeout=60,
    )


def test_docs_apagados_en_produccion_y_activos_en_desarrollo():
    codigo = "from app.main import app; print(app.docs_url, app.openapi_url)"
    assert _correr(codigo, "production").stdout.strip() == "None None"
    assert _correr(codigo, "development").stdout.strip() == "/docs /openapi.json"


@pytest.mark.parametrize("modulo", ["app.seed", "app.seed_demo"])
def test_seeds_de_demo_se_niegan_a_correr_en_produccion(modulo):
    env = {**os.environ, "APP_ENV": "production"}
    r = subprocess.run(
        [sys.executable, "-m", modulo],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode != 0
    assert "APP_ENV=production" in r.stderr
