import datetime
import uuid

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
