"""Pestaña 'Errores y reintentos' (auditoría de Sebastián 2026-10-12, Figma
#66:2950): incidencias abiertas del centro, derivadas del estado real."""

from app.models.enums import EstadoVerificacion, StationType, SyncStatus
from app.models.event_log import EventLog
from app.models.print_job import PrintJob
from app.models.sync_outbox import SyncOutbox
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa, crear_sesion_supervisor

URL = "/api/supervision/incidencias"


async def _impresion_fallida(db_session, *, linea_id=1, centro_id="OAX-01"):
    exp = await crear_expediente(
        db_session, linea_id=linea_id, centro_id=centro_id, estado=EstadoVerificacion.IMPRESION_FALLIDA
    )
    exp.folio_externo = "029303258"
    db_session.add(
        PrintJob(
            verificacion_id=exp.id,
            tipo_documento="PARTICULAR",
            folio_externo=exp.folio_externo,
            intentos=2,
            error_message="La impresora no respondió.",
        )
    )
    db_session.add(
        EventLog(
            verificacion_id=exp.id,
            evento="impresion_fallida",
            estado_anterior=EstadoVerificacion.FOLIO_ASIGNADO,
            estado_nuevo=EstadoVerificacion.IMPRESION_FALLIDA,
            modulo="impresion",
            detalle_json={"intentos": 2},
        )
    )
    await db_session.flush()
    return exp


async def test_incidencias_exige_supervisor(client, db_session):
    estacion = await crear_estacion(db_session, station_type=StationType.IMPRESION)
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.get(URL, headers={"X-Session-Id": str(sesion.id)})

    assert resp.status_code == 403


async def test_impresion_fallida_y_folio_error_del_centro(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    fallida = await _impresion_fallida(db_session)
    sin_folio = await crear_expediente(
        db_session, linea_id=2, centro_id="OAX-01", estado=EstadoVerificacion.FOLIO_ERROR
    )
    db_session.add(
        EventLog(
            verificacion_id=sin_folio.id,
            evento="folio_error",
            estado_nuevo=EstadoVerificacion.FOLIO_ERROR,
            modulo="folios",
            detalle_json={"motivo": "sin_folio_disponible", "tipo_certificado": "PARTICULAR"},
        )
    )
    await _impresion_fallida(db_session, centro_id="OAX-02")
    await crear_expediente(db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ASIGNADO)
    await db_session.commit()

    resp = await client.get(URL, headers={"X-Session-Id": str(sesion.id)})

    assert resp.status_code == 200
    por_tipo = {i["tipo"]: i for i in resp.json()}
    assert set(por_tipo) == {"IMPRESION_FALLIDA", "FOLIO_ERROR"}
    imp = por_tipo["IMPRESION_FALLIDA"]
    assert imp["expediente_id"] == str(fallida.id)
    assert imp["intentos"] == 2
    assert imp["accion"] == "REINTENTAR_IMPRESION"
    assert "folio=029303258" in imp["mensaje_tecnico"]
    assert "La impresora no respondió." in imp["mensaje_tecnico"]
    assert por_tipo["FOLIO_ERROR"]["mensaje_tecnico"] == "motivo=sin_folio_disponible · tipo=PARTICULAR"
    assert por_tipo["FOLIO_ERROR"]["accion"] == "REGISTRAR_LOTE"


async def test_sync_en_error_solo_del_centro(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    propio = await crear_expediente(db_session, linea_id=1, centro_id="OAX-01")
    ajeno = await crear_expediente(db_session, linea_id=1, centro_id="OAX-02")
    for exp in (propio, ajeno):
        db_session.add(
            SyncOutbox(
                entity_type="verificacion",
                entity_uuid=exp.id,
                operation="upsert",
                payload={},
                attempts=3,
                sync_status=SyncStatus.ERROR,
                server_response={"error": "ConnectTimeout"},
            )
        )
    await db_session.commit()

    resp = await client.get(URL, headers={"X-Session-Id": str(sesion.id)})

    sync = [i for i in resp.json() if i["tipo"] == "SYNC_ERROR"]
    assert [i["expediente_id"] for i in sync] == [str(propio.id)]
    assert sync[0]["intentos"] == 3
    assert sync[0]["mensaje_tecnico"] == "verificacion.upsert · ConnectTimeout"


async def test_filtros_linea_origen_y_busqueda(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    l1 = await _impresion_fallida(db_session, linea_id=1)
    await _impresion_fallida(db_session, linea_id=2)
    await crear_expediente(db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ERROR)
    await db_session.commit()
    h = {"X-Session-Id": str(sesion.id)}

    por_linea = (await client.get(URL, params={"linea_id": 2}, headers=h)).json()
    assert {i["linea_id"] for i in por_linea} == {2}

    por_origen = (await client.get(URL, params={"origen": "Sincronización"}, headers=h)).json()
    assert por_origen == []

    por_placa = (await client.get(URL, params={"q": l1.placa.lower()}, headers=h)).json()
    assert [i["expediente_id"] for i in por_placa] == [str(l1.id)]


async def test_incidencia_se_cierra_al_salir_del_estado_de_error(client, db_session):
    sesion = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    exp = await _impresion_fallida(db_session)
    await db_session.commit()
    h = {"X-Session-Id": str(sesion.id)}
    assert len((await client.get(URL, headers=h)).json()) == 1

    exp.estado = EstadoVerificacion.IMPRESO
    await db_session.commit()

    assert (await client.get(URL, headers=h)).json() == []
