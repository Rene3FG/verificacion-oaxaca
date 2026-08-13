"""Etapa 12: operación sin internet.

Análisis previo (documentado en CLAUDE.md): todos los modelos usan
`UUIDPKMixin` con `default=uuid.uuid4` — el id se genera en Python al
construir el objeto, antes del INSERT, no en el servidor de Postgres. Toda
fila creada localmente ya nace con un identificador propio, global y
estable. Por eso `sync_outbox.entity_uuid` (o, para el propio registro de
cola, `SyncOutbox.id`) alcanza como clave de deduplicación: el central
puede hacer upsert-por-id sin importar cuántas veces se reenvíe la misma
fila.

Lo que SÍ hacía falta arreglar: `PrintJob.intentos` era un contador mutado
(`+= 1`), que no es idempotente bajo reenvío — reenviar el mismo evento de
sincronización lo duplicaría en el central. Ver `app/models/print_attempt.py`.

Decisión de diseño: `event_log` es el historial de verdad (append-only, un
registro inmutable por transición, ya con su propio id) y se sincroniza tal
cual. Las entidades mutables de larga vida (`Verificacion`, `PrintJob`,
`StationSession`) se sincronizan como snapshots idempotentes (SET, no
incrementos) en cada cambio relevante — se puede reenviar el mismo snapshot
sin corromper nada.

Regla de negocio: sin conexión se puede capturar y probar (todo corre
contra el Postgres local), pero no imprimir el certificado definitivo,
porque el folio requiere el sistema externo — eso ya está garantizado
estructuralmente (`folio_externo is None -> 409` en impresion.py), no por
este módulo.
"""

import datetime
import uuid
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SyncStatus
from app.models.event_log import EventLog
from app.models.sync_outbox import SyncOutbox
from app.models.verificacion import Verificacion

# Backoff exponencial: espera BACKOFF_BASE_SECONDS * 2**(attempts-1) entre
# reintentos del mismo registro pendiente.
BACKOFF_BASE_SECONDS = 5
BACKOFF_MAX_SECONDS = 3600


def calcular_espera_segundos(attempts: int) -> int:
    if attempts <= 0:
        return 0
    return min(BACKOFF_BASE_SECONDS * (2 ** (attempts - 1)), BACKOFF_MAX_SECONDS)


async def encolar_sync(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_uuid: uuid.UUID,
    operation: str,
    payload: dict,
) -> SyncOutbox:
    """Encola un cambio para sincronizar. No hace commit — el llamador ya
    está dentro de una transacción más grande (la del endpoint)."""

    outbox = SyncOutbox(
        entity_type=entity_type,
        entity_uuid=entity_uuid,
        operation=operation,
        payload=payload,
    )
    db.add(outbox)
    await db.flush()
    return outbox


def _serializar_event_log(event: EventLog) -> dict:
    return {
        "id": str(event.id),
        "verificacion_id": str(event.verificacion_id),
        "evento": event.evento,
        "estado_anterior": event.estado_anterior.value if event.estado_anterior else None,
        "estado_nuevo": event.estado_nuevo.value if event.estado_nuevo else None,
        "usuario_id": str(event.usuario_id) if event.usuario_id else None,
        "modulo": event.modulo,
        "detalle_json": event.detalle_json,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _serializar_verificacion(v: Verificacion) -> dict:
    """Snapshot idempotente: siempre el estado ACTUAL completo, nunca un
    delta. Reenviar el mismo snapshot dos veces es un no-op seguro."""

    return {
        "id": str(v.id),
        "placa": v.placa,
        "centro_id": v.centro_id,
        "linea_id": v.linea_id,
        "estado": v.estado.value,
        "combustible_validado": v.combustible_validado,
        "certificado_tipo": v.certificado_tipo,
        "folio_externo": v.folio_externo,
        "resultado_final": v.resultado_final.value if v.resultado_final else None,
        "cerrado_at": v.cerrado_at.isoformat() if v.cerrado_at else None,
    }


async def registrar_evento_con_sync(
    db: AsyncSession, event: EventLog, *, verificacion: Verificacion | None = None
) -> EventLog:
    """Reemplaza los `db.add(EventLog(...))` sueltos: agrega el evento a la
    sesión Y lo encola para sincronizar, junto con un snapshot de la
    Verificacion si se pasa (para que el central vea el estado resultante,
    no solo el evento). No hace commit."""

    db.add(event)
    await db.flush()

    await encolar_sync(
        db,
        entity_type="event_log",
        entity_uuid=event.id,
        operation="insert",
        payload=_serializar_event_log(event),
    )
    if verificacion is not None:
        await encolar_sync(
            db,
            entity_type="verificacion",
            entity_uuid=verificacion.id,
            operation="upsert",
            payload=_serializar_verificacion(verificacion),
        )
    return event


EnviarUnoACentral = Callable[[SyncOutbox], Awaitable[dict]]


async def enviar_uno_a_central(row: SyncOutbox) -> dict:
    """Stub — no hay integración real definida con un servidor central
    (mismo patrón que consultar_placa/impresora/sistema de folios: función
    inyectable, monkeypatcheable en pruebas, lista para conectar cuando
    exista el central real)."""

    raise NotImplementedError("Integración con el central aún no está definida.")


async def procesar_pendientes(
    db: AsyncSession,
    *,
    enviar: EnviarUnoACentral = enviar_uno_a_central,
    max_lote: int = 50,
    ahora: datetime.datetime | None = None,
) -> dict:
    """Envía ordenado (por created_at, FIFO) los pendientes/errados cuyo
    backoff ya expiró. Cada fila se marca SYNCED solo si `enviar` no lanza
    excepción; si falla, queda en ERROR con `attempts`/`last_attempt_at`
    actualizados para el siguiente backoff. entity_uuid/SyncOutbox.id ya
    son estables desde la creación (ver docstring del módulo), así que
    reenviar la misma fila no duplica nada del lado del central siempre que
    éste haga upsert-por-id."""

    ahora = ahora or datetime.datetime.now(datetime.timezone.utc)

    pendientes = (
        (
            await db.execute(
                select(SyncOutbox)
                .where(SyncOutbox.sync_status.in_([SyncStatus.PENDING, SyncStatus.ERROR]))
                .order_by(SyncOutbox.created_at)
                .limit(max_lote)
            )
        )
        .scalars()
        .all()
    )

    enviados = 0
    en_backoff = 0
    fallidos = 0

    for row in pendientes:
        if row.last_attempt_at is not None:
            espera = calcular_espera_segundos(row.attempts)
            transcurrido = (ahora - row.last_attempt_at).total_seconds()
            if transcurrido < espera:
                en_backoff += 1
                continue

        row.sync_status = SyncStatus.SYNCING
        row.attempts += 1
        row.last_attempt_at = ahora
        db.add(row)
        await db.flush()

        try:
            respuesta = await enviar(row)
        except Exception as exc:  # noqa: BLE001 - cualquier falla de red/central
            row.sync_status = SyncStatus.ERROR
            row.server_response = {"error": str(exc)}
            fallidos += 1
        else:
            row.sync_status = SyncStatus.SYNCED
            row.server_response = respuesta
            enviados += 1
        db.add(row)

    await db.commit()
    return {
        "procesados": len(pendientes),
        "enviados": enviados,
        "fallidos": fallidos,
        "en_backoff": en_backoff,
    }
