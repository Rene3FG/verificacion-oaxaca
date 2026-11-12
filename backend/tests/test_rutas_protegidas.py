"""Q3 / auditoría 3.7: toda ruta nueva nace protegida. Recorre `app.routes`
y exige 401 sin `X-Session-Id` salvo la lista blanca de rutas públicas, y
403 con una sesión sin permiso de supervisor en todas las rutas que usan
`requiere_supervisor`. Falla en cuanto alguien agregue una ruta sin guarda."""

import re
import uuid

import pytest
from fastapi.routing import APIRoute

from app.api.deps import get_current_session, get_session_cambio_password, requiere_supervisor
from app.main import app
from app.models.enums import StationType
from tests.conftest import crear_estacion, crear_permiso, crear_sesion_activa, crear_usuario

PUBLICAS = {
    ("POST", "/api/estaciones/login"),
    ("GET", "/api/estaciones/{device_identifier}"),
    ("GET", "/health"),
}


def _rutas():
    for r in app.routes:
        if isinstance(r, APIRoute):
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                yield m, r


def _url(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def _usa(dep, route: APIRoute) -> bool:
    pila = list(route.dependant.dependencies)
    while pila:
        d = pila.pop()
        if d.call is dep:
            return True
        pila.extend(d.dependencies)
    return False


RUTAS = [(m, r) for m, r in _rutas()]
PRIVADAS = [(m, r) for m, r in RUTAS if (m, r.path) not in PUBLICAS]
SUPERVISOR = [(m, r) for m, r in PRIVADAS if _usa(requiere_supervisor, r)]


def _tipos_permitidos(route: APIRoute) -> set[StationType] | None:
    """Tipos de estación que acepta la ruta según `requiere_estacion(...)`,
    leídos del closure del checker; None si la ruta no usa esa guarda."""
    pila = list(route.dependant.dependencies)
    while pila:
        d = pila.pop()
        if getattr(d.call, "__qualname__", "") == "requiere_estacion.<locals>.checker":
            celdas = dict(zip(d.call.__code__.co_freevars, d.call.__closure__))
            return set(celdas["tipos"].cell_contents)
        pila.extend(d.dependencies)
    return None


POR_TIPO = [
    (m, r, tipo)
    for m, r in PRIVADAS
    if (permitidos := _tipos_permitidos(r)) is not None
    for tipo in StationType
    if tipo not in permitidos
]


def test_inventario_de_rutas():
    assert len(PUBLICAS) == sum(1 for m, r in RUTAS if (m, r.path) in PUBLICAS)
    assert len(SUPERVISOR) >= 30
    sin_guarda = [
        f"{m} {r.path}"
        for m, r in PRIVADAS
        if not (_usa(get_current_session, r) or _usa(get_session_cambio_password, r))
    ]
    assert sin_guarda == []


@pytest.mark.parametrize("metodo,ruta", PRIVADAS, ids=[f"{m} {r.path}" for m, r in PRIVADAS])
async def test_sin_sesion_responde_401(client, metodo, ruta):
    resp = await client.request(metodo, _url(ruta.path))
    assert resp.status_code == 401, resp.text


@pytest.mark.parametrize("metodo,ruta", SUPERVISOR, ids=[f"{m} {r.path}" for m, r in SUPERVISOR])
async def test_operador_sin_supervision_responde_403(client, db_session, metodo, ruta):
    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA)
    usuario = await crear_usuario(db_session)
    await crear_permiso(
        db_session, user_id=usuario.id, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion, user_id=usuario.id)
    await db_session.commit()

    resp = await client.request(metodo, _url(ruta.path), headers={"X-Session-Id": str(sesion.id)})
    assert resp.status_code == 403, resp.text


def test_inventario_por_tipo_de_estacion():
    # obd, pruebas y folios (Q3) quedan cubiertos junto con el resto.
    rutas = {r.path for _, r, _ in POR_TIPO}
    for prefijo in ("/api/obd", "/api/pruebas", "/api/folios"):
        assert any(p.startswith(prefijo) for p in rutas), prefijo


@pytest.mark.parametrize(
    "metodo,ruta,tipo",
    POR_TIPO,
    ids=[f"{m} {r.path} desde {t.value}" for m, r, t in POR_TIPO],
)
async def test_estacion_de_otro_tipo_responde_403(client, db_session, metodo, ruta, tipo):
    estacion = await crear_estacion(db_session, station_type=tipo)
    usuario = await crear_usuario(db_session)
    await crear_permiso(db_session, user_id=usuario.id, station_type=tipo, center_id="OAX-01", line_id=1)
    sesion = await crear_sesion_activa(db_session, estacion=estacion, user_id=usuario.id)
    await db_session.commit()

    resp = await client.request(metodo, _url(ruta.path), headers={"X-Session-Id": str(sesion.id)})
    assert resp.status_code == 403, resp.text
    assert "requiere una estación de tipo" in resp.json()["detail"]
