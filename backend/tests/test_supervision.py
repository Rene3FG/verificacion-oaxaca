import datetime

from app.models.enums import EstadoVerificacion, StationType
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa, crear_sesion_supervisor


async def test_monitor_sin_supervisor_responde_403(client, db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.get("/api/supervision/monitor", headers={"X-Session-Id": str(sesion.id)})
    assert resp.status_code == 403


async def test_monitor_incluye_todas_las_lineas_del_centro(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.CREADO
    )
    await crear_expediente(
        db_session, linea_id=2, centro_id="OAX-01", estado=EstadoVerificacion.LISTO_PARA_PRUEBA
    )
    await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-02", estado=EstadoVerificacion.CREADO
    )
    await db_session.commit()

    resp = await client.get("/api/supervision/monitor", headers={"X-Session-Id": str(sesion.id)})

    assert resp.status_code == 200
    body = resp.json()
    assert {e["linea_id"] for e in body} == {1, 2}
    assert all(e["centro_id"] == "OAX-01" for e in body)


async def test_monitor_excluye_cerrados_y_cancelados(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    activo = await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.CREADO
    )
    await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.CERRADO_APROBADO
    )
    await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.CERRADO_RECHAZADO
    )
    await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.CANCELADO
    )
    await db_session.commit()

    resp = await client.get("/api/supervision/monitor", headers={"X-Session-Id": str(sesion.id)})

    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    assert ids == {str(activo.id)}


async def test_bitacora_expediente_orden_cronologico(client, db_session):
    sesion_captura = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    estacion_captura = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1
    )
    sesion_operador = await crear_sesion_activa(db_session, estacion=estacion_captura)
    expediente = await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", estado=EstadoVerificacion.CREADO
    )
    await db_session.commit()

    await client.post(
        f"/api/siox/captura-manual/{expediente.id}",
        headers={"X-Session-Id": str(sesion_operador.id)},
    )

    resp = await client.get(
        f"/api/supervision/expedientes/{expediente.id}/bitacora",
        headers={"X-Session-Id": str(sesion_captura.id)},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    assert body[0]["evento"] == "captura_manual"
    fechas = [e["created_at"] for e in body]
    assert fechas == sorted(fechas)


async def test_bitacora_de_otro_centro_responde_403(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    expediente_ajeno = await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-02", estado=EstadoVerificacion.CREADO
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/supervision/expedientes/{expediente_ajeno.id}/bitacora",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 403


async def test_buscar_expedientes_sin_supervisor_responde_403(client, db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.IMPRESION, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.get(
        "/api/supervision/expedientes/buscar",
        params={"placa": "ABC"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_buscar_expedientes_encuentra_por_placa_parcial_en_cualquier_linea(
    client, db_session
):
    """Punto de entrada 2026-09-03 para reimpresión/corrección post-
    impresión: a diferencia de la cola de Impresión y del Monitor, sí debe
    encontrar expedientes en IMPRESO/CERRADO_* (donde esas dos operaciones
    aplican), y de cualquier línea del centro, no solo la de la sesión de
    login del supervisor."""

    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01", line_id=1)
    impreso = await crear_expediente(
        db_session, linea_id=2, centro_id="OAX-01", placa="XYZ-123-A",
        estado=EstadoVerificacion.IMPRESO,
    )
    await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-01", placa="OTR-999-B",
        estado=EstadoVerificacion.CREADO,
    )
    await crear_expediente(
        db_session, linea_id=1, centro_id="OAX-02", placa="XYZ-777-C",
        estado=EstadoVerificacion.IMPRESO,
    )
    await db_session.commit()

    resp = await client.get(
        "/api/supervision/expedientes/buscar",
        params={"placa": "xyz"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    assert ids == {str(impreso.id)}


async def test_buscar_expedientes_placa_vacia_responde_422(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    await db_session.commit()

    resp = await client.get(
        "/api/supervision/expedientes/buscar",
        params={"placa": "   "},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 422


async def test_consultar_semestre_sin_supervisor_responde_403(client, db_session):
    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA)
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.get(
        "/api/supervision/semestre", headers={"X-Session-Id": str(sesion.id)}
    )
    assert resp.status_code == 403


async def test_consultar_semestre_sin_prorroga_usa_regla_base(client, db_session):
    sesion = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.get(
        "/api/supervision/semestre", headers={"X-Session-Id": str(sesion.id)}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["prorroga_activa"] is False
    assert body["fecha_final_prorroga"] is None
    hoy = datetime.date.today()
    assert body["semestre_actual"] == (1 if hoy.month <= 6 else 2)


async def test_configurar_prorroga_sin_motivo_responde_422(client, db_session):
    sesion = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.post(
        "/api/supervision/semestre/prorroga",
        json={"fecha_final": str(datetime.date.today()), "motivo": "   "},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 422


async def test_configurar_prorroga_activa_fuerza_semestre_1(client, db_session):
    sesion = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    fecha_final = datetime.date.today() + datetime.timedelta(days=30)
    resp = await client.post(
        "/api/supervision/semestre/prorroga",
        json={"fecha_final": str(fecha_final), "motivo": "Extensión autorizada por el centro"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["prorroga_activa"] is True
    assert body["semestre_actual"] == 1
    assert body["fecha_final_prorroga"] == str(fecha_final)

    consulta = await client.get(
        "/api/supervision/semestre", headers={"X-Session-Id": str(sesion.id)}
    )
    assert consulta.json()["prorroga_activa"] is True


async def test_configurar_prorroga_con_fecha_pasada_la_desactiva(client, db_session):
    """Configurar una prórroga nueva con `fecha_final` en el pasado es la
    forma de desactivar la anterior antes de tiempo (sin columna `activa`
    separada, ver docstring de `ProrrogaSemestre`)."""

    sesion = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    fecha_futura = datetime.date.today() + datetime.timedelta(days=30)
    await client.post(
        "/api/supervision/semestre/prorroga",
        json={"fecha_final": str(fecha_futura), "motivo": "Extensión inicial"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    fecha_pasada = datetime.date.today() - datetime.timedelta(days=1)
    resp = await client.post(
        "/api/supervision/semestre/prorroga",
        json={"fecha_final": str(fecha_pasada), "motivo": "Cancelación anticipada"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["prorroga_activa"] is False
