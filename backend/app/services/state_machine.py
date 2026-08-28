"""Máquina de estados del expediente (`verificaciones.estado`).

Regla central del proyecto: NINGÚN módulo debe hacer UPDATE directo sobre
`estado`. Toda transición pasa por `transition()`, que valida contra
ALLOWED_TRANSITIONS y tres efectos son atómicos con el cambio de estado:
1. escribir el nuevo estado en `verificaciones`
2. escribir la fila correspondiente en `event_log`
3. encolar ambos en `sync_outbox` para el central (Etapa 12, ver
   app/services/sync.py)

Ver Regla de negocio #11 ("prohibido saltar flujo") y la sección
"Reglas que deben quedar explícitas para desarrollo" #19 del proyecto.
"""

import datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EstadoVerificacion as E
from app.models.event_log import EventLog
from app.models.verificacion import Verificacion
from app.services.sync import registrar_evento_con_sync

TERMINAL_STATES = {E.CERRADO_APROBADO, E.CERRADO_RECHAZADO, E.CANCELADO}

ERROR_STATES = {E.ERROR_INTEGRACION, E.IMPRESION_FALLIDA, E.FOLIO_ERROR}

# Estados desde los que un supervisor puede cancelar el expediente
# (regla de negocio: no se cancela nada ya cerrado o ya impreso).
CANCELABLE_FROM = {
    E.CREADO,
    E.DATOS_SIOX_CONSULTADOS,
    E.DATOS_SIOX_IMPORTADOS,
    E.DATOS_CAPTURADOS_MANUALMENTE,
    E.DATOS_NORMALIZADOS,
    E.INSPECCION_VISUAL_PENDIENTE,
    E.INSPECCION_VISUAL_APROBADA,
    E.OBD_NO_APLICA,
    E.OBD_PENDIENTE,
    E.OBD_SOLICITADO,
    E.OBD_RECIBIDO,
    E.LISTO_PARA_PRUEBA,
    E.PRUEBA_CONFIGURADA,
    E.ERROR_INTEGRACION,
}

ALLOWED_TRANSITIONS: dict[E, set[E]] = {
    E.CREADO: {E.DATOS_SIOX_CONSULTADOS, E.DATOS_CAPTURADOS_MANUALMENTE},
    E.DATOS_SIOX_CONSULTADOS: {
        E.DATOS_SIOX_IMPORTADOS,
        E.DATOS_CAPTURADOS_MANUALMENTE,
        E.ERROR_INTEGRACION,
    },
    E.DATOS_SIOX_IMPORTADOS: {E.DATOS_NORMALIZADOS},
    E.DATOS_CAPTURADOS_MANUALMENTE: {E.DATOS_NORMALIZADOS},
    E.DATOS_NORMALIZADOS: {E.INSPECCION_VISUAL_PENDIENTE},
    E.INSPECCION_VISUAL_PENDIENTE: {
        E.INSPECCION_VISUAL_APROBADA,
        E.INSPECCION_VISUAL_RECHAZADA,
    },
    # Regla de negocio #3: rechazo visual salta OBD y prueba, va directo a
    # impresión (certificado de rechazo, que también consume folio externo).
    # Cola propia (PENDIENTE_DE_IMPRESION_RECHAZO) desde el hallazgo #4 del
    # Figma 2026-08-24 — antes compartía PENDIENTE_IMPRESION con el aprobado.
    E.INSPECCION_VISUAL_RECHAZADA: {E.PENDIENTE_DE_IMPRESION_RECHAZO},
    E.INSPECCION_VISUAL_APROBADA: {E.OBD_NO_APLICA, E.OBD_PENDIENTE},
    E.OBD_NO_APLICA: {E.LISTO_PARA_PRUEBA},
    E.OBD_PENDIENTE: {E.OBD_SOLICITADO},
    E.OBD_SOLICITADO: {E.OBD_RECIBIDO, E.ERROR_INTEGRACION},
    E.OBD_RECIBIDO: {E.LISTO_PARA_PRUEBA},
    E.LISTO_PARA_PRUEBA: {E.PRUEBA_CONFIGURADA},
    E.PRUEBA_CONFIGURADA: {E.PRUEBA_EN_PROCESO},
    E.PRUEBA_EN_PROCESO: {E.PRUEBA_FINALIZADA},
    # El resultado de la prueba decide la cola: APROBADO -> PENDIENTE_IMPRESION,
    # RECHAZADO -> PENDIENTE_DE_IMPRESION_RECHAZO (ver pruebas.guardar_resultado).
    E.PRUEBA_FINALIZADA: {E.PENDIENTE_IMPRESION, E.PENDIENTE_DE_IMPRESION_RECHAZO},
    E.PENDIENTE_IMPRESION: {E.FOLIO_SOLICITADO},
    E.PENDIENTE_DE_IMPRESION_RECHAZO: {E.FOLIO_SOLICITADO},
    E.FOLIO_SOLICITADO: {E.FOLIO_ASIGNADO, E.FOLIO_ERROR},
    # FOLIO_ERROR: sección 3 del handoff — marcar el folio asignado como
    # DAÑADO antes de imprimir intenta tomar el siguiente folio disponible
    # del mismo tipo; si el inventario de ese tipo también está agotado, el
    # expediente cae al mismo estado de error que una solicitud sin folio
    # (ver impresion.marcar_folio_danado).
    E.FOLIO_ASIGNADO: {E.IMPRESO, E.IMPRESION_FALLIDA, E.FOLIO_ERROR},
    # Split del CERRADO único: el cierre distingue aprobado/rechazado (ver
    # impresion.cerrar_expediente, que decide cuál según certificado_tipo).
    E.IMPRESO: {E.CERRADO_APROBADO, E.CERRADO_RECHAZADO},
    # Reintentos desde estados de error: vuelven al paso que falló.
    E.ERROR_INTEGRACION: {
        E.DATOS_SIOX_CONSULTADOS,
        E.OBD_SOLICITADO,
    },
    E.FOLIO_ERROR: {E.FOLIO_SOLICITADO},
    E.IMPRESION_FALLIDA: {E.FOLIO_ASIGNADO},
}


class TransitionNotAllowed(Exception):
    pass


async def transition(
    db: AsyncSession,
    verificacion: Verificacion,
    nuevo_estado: E,
    *,
    usuario_id: uuid.UUID | None,
    modulo: str,
    evento: str,
    detalle: dict | None = None,
    cancelacion: bool = False,
) -> Verificacion:
    estado_anterior = verificacion.estado

    if cancelacion:
        if estado_anterior not in CANCELABLE_FROM or nuevo_estado != E.CANCELADO:
            raise TransitionNotAllowed(
                f"No se puede cancelar un expediente en estado {estado_anterior}"
            )
    else:
        permitidos = ALLOWED_TRANSITIONS.get(estado_anterior, set())
        if nuevo_estado not in permitidos:
            raise TransitionNotAllowed(
                f"Transición {estado_anterior} -> {nuevo_estado} no permitida"
            )

    verificacion.estado = nuevo_estado
    db.add(verificacion)

    if nuevo_estado in (E.CERRADO_APROBADO, E.CERRADO_RECHAZADO):
        verificacion.cerrado_at = datetime.datetime.now(datetime.timezone.utc)

    # Etapa 12: cada transición encola su evento (append-only, ya con id
    # propio) y un snapshot idempotente de la Verificacion para
    # sincronizar hacia el central cuando haya conexión — ver
    # app/services/sync.py.
    await registrar_evento_con_sync(
        db,
        EventLog(
            verificacion_id=verificacion.id,
            evento=evento,
            estado_anterior=estado_anterior,
            estado_nuevo=nuevo_estado,
            usuario_id=usuario_id,
            modulo=modulo,
            detalle_json=detalle,
        ),
        verificacion=verificacion,
    )

    return verificacion
