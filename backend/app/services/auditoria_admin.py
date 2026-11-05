"""X7-c: rastro de auditoría de las acciones administrativas.

Antes, crear usuarios, restablecer contraseñas, otorgar permisos, cambiar
parámetros, registrar equipos o lotes de folios no dejaba ningún registro.
Ahora cada una escribe una fila en `event_log` con `modulo="administracion"`
y sin expediente, y aparece en la pestaña Auditoría del Supervisor.

Reglas:
- Nunca se guardan contraseñas ni hashes: solo el hecho ("password
  restablecida") y los nombres de los campos que cambiaron.
- No se encola a `sync_outbox`: usuarios, permisos y parámetros se
  administran solo con conexión y no viajan por la cola offline (decisión
  documentada en agosto); su bitácora tampoco.
- No hace commit: va en la misma transacción que el cambio que registra,
  así que si el cambio falla, el evento tampoco queda.
"""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_log import EventLog

if TYPE_CHECKING:  # evita importar app.api desde app.services en tiempo de ejecución
    from app.api.deps import SessionContext

MODULO_ADMIN = "administracion"

_CAMPOS_SECRETOS = {"password", "password_hash"}


def _limpiar(valor: Any) -> Any:
    """JSON-serializable y sin secretos."""
    if isinstance(valor, dict):
        return {k: _limpiar(v) for k, v in valor.items() if k not in _CAMPOS_SECRETOS}
    if isinstance(valor, (list, tuple)):
        return [_limpiar(v) for v in valor]
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if hasattr(valor, "value"):  # Enum
        return valor.value
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


def registrar_evento_admin(
    db: AsyncSession,
    session: "SessionContext",
    evento: str,
    detalle: dict | None = None,
) -> EventLog:
    ev = EventLog(
        verificacion_id=None,
        centro_id=session.center_id,
        evento=evento,
        usuario_id=session.user_id,
        modulo=MODULO_ADMIN,
        detalle_json=_limpiar(detalle) if detalle else None,
    )
    db.add(ev)
    return ev
