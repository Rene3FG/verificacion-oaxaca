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
