import datetime
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import EstadoVerificacion


class EventLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime.datetime
    evento: str
    estado_anterior: EstadoVerificacion | None
    estado_nuevo: EstadoVerificacion | None
    usuario_id: uuid.UUID | None
    modulo: str
    detalle_json: dict | None


class AuditoriaRead(EventLogRead):
    """N4: fila de la bitácora global — EventLog + placa del expediente y
    nombre de quien actuó, para no obligar al frontend a resolverlos."""

    verificacion_id: uuid.UUID
    placa: str
    usuario_nombre: str | None


class AuditoriaPagina(BaseModel):
    total: int
    items: list[AuditoriaRead]
