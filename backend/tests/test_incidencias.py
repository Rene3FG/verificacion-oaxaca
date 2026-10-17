"""Pestaña 'Errores y reintentos' (auditoría de Sebastián 2026-10-12, Figma
#66:2950): incidencias abiertas del centro, derivadas del estado real."""

from sqlalchemy import func, select

from app.models.enums import EstadoVerificacion, StationType, SyncStatus
from app.models.event_log import EventLog
from app.models.print_attempt import PrintAttempt
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


def _ids(resp):
    return {i["expediente_id"] for i in resp.json()}


async def _fallida_lista_para_reintentar(db_session, *, intentos_previos=2):
    """IMPRESION_FALLIDA con PrintJob y N PrintAttempt fallidos reales
    (intentos se recalcula por conteo de filas, no por el campo)."""
    exp = await _impresion_fallida(db_session)
    exp.certificado_tipo = "PARTICULAR"
    job = (
        await db_session.execute(select(PrintJob).where(PrintJob.verificacion_id == exp.id))
    ).scalar_one()
    for _ in range(intentos_previos):
        db_session.add(
            PrintAttempt(print_job_id=job.id, verificacion_id=exp.id, exitoso=False, error_message="fallo")
        )
    await db_session.commit()
    return exp


async def test_reintento_secuencial_de_dos_supervisores_imprime_una_sola_vez(
    client, db_session, monkeypatch
):
    """El segundo supervisor llega con el expediente ya IMPRESO: 409 y sin
    segundo PrintAttempt. (Con la sesión única de la fixture no hay
    concurrencia real; la serialización la da el FOR UPDATE.)"""
    sup1 = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    sup2 = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    exp = await _fallida_lista_para_reintentar(db_session)

    async def _ok(pdf_bytes: bytes) -> bool:
        return True

    monkeypatch.setattr("app.api.routers.impresion.imprimir_en_impresora", _ok)

    r1 = await client.post(f"/api/impresion/imprimir/{exp.id}", headers={"X-Session-Id": str(sup1.id)})
    r2 = await client.post(f"/api/impresion/imprimir/{exp.id}", headers={"X-Session-Id": str(sup2.id)})

    assert r1.status_code == 200
    assert r1.json()["estado_expediente"] == EstadoVerificacion.IMPRESO.value
    assert r2.status_code == 409
    total = (
        await db_session.execute(
            select(func.count()).select_from(PrintAttempt).where(PrintAttempt.verificacion_id == exp.id)
        )
    ).scalar_one()
    assert total == 3  # 2 previos + 1 exitoso, ninguno duplicado

    sup = await crear_sesion_supervisor(db_session)
    inc = await client.get(URL, headers={"X-Session-Id": str(sup.id)})
    assert str(exp.id) not in _ids(inc)


async def test_reintento_fallido_incrementa_intentos_y_la_incidencia_sigue_abierta(
    client, db_session, monkeypatch
):
    sup = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    exp = await _fallida_lista_para_reintentar(db_session)

    async def _falla(pdf_bytes: bytes) -> bool:
        return False

    monkeypatch.setattr("app.api.routers.impresion.imprimir_en_impresora", _falla)

    r = await client.post(f"/api/impresion/imprimir/{exp.id}", headers={"X-Session-Id": str(sup.id)})
    assert r.status_code == 200
    assert r.json()["estado_expediente"] == EstadoVerificacion.IMPRESION_FALLIDA.value
    assert r.json()["intentos"] == 3

    inc = await client.get(URL, headers={"X-Session-Id": str(sup.id)})
    fila = next(i for i in inc.json() if i["expediente_id"] == str(exp.id))
    assert fila["intentos"] == 3
    assert fila["accion"] == "REINTENTAR_IMPRESION"


async def test_folio_error_se_cierra_al_registrar_lote_y_solicitar(client, db_session):
    sup = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    exp = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ERROR
    )
    exp.certificado_tipo = "PARTICULAR"
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}

    antes = await client.get(URL, headers=h)
    assert str(exp.id) in _ids(antes)

    lote = await client.post(
        "/api/folios/lotes",
        params={"tipo_certificado": "PARTICULAR", "folio_inicio": "INC-900001", "folio_fin": "INC-900002"},
        headers=h,
    )
    assert lote.status_code == 200
    # Registrar el lote solo no cierra la incidencia: el expediente sigue en FOLIO_ERROR.
    medio = await client.get(URL, headers=h)
    assert str(exp.id) in _ids(medio)

    sol = await client.post(
        f"/api/folios/solicitar/{exp.id}", params={"tipo_certificado": "PARTICULAR"}, headers=h
    )
    assert sol.status_code == 200
    assert sol.json()["estado_expediente"] == EstadoVerificacion.FOLIO_ASIGNADO.value

    despues = await client.get(URL, headers=h)
    assert str(exp.id) not in _ids(despues)
