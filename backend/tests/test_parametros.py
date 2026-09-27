from app.models.enums import StationType
from tests.conftest import crear_estacion, crear_sesion_activa, crear_sesion_supervisor


async def test_listar_parametros_sin_supervisor_responde_403(client, db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.get("/api/parametros", headers={"X-Session-Id": str(sesion.id)})
    assert resp.status_code == 403


async def test_listar_parametros_incluye_defaults_sin_fila_propia(client, db_session):
    from sqlalchemy import delete

    from app.models.catalogos import CatParametroSistema

    # `app/seed.py` siempre inserta una fila real por cada DEFAULTS al
    # arrancar el sistema — se borra aquí, dentro de la transacción de la
    # prueba, para poder probar la ruta de fallback sin depender de si la
    # BD compartida con pytest ya tenía la fila o no (ver CLAUDE.md, "BD de
    # desarrollo... es la MISMA que usa pytest").
    await db_session.execute(
        delete(CatParametroSistema).where(CatParametroSistema.clave == "obd_modelo_minimo")
    )
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.get("/api/parametros", headers={"X-Session-Id": str(sup.id)})

    assert resp.status_code == 200
    por_clave = {p["clave"]: p for p in resp.json()}
    assert por_clave["obd_modelo_minimo"]["valor"] == "2006"
    assert por_clave["obd_modelo_minimo"]["origen"] == "default"


async def test_actualizar_parametro_obd_modelo_minimo_ida_y_vuelta(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}

    resp = await client.patch("/api/parametros/obd_modelo_minimo", headers=h, json={"valor": "2010"})
    assert resp.status_code == 200
    assert resp.json()["valor"] == "2010"
    assert resp.json()["origen"] == "catalogo"

    resp = await client.get("/api/parametros", headers=h)
    por_clave = {p["clave"]: p for p in resp.json()}
    assert por_clave["obd_modelo_minimo"]["valor"] == "2010"
    assert por_clave["obd_modelo_minimo"]["origen"] == "catalogo"


async def test_actualizar_parametro_valor_invalido_rechaza(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}

    resp = await client.patch("/api/parametros/obd_modelo_minimo", headers=h, json={"valor": "no-es-un-año"})
    assert resp.status_code == 422

    resp = await client.patch(
        "/api/parametros/gasolina_permite_cambio_estatica", headers=h, json={"valor": "tal-vez"}
    )
    assert resp.status_code == 422


async def test_actualizar_parametro_clave_desconocida_responde_404(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.patch(
        "/api/parametros/clave_inventada",
        headers={"X-Session-Id": str(sup.id)},
        json={"valor": "x"},
    )
    assert resp.status_code == 404


async def test_obd_aplica_usa_el_valor_actualizado(client, db_session):
    from app.services.parametros import obd_aplica

    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.patch(
        "/api/parametros/obd_modelo_minimo",
        headers={"X-Session-Id": str(sup.id)},
        json={"valor": "2015"},
    )
    assert resp.status_code == 200

    aplica_2010 = await obd_aplica(
        db_session,
        inspeccion_aprobada=True,
        tipo_vehiculo="vehiculo",
        combustible="gasolina",
        modelo=2010,
    )
    aplica_2016 = await obd_aplica(
        db_session,
        inspeccion_aprobada=True,
        tipo_vehiculo="vehiculo",
        combustible="gasolina",
        modelo=2016,
    )
    assert aplica_2010 is False
    assert aplica_2016 is True
