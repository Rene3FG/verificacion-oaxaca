import datetime
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.siox_consulta import EstadoSioxConsulta


class SioxConsultaRead(BaseModel):
    """Fila de historial. No expone `response_raw` (el HTML crudo de SIOX);
    solo `response_normalized`, ya sea que la consulta haya tenido éxito o no."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime.datetime
    placa: str
    status: EstadoSioxConsulta
    response_normalized: dict | None
    consultado_por: uuid.UUID | None
