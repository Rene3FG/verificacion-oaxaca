"""NOM-047 punto 5 (B10-b): campo 001 del certificado = clave del técnico.
Aquí solo se cubre el catálogo (alta, edición, unicidad, normalización);
cómo llega al certificado está pendiente de definir con el cliente."""

from tests.conftest import crear_sesion_supervisor, crear_usuario


def _alta(clave=None, username="tec.uno"):
    body = {"username": username, "password": "clave-segura-1", "nombre_completo": "Técnico"}
    if clave is not None:
        body["clave_tecnico"] = clave
    return body


async def test_alta_con_clave_tecnico_se_normaliza_y_se_devuelve(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.post(
        "/api/usuarios", headers={"X-Session-Id": str(sup.id)}, json=_alta("  t-07 ")
    )

    assert resp.status_code == 201
    assert resp.json()["clave_tecnico"] == "T-07"


async def test_alta_sin_clave_tecnico_queda_null(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.post("/api/usuarios", headers={"X-Session-Id": str(sup.id)}, json=_alta())

    assert resp.status_code == 201
    assert resp.json()["clave_tecnico"] is None


async def test_alta_con_clave_tecnico_invalida_responde_422(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.post(
        "/api/usuarios", headers={"X-Session-Id": str(sup.id)}, json=_alta("T 07!")
    )

    assert resp.status_code == 422


async def test_clave_tecnico_duplicada_en_alta_responde_409(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}

    assert (await client.post("/api/usuarios", headers=h, json=_alta("001"))).status_code == 201
    resp = await client.post("/api/usuarios", headers=h, json=_alta("001", username="tec.dos"))

    assert resp.status_code == 409


async def test_editar_asigna_y_quita_clave_tecnico(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    usuario = await crear_usuario(db_session, username="tec.edit")
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}

    resp = await client.patch(f"/api/usuarios/{usuario.id}", headers=h, json={"clave_tecnico": "a12"})
    assert resp.status_code == 200 and resp.json()["clave_tecnico"] == "A12"

    # Omitir el campo no la toca
    resp = await client.patch(f"/api/usuarios/{usuario.id}", headers=h, json={"nombre_completo": "Otro"})
    assert resp.json()["clave_tecnico"] == "A12"

    # null la quita
    resp = await client.patch(f"/api/usuarios/{usuario.id}", headers=h, json={"clave_tecnico": None})
    assert resp.status_code == 200 and resp.json()["clave_tecnico"] is None


async def test_editar_a_clave_ajena_responde_409_y_la_propia_se_permite(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    uno = await crear_usuario(db_session, username="tec.a")
    dos = await crear_usuario(db_session, username="tec.b")
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}

    await client.patch(f"/api/usuarios/{uno.id}", headers=h, json={"clave_tecnico": "X1"})
    resp = await client.patch(f"/api/usuarios/{dos.id}", headers=h, json={"clave_tecnico": "X1"})
    assert resp.status_code == 409

    resp = await client.patch(f"/api/usuarios/{uno.id}", headers=h, json={"clave_tecnico": "x1"})
    assert resp.status_code == 200
