from app.models.enums import EstadoVerificacion, FuenteDatos, StationType
from app.models.event_log import EventLog
from app.models.vehiculo import Vehiculo
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa


async def test_crear_expediente_hereda_centro_y_linea_de_la_sesion(client, db_session):
    """HU-019/HU-018: centro_id y linea_id nunca se aceptan del payload,
    salen de la sesión de la estación de Captura."""

    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=3
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.post(
        "/api/expedientes",
        json={"placa": "ABC123"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["placa"] == "ABC123"
    assert body["centro_id"] == "OAX-01"
    assert body["linea_id"] == 3
    assert body["estado"] == EstadoVerificacion.CREADO.value


async def test_crear_expediente_ignora_linea_del_payload(client, db_session):
    """Aunque el cliente mande linea_id en el body, ExpedienteCreate no lo
    acepta: solo cuenta lo que diga la sesión."""

    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=3
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.post(
        "/api/expedientes",
        json={"placa": "ABC123", "linea_id": 99, "centro_id": "OAX-99"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["linea_id"] == 3
    assert body["centro_id"] == "OAX-01"


async def test_crear_expediente_desde_estacion_de_prueba_responde_403(client, db_session):
    """HU-019: solo Captura abre expedientes; Prueba e Impresión no."""

    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.post(
        "/api/expedientes",
        json={"placa": "ABC123"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 403


async def test_crear_expediente_sin_session_id_responde_401(client, db_session):
    resp = await client.post("/api/expedientes", json={"placa": "ABC123"})
    assert resp.status_code in (401, 422)


async def _sesion_captura(db_session, *, line_id: int = 1):
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=line_id
    )
    return await crear_sesion_activa(db_session, estacion=estacion)


async def test_normalizar_desde_datos_siox_importados_llega_a_inspeccion_pendiente(
    client, db_session
):
    """Decisión 2026-08-07: la normalización es una confirmación manual del
    operador de Captura, no automática."""

    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.DATOS_SIOX_IMPORTADOS,
        combustible="GASOLINA",
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/expedientes/{expediente.id}/normalizar",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["estado"] == EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE.value


async def test_normalizar_desde_datos_capturados_manualmente_llega_a_inspeccion_pendiente(
    client, db_session
):
    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.DATOS_CAPTURADOS_MANUALMENTE,
        combustible="DIESEL",
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/expedientes/{expediente.id}/normalizar",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["estado"] == EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE.value


async def test_normalizar_desde_estado_no_valido_responde_409(client, db_session):
    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.CREADO
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/expedientes/{expediente.id}/normalizar",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 409


async def test_actualizar_vehiculo_solo_toca_campos_enviados(client, db_session):
    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(db_session, linea_id=1)
    await db_session.commit()

    resp = await client.patch(
        f"/api/expedientes/{expediente.id}/vehiculo",
        json={"marca": "NISSAN", "modelo": 2023},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["marca"] == "NISSAN"
    assert body["modelo"] == 2023
    assert body["niv"] is None
    # No venía de SIOX, así que corregir a mano no cambia la fuente.
    assert body["fuente_datos"] == FuenteDatos.MANUAL.value


async def test_actualizar_vehiculo_corregido_marca_fuente_corregido_operador(
    client, db_session
):
    """HU-016: si el dato corregido venía de SIOX, fuente_datos pasa a
    CORREGIDO_OPERADOR."""

    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(db_session, linea_id=1)
    vehiculo = await db_session.get(Vehiculo, expediente.vehiculo_id)
    vehiculo.marca = "NISSAN"
    vehiculo.fuente_datos = FuenteDatos.SIOX
    db_session.add(vehiculo)
    await db_session.commit()

    resp = await client.patch(
        f"/api/expedientes/{expediente.id}/vehiculo",
        json={"marca": "CHEVROLET"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["marca"] == "CHEVROLET"
    assert body["fuente_datos"] == FuenteDatos.CORREGIDO_OPERADOR.value

    evento = (
        await db_session.execute(
            EventLog.__table__.select().where(
                EventLog.verificacion_id == expediente.id,
                EventLog.evento == "datos_vehiculo_corregidos",
            )
        )
    ).mappings().one()
    assert evento["detalle_json"]["campos_modificados"]["marca"] == {
        "anterior": "NISSAN",
        "nuevo": "CHEVROLET",
    }
    assert evento["detalle_json"]["fuente_datos_anterior"] == FuenteDatos.SIOX.value
    assert evento["detalle_json"]["fuente_datos_nueva"] == FuenteDatos.CORREGIDO_OPERADOR.value


async def test_actualizar_vehiculo_sin_cambios_no_escribe_evento(client, db_session):
    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(db_session, linea_id=1)
    await db_session.commit()

    resp = await client.patch(
        f"/api/expedientes/{expediente.id}/vehiculo",
        json={},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    eventos = (
        await db_session.execute(
            EventLog.__table__.select().where(
                EventLog.verificacion_id == expediente.id,
                EventLog.evento == "datos_vehiculo_corregidos",
            )
        )
    ).mappings().all()
    assert eventos == []


async def test_actualizar_vehiculo_desde_estacion_de_prueba_responde_200(client, db_session):
    """Decisión de producto 2026-08-14: si Inspección Visual detecta un
    error en los datos del vehículo, Prueba debe poder corregirlo sin
    devolver el expediente a Captura."""

    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    expediente = await crear_expediente(db_session, linea_id=1)
    await db_session.commit()

    resp = await client.patch(
        f"/api/expedientes/{expediente.id}/vehiculo",
        json={"marca": "NISSAN"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["marca"] == "NISSAN"


async def test_actualizar_vehiculo_desde_estacion_de_impresion_responde_403(client, db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.IMPRESION, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    expediente = await crear_expediente(db_session, linea_id=1)
    await db_session.commit()

    resp = await client.patch(
        f"/api/expedientes/{expediente.id}/vehiculo",
        json={"marca": "NISSAN"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 403


async def test_actualizar_vehiculo_expediente_de_otra_linea_responde_403(client, db_session):
    sesion = await _sesion_captura(db_session, line_id=1)
    expediente_ajeno = await crear_expediente(db_session, linea_id=2)
    await db_session.commit()

    resp = await client.patch(
        f"/api/expedientes/{expediente_ajeno.id}/vehiculo",
        json={"marca": "NISSAN"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 403


async def test_normalizar_sin_combustible_responde_409(client, db_session):
    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.DATOS_SIOX_IMPORTADOS,
        combustible=None,
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/expedientes/{expediente.id}/normalizar",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 409
    assert "combustible" in resp.json()["detail"].lower()


async def test_normalizar_con_combustible_escribe_combustible_validado(client, db_session):
    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.DATOS_SIOX_IMPORTADOS,
        combustible="GASOLINA",
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/expedientes/{expediente.id}/normalizar",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["estado"] == EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE.value

    await db_session.refresh(expediente)
    assert expediente.combustible_validado == "GASOLINA"


async def test_normalizar_desde_estacion_de_prueba_responde_403(client, db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.DATOS_SIOX_IMPORTADOS
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/expedientes/{expediente.id}/normalizar",
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 403
