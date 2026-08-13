"""HU-016: escritura/corrección de los datos del vehículo, compartida entre
`PATCH /api/expedientes/{id}/vehiculo` y `POST /api/siox/captura-manual/{id}`
(HU-015), que reutiliza esta misma lógica."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import FuenteDatos
from app.models.event_log import EventLog
from app.models.vehiculo import Vehiculo
from app.services.sync import registrar_evento_con_sync


async def actualizar_datos_vehiculo(
    db: AsyncSession,
    vehiculo: Vehiculo,
    campos: dict,
    *,
    verificacion_id: uuid.UUID,
    usuario_id: uuid.UUID | None,
    modulo: str,
    evento: str,
) -> dict[str, dict]:
    """Aplica `campos` (ya filtrados a los presentes en el payload) sobre
    `vehiculo`, registra en event_log qué cambió (valor anterior/nuevo), y
    si el dato corregido venía de SIOX marca fuente_datos como
    CORREGIDO_OPERADOR. No hace commit ni flush; eso queda a cargo del
    llamador."""

    cambios: dict[str, dict] = {}
    for campo, nuevo_valor in campos.items():
        anterior = getattr(vehiculo, campo)
        if anterior != nuevo_valor:
            cambios[campo] = {"anterior": anterior, "nuevo": nuevo_valor}
            setattr(vehiculo, campo, nuevo_valor)

    if not cambios:
        return cambios

    fuente_anterior = vehiculo.fuente_datos
    if vehiculo.fuente_datos == FuenteDatos.SIOX:
        vehiculo.fuente_datos = FuenteDatos.CORREGIDO_OPERADOR
    db.add(vehiculo)

    await registrar_evento_con_sync(
        db,
        EventLog(
            verificacion_id=verificacion_id,
            evento=evento,
            usuario_id=usuario_id,
            modulo=modulo,
            detalle_json={
                "campos_modificados": cambios,
                "fuente_datos_anterior": fuente_anterior.value,
                "fuente_datos_nueva": vehiculo.fuente_datos.value,
            },
        ),
    )
    return cambios
