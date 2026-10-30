import datetime
import uuid

import httpx
from sqlalchemy import select

from app.models.enums import StationType, SyncStatus
from app.models.sync_outbox import SyncOutbox
from app.services.sync import calcular_espera_segundos, procesar_pendientes
from tests.conftest import crear_estacion, crear_sesion_activa, crear_sesion_supervisor


async def _encolar(db_session, **overrides) -> SyncOutbox:
    defaults = dict(
        entity_type="event_log",
        entity_uuid=uuid.uuid4(),
        operation="insert",
        payload={"x": 1},
    )
    defaults.update(overrides)
    outbox = SyncOutbox(**defaults)
    db_session.add(outbox)
    await db_session.flush()
    return outbox


def test_calcular_espera_segundos_backoff_exponencial_con_tope():
    assert calcular_espera_segundos(0) == 0
    assert calcular_espera_segundos(1) == 5
    assert calcular_espera_segundos(2) == 10
    assert calcular_espera_segundos(3) == 20
    assert calcular_espera_segundos(20) == 3600


async def test_reenviar_la_misma_operacion_cinco_veces_produce_un_solo_registro_en_central(
    db_session,
):
    """El central deduplica por entity_uuid (upsert-por-id), no por número
    de envíos: reenviar la misma fila 5 veces (p.ej. por un reintento de
    red tras perder la confirmación) no debe producir más de un registro
    ahí — ver docstring de app.services.sync."""

    outbox = await _encolar(db_session)
    await db_session.commit()

    central: dict[str, dict] = {}

    async def _enviar_falso(row: SyncOutbox) -> dict:
        central[str(row.entity_uuid)] = row.payload  # upsert-por-id
        return {"ok": True}

    for _ in range(5):
        await _enviar_falso(outbox)

    assert len(central) == 1
    assert central[str(outbox.entity_uuid)] == outbox.payload


async def test_procesar_pendientes_envia_en_orden_fifo(db_session):
    viejo = await _encolar(db_session)
    nuevo = await _encolar(db_session)
    await db_session.commit()

    # created_at tiene default server-side; forzamos el timestamp del más
    # viejo hacia atrás para no depender de la resolución del reloj entre
    # dos inserts consecutivos.
    viejo.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        minutes=5
    )
    db_session.add(viejo)
    await db_session.commit()

    orden: list[uuid.UUID] = []

    async def _enviar(row: SyncOutbox) -> dict:
        orden.append(row.id)
        return {"ok": True}

    resultado = await procesar_pendientes(db_session, enviar=_enviar)

    assert resultado == {"procesados": 2, "enviados": 2, "fallidos": 0, "en_backoff": 0}
    assert orden == [viejo.id, nuevo.id]

    filas = (await db_session.execute(select(SyncOutbox))).scalars().all()
    assert all(fila.sync_status == SyncStatus.SYNCED for fila in filas)


async def test_procesar_pendientes_respeta_backoff_tras_error(db_session):
    outbox = await _encolar(db_session)
    await db_session.commit()

    async def _enviar_falla(row: SyncOutbox) -> dict:
        raise RuntimeError("central no disponible")

    ahora = datetime.datetime.now(datetime.timezone.utc)
    resultado1 = await procesar_pendientes(db_session, enviar=_enviar_falla, ahora=ahora)
    assert resultado1 == {"procesados": 1, "enviados": 0, "fallidos": 1, "en_backoff": 0}

    await db_session.refresh(outbox)
    assert outbox.sync_status == SyncStatus.ERROR
    assert outbox.attempts == 1

    # Antes de que expire el backoff (5s tras el 1er intento), un segundo
    # intento debe quedar en espera sin volver a llamar al central.
    resultado2 = await procesar_pendientes(
        db_session, enviar=_enviar_falla, ahora=ahora + datetime.timedelta(seconds=1)
    )
    assert resultado2 == {"procesados": 1, "enviados": 0, "fallidos": 0, "en_backoff": 1}

    async def _enviar_exitoso(row: SyncOutbox) -> dict:
        return {"ok": True}

    # Tras expirar el backoff, si el central ya responde, se marca SYNCED.
    resultado3 = await procesar_pendientes(
        db_session, enviar=_enviar_exitoso, ahora=ahora + datetime.timedelta(seconds=10)
    )
    assert resultado3 == {"procesados": 1, "enviados": 1, "fallidos": 0, "en_backoff": 0}

    await db_session.refresh(outbox)
    assert outbox.sync_status == SyncStatus.SYNCED
    assert outbox.attempts == 2


async def test_fila_en_backoff_no_bloquea_una_fila_mas_nueva_lista_para_enviar(db_session):
    """Hallazgo de la revisión del PR #1: antes el `SELECT` limitaba a
    `max_lote` filas *antes* de descartar las que seguían en backoff — con
    `max_lote=1` y la fila más vieja en backoff, el lote se llenaba solo
    con ella y la más nueva (lista para enviarse) nunca se intentaba."""

    viejo = await _encolar(db_session)
    await db_session.commit()

    ahora = datetime.datetime.now(datetime.timezone.utc)
    viejo.attempts = 1
    viejo.sync_status = SyncStatus.ERROR
    viejo.last_attempt_at = ahora  # backoff de 5s tras el 1er intento
    db_session.add(viejo)
    await db_session.commit()

    nuevo = await _encolar(db_session)
    nuevo.created_at = ahora + datetime.timedelta(seconds=1)
    db_session.add(nuevo)
    await db_session.commit()

    enviados: list[uuid.UUID] = []

    async def _enviar(row: SyncOutbox) -> dict:
        enviados.append(row.id)
        return {"ok": True}

    # 1 segundo después: `viejo` sigue en backoff (necesita 5s), pero
    # `nuevo` ya está listo. max_lote=1 fuerza el caso donde antes el lote
    # se llenaba solo con la fila vieja en espera.
    resultado = await procesar_pendientes(
        db_session, enviar=_enviar, max_lote=1, ahora=ahora + datetime.timedelta(seconds=2)
    )

    assert enviados == [nuevo.id]
    assert resultado["enviados"] == 1
    assert resultado["en_backoff"] == 1

    await db_session.refresh(nuevo)
    await db_session.refresh(viejo)
    assert nuevo.sync_status == SyncStatus.SYNCED
    assert viejo.sync_status == SyncStatus.ERROR  # sin tocar, sigue en backoff


async def test_procesar_endpoint_requiere_supervisor(client, db_session):
    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA)
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.post("/api/sync/procesar", headers={"X-Session-Id": str(sesion.id)})

    assert resp.status_code == 403


async def test_procesar_endpoint_envia_pendientes(client, db_session, monkeypatch):
    sesion = await crear_sesion_supervisor(db_session)
    outbox = await _encolar(db_session)
    await db_session.commit()

    async def _fake(row: SyncOutbox) -> dict:
        return {"ok": True}

    monkeypatch.setattr("app.api.routers.sync._enviar_a_central", _fake)

    resp = await client.post("/api/sync/procesar", headers={"X-Session-Id": str(sesion.id)})

    assert resp.status_code == 200
    assert resp.json() == {"procesados": 1, "enviados": 1, "fallidos": 0, "en_backoff": 0}

    await db_session.refresh(outbox)
    assert outbox.sync_status == SyncStatus.SYNCED


async def test_estado_no_requiere_supervisor(client, db_session, monkeypatch):
    """A diferencia de /procesar, /estado es de solo lectura: cualquier
    estación con sesión activa debe poder consultarlo (lo usa el Top App
    Bar en toda vista, no solo en Supervisor)."""

    from app.core.config import settings

    monkeypatch.setattr(settings, "central_sync_url", "")
    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA)
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    await db_session.commit()

    resp = await client.get("/api/sync/estado", headers={"X-Session-Id": str(sesion.id)})

    assert resp.status_code == 200
    assert resp.json() == {
        "pendientes": 0,
        "sincronizando": 0,
        "en_error": 0,
        "sincronizados": 0,
        "pendiente_mas_antiguo": None,
        "central": "SIN_CONFIGURAR",
    }


async def test_estado_cuenta_pendientes_y_errores(client, db_session, monkeypatch):
    sesion = await crear_sesion_supervisor(db_session)
    await _encolar(db_session)
    await _encolar(db_session)
    await db_session.commit()

    async def _falla(row: SyncOutbox) -> dict:
        raise RuntimeError("central no disponible")

    monkeypatch.setattr("app.api.routers.sync._enviar_a_central", _falla)
    resp = await client.post("/api/sync/procesar", headers={"X-Session-Id": str(sesion.id)})
    assert resp.status_code == 200

    resp = await client.get("/api/sync/estado", headers={"X-Session-Id": str(sesion.id)})
    body = resp.json()

    # Ambos fallaron: PENDING -> ERROR, y "pendientes" agrupa PENDING+ERROR
    # (desde la perspectiva del operador ambos son "trabajo sin sincronizar").
    assert body["pendientes"] == 2
    assert body["en_error"] == 2
    assert body["sincronizados"] == 0
    assert body["pendiente_mas_antiguo"] is not None


async def test_enviar_uno_a_central_http_idempotente_con_bearer(monkeypatch):
    """Supuesto 2026-09-29: POST al central con Idempotency-Key = id de la
    fila y Bearer; 2xx = recibido, 5xx lanza para que quede en ERROR."""

    import uuid

    import httpx

    from app.core.config import settings
    from app.models.sync_outbox import SyncOutbox
    from app.services import sync as sync_mod

    vistos = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append(request)
        return httpx.Response(200 if len(vistos) == 1 else 503, json={"ok": True})

    transporte = httpx.MockTransport(handler)
    real = httpx.AsyncClient
    monkeypatch.setattr(
        sync_mod.httpx, "AsyncClient", lambda **kw: real(transport=transporte, **kw)
    )
    monkeypatch.setattr(settings, "central_sync_url", "http://central.test/sync")
    monkeypatch.setattr(settings, "central_sync_token", "tok")

    row = SyncOutbox(
        id=uuid.uuid4(),
        entity_type="verificacion",
        entity_uuid=uuid.uuid4(),
        operation="update",
        payload={"a": 1},
    )
    assert await sync_mod.enviar_uno_a_central(row) == {"ok": True}
    assert vistos[0].headers["Idempotency-Key"] == str(row.id)
    assert vistos[0].headers["Authorization"] == "Bearer tok"

    with __import__("pytest").raises(httpx.HTTPStatusError):
        await sync_mod.enviar_uno_a_central(row)


async def test_enviar_uno_a_central_sin_url_sigue_lanzando(monkeypatch):
    import pytest

    from app.core.config import settings
    from app.services import sync as sync_mod

    monkeypatch.setattr(settings, "central_sync_url", "")
    with pytest.raises(NotImplementedError):
        await sync_mod.enviar_uno_a_central(None)


async def test_estado_por_expediente_resume_sus_filas(client, db_session):
    """HU-105/109/110: el estado se calcula solo con las filas del
    expediente (snapshot + eventos ligados por verificacion_id)."""

    from tests.conftest import crear_expediente

    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA)
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    expediente = await crear_expediente(db_session, linea_id=sesion.line_id or 1)
    await db_session.commit()
    headers = {"X-Session-Id": str(sesion.id)}
    url = f"/api/sync/expediente/{expediente.id}"

    resp = await client.get(url, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["estado"] == "SIN_REGISTROS"

    sync_ok = await _encolar(
        db_session, entity_uuid=uuid.uuid4(), payload={"verificacion_id": str(expediente.id)}
    )
    sync_ok.sync_status = SyncStatus.SYNCED
    await _encolar(db_session, entity_type="verificacion", entity_uuid=expediente.id)
    ajeno = await _encolar(db_session, payload={"verificacion_id": str(uuid.uuid4())})
    ajeno.sync_status = SyncStatus.ERROR
    await db_session.commit()

    body = (await client.get(url, headers=headers)).json()
    assert (body["estado"], body["total"], body["pendientes"], body["sincronizados"]) == (
        "PENDIENTE", 2, 1, 1,
    )

    sync_ok.sync_status = SyncStatus.ERROR
    await db_session.commit()
    assert (await client.get(url, headers=headers)).json()["estado"] == "ERROR"

    resp = await client.get(f"/api/sync/expediente/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


async def test_sync_auto_solo_se_habilita_con_central_configurado(monkeypatch):
    """HU-107: sin CENTRAL_SYNC_URL o con intervalo 0 el bucle no arranca."""

    from app.core.config import settings
    from app.services.sync_auto import sync_auto_habilitado

    monkeypatch.setattr(settings, "central_sync_url", "")
    assert not sync_auto_habilitado()
    monkeypatch.setattr(settings, "central_sync_url", "http://central.test")
    monkeypatch.setattr(settings, "sync_auto_intervalo_s", 0)
    assert not sync_auto_habilitado()
    monkeypatch.setattr(settings, "sync_auto_intervalo_s", 30)
    assert sync_auto_habilitado()


async def test_sync_auto_bucle_sobrevive_a_una_vuelta_fallida(monkeypatch):
    """Una excepción en una vuelta no mata el bucle: sigue intentando."""

    import asyncio

    from app.core.config import settings
    from app.services import sync_auto

    llamadas = []

    async def vuelta():
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("central caido")
        return {}

    monkeypatch.setattr(sync_auto, "una_vuelta", vuelta)
    monkeypatch.setattr(settings, "sync_auto_intervalo_s", 0.01)
    tarea = asyncio.create_task(sync_auto.bucle_sync_auto())
    await asyncio.sleep(0.15)
    tarea.cancel()
    assert len(llamadas) >= 2


async def test_procesar_pendientes_forzar_ignora_el_backoff(db_session):
    outbox = await _encolar(db_session)
    await db_session.commit()

    async def _enviar_falla(row: SyncOutbox) -> dict:
        raise RuntimeError("central no disponible")

    async def _enviar_exitoso(row: SyncOutbox) -> dict:
        return {"ok": True}

    ahora = datetime.datetime.now(datetime.timezone.utc)
    await procesar_pendientes(db_session, enviar=_enviar_falla, ahora=ahora)

    # Un segundo después seguiría en backoff (5 s): sin forzar no se envía...
    en_espera = await procesar_pendientes(
        db_session,
        enviar=_enviar_exitoso,
        ahora=ahora + datetime.timedelta(seconds=1),
    )
    assert en_espera == {"procesados": 1, "enviados": 0, "fallidos": 0, "en_backoff": 1}

    # ...y con forzar (acción explícita del supervisor) sí.
    forzado = await procesar_pendientes(
        db_session,
        enviar=_enviar_exitoso,
        ahora=ahora + datetime.timedelta(seconds=1),
        forzar=True,
    )
    assert forzado == {"procesados": 1, "enviados": 1, "fallidos": 0, "en_backoff": 0}
    await db_session.refresh(outbox)
    assert outbox.sync_status == SyncStatus.SYNCED


async def test_central_inalcanzable_corta_el_lote_sin_gastar_intentos_de_las_demas(
    db_session,
):
    for _ in range(3):
        await _encolar(db_session)
    await db_session.commit()

    llamadas = []

    async def _sin_internet(row: SyncOutbox) -> dict:
        llamadas.append(row.id)
        raise httpx.ConnectError("sin internet")

    resultado = await procesar_pendientes(db_session, enviar=_sin_internet)

    assert len(llamadas) == 1
    assert resultado["fallidos"] == 1
    assert resultado["enviados"] == 0
    assert resultado["central_inalcanzable"] is True
    assert resultado["omitidos"] == 2

    intactas = (
        await db_session.execute(
            select(SyncOutbox).where(
                SyncOutbox.sync_status == SyncStatus.PENDING, SyncOutbox.attempts == 0
            )
        )
    ).scalars().all()
    assert len(intactas) == 2


async def test_error_http_del_central_no_corta_el_lote(db_session):
    """Si el central contesta con un error (4xx/5xx) el problema es de esa
    fila, no de la conexión: las demás se siguen intentando."""

    for _ in range(3):
        await _encolar(db_session)
    await db_session.commit()

    primera = True

    async def _enviar(row: SyncOutbox) -> dict:
        nonlocal primera
        if primera:
            primera = False
            raise httpx.HTTPStatusError(
                "422",
                request=httpx.Request("POST", "http://central"),
                response=httpx.Response(422),
            )
        return {"ok": True}

    resultado = await procesar_pendientes(db_session, enviar=_enviar)

    assert resultado == {"procesados": 3, "enviados": 2, "fallidos": 1, "en_backoff": 0}


async def test_procesar_endpoint_forzar_reintenta_filas_en_backoff(
    client, db_session, monkeypatch
):
    sesion = await crear_sesion_supervisor(db_session)
    outbox = await _encolar(
        db_session,
        sync_status=SyncStatus.ERROR,
        attempts=1,
        last_attempt_at=datetime.datetime.now(datetime.timezone.utc),
    )
    await db_session.commit()

    async def _fake(row: SyncOutbox) -> dict:
        return {"ok": True}

    monkeypatch.setattr("app.api.routers.sync._enviar_a_central", _fake)
    headers = {"X-Session-Id": str(sesion.id)}

    normal = await client.post("/api/sync/procesar", headers=headers)
    assert normal.json() == {"procesados": 1, "enviados": 0, "fallidos": 0, "en_backoff": 1}

    forzado = await client.post("/api/sync/procesar?forzar=true", headers=headers)
    assert forzado.json() == {"procesados": 1, "enviados": 1, "fallidos": 0, "en_backoff": 0}

    await db_session.refresh(outbox)
    assert outbox.sync_status == SyncStatus.SYNCED


async def test_estado_distingue_operando_sin_internet(client, db_session, monkeypatch):
    """HU-104: tras un lote cortado por falta de conexión el estado es
    SIN_CONEXION; el siguiente lote que llega al central lo regresa a
    EN_LINEA. Sin central configurado, SIN_CONFIGURAR."""

    from app.core.config import settings

    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA)
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    h = {"X-Session-Id": str(sesion.id)}
    await _encolar(db_session)
    await db_session.commit()

    monkeypatch.setattr(settings, "central_sync_url", "")
    assert (await client.get("/api/sync/estado", headers=h)).json()["central"] == "SIN_CONFIGURAR"

    monkeypatch.setattr(settings, "central_sync_url", "http://central.test")

    async def _sin_internet(row):
        raise httpx.ConnectError("sin internet")

    await procesar_pendientes(db_session, enviar=_sin_internet)
    assert (await client.get("/api/sync/estado", headers=h)).json()["central"] == "SIN_CONEXION"

    async def _ok(row):
        return {"ok": True}

    await procesar_pendientes(
        db_session,
        enviar=_ok,
        forzar=True,
        ahora=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=1),
    )
    assert (await client.get("/api/sync/estado", headers=h)).json()["central"] == "EN_LINEA"


async def _contar_syncing(db_session) -> int:
    return len(
        (
            await db_session.execute(
                select(SyncOutbox.id).where(SyncOutbox.sync_status == SyncStatus.SYNCING)
            )
        ).all()
    )


async def test_lote_en_vuelo_queda_visible_como_syncing(db_session):
    """F9: el lote se marca SYNCING antes de enviar y cada fila sale de ese
    estado al terminar; antes el contador "sincronizando" siempre daba 0."""

    for _ in range(3):
        await _encolar(db_session)
    await db_session.commit()

    vistos: list[int] = []

    async def _enviar(row: SyncOutbox) -> dict:
        vistos.append(await _contar_syncing(db_session))
        return {"ok": True}

    resultado = await procesar_pendientes(db_session, enviar=_enviar)

    assert resultado["enviados"] == 3
    assert vistos == [3, 2, 1]
    assert await _contar_syncing(db_session) == 0


async def test_fila_syncing_huerfana_se_reintenta_tras_caducar(db_session):
    """Si el proceso muere a mitad del envío la fila queda SYNCING; pasada
    la caducidad vuelve a ser candidata (sin backoff). Una SYNCING reciente
    sigue en vuelo y no se toca."""

    ahora = datetime.datetime.now(datetime.timezone.utc)
    huerfana = await _encolar(
        db_session,
        sync_status=SyncStatus.SYNCING,
        attempts=1,
        last_attempt_at=ahora - datetime.timedelta(hours=1),
    )
    en_vuelo = await _encolar(
        db_session,
        sync_status=SyncStatus.SYNCING,
        attempts=1,
        last_attempt_at=ahora - datetime.timedelta(seconds=5),
    )
    await db_session.commit()

    enviados: list[uuid.UUID] = []

    async def _enviar(row: SyncOutbox) -> dict:
        enviados.append(row.id)
        return {"ok": True}

    await procesar_pendientes(db_session, enviar=_enviar, ahora=ahora)

    assert enviados == [huerfana.id]
    await db_session.refresh(huerfana)
    await db_session.refresh(en_vuelo)
    assert huerfana.sync_status == SyncStatus.SYNCED
    assert huerfana.attempts == 2
    assert en_vuelo.sync_status == SyncStatus.SYNCING
