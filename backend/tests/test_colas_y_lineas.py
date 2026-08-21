from app.models.enums import EstadoVerificacion, StationType
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa


async def test_cola_prueba_deriva_de_la_sesion(client, db_session):
    """HU-002: la línea sale de la sesión, no de la URL."""

    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)

    de_mi_linea = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.LISTO_PARA_PRUEBA
    )
    await crear_expediente(
        db_session, linea_id=2, estado=EstadoVerificacion.LISTO_PARA_PRUEBA
    )
    # Misma línea (1), pero de OTRO centro: el número de línea es local a
    # cada centro, así que esto no debe aparecer en la cola de OAX-01.
    await crear_expediente(
        db_session, centro_id="reforma", linea_id=1, estado=EstadoVerificacion.LISTO_PARA_PRUEBA
    )
    await db_session.commit()

    resp = await client.get(
        "/api/pruebas/cola", headers={"X-Session-Id": str(sesion.id)}
    )

    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    assert ids == {str(de_mi_linea.id)}


async def test_pruebas_cola_ya_no_acepta_linea_por_url(client, db_session):
    """Antes /api/pruebas/cola/{linea_id} dejaba que una estación de línea 1
    pidiera la cola de la línea 2 cambiando la URL. Esa ruta ya no existe."""

    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.get(
        "/api/pruebas/cola/2", headers={"X-Session-Id": str(sesion.id)}
    )

    assert resp.status_code == 404


async def test_operar_expediente_de_otra_linea_responde_403(client, db_session):
    """HU-008: el mensaje de error debe ser exactamente el especificado."""

    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    expediente_ajeno = await crear_expediente(
        db_session, linea_id=2, estado=EstadoVerificacion.LISTO_PARA_PRUEBA
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/pruebas/iniciar/{expediente_ajeno.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == "Acceso denegado. Este expediente pertenece a otra línea."


async def test_operar_expediente_de_otro_centro_misma_linea_responde_403(client, db_session):
    """El número de línea es local a cada centro: una "línea 1" del centro
    A y una "línea 1" del centro B son cosas distintas. Antes
    `assert_linea_permitida` solo comparaba el número de línea, así que
    esto no daba 403."""

    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    expediente_otro_centro = await crear_expediente(
        db_session, centro_id="reforma", linea_id=1, estado=EstadoVerificacion.LISTO_PARA_PRUEBA
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/pruebas/iniciar/{expediente_otro_centro.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == "Acceso denegado. Este expediente pertenece a otra línea."


async def test_impresion_cola_limitada_a_allowed_line_ids(client, db_session):
    """HU-003/009: Impresión Central solo ve las líneas de allowed_line_ids,
    nunca todas las líneas del sistema."""

    estacion = await crear_estacion(
        db_session,
        station_type=StationType.IMPRESION,
        center_id="OAX-01",
        line_id=None,
        is_centralized=True,
        allowed_line_ids=[1, 2],
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)

    linea_1 = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    linea_2 = await crear_expediente(
        db_session, linea_id=2, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await crear_expediente(
        db_session, linea_id=3, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    # Misma línea (1) que sí está permitida, pero de otro centro: no debe
    # aparecer en la cola de una estación centralizada de OAX-01.
    await crear_expediente(
        db_session, centro_id="reforma", linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp = await client.get(
        "/api/impresion/cola", headers={"X-Session-Id": str(sesion.id)}
    )

    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    assert ids == {str(linea_1.id), str(linea_2.id)}


async def test_impresion_filtro_linea_no_puede_ampliar_acceso(client, db_session):
    """El filtro ?linea_id= solo puede estrechar el conjunto permitido,
    nunca ampliarlo: pedir una línea fuera de allowed_line_ids no debe
    devolver nada de esa línea."""

    estacion = await crear_estacion(
        db_session,
        station_type=StationType.IMPRESION,
        center_id="OAX-01",
        line_id=None,
        is_centralized=True,
        allowed_line_ids=[1],
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await crear_expediente(
        db_session, linea_id=5, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp = await client.get(
        "/api/impresion/cola?linea_id=5", headers={"X-Session-Id": str(sesion.id)}
    )

    assert resp.status_code == 200
    assert resp.json() == []


async def test_sin_session_id_responde_401(client, db_session):
    resp = await client.get("/api/pruebas/cola")
    assert resp.status_code in (401, 422)
