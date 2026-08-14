import datetime
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import StationType


class WorkstationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    station_type: StationType
    center_id: str
    line_id: int | None
    is_centralized: bool
    allowed_line_ids: list[int] | None
    is_active: bool


class StationSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    workstation_id: uuid.UUID
    station_type: StationType
    center_id: str | None
    line_id: int | None
    login_at: datetime.datetime | None
    logout_at: datetime.datetime | None
    status: str
    # No es columna de StationSession: se calcula en /estaciones/login a
    # partir del UserStationPermission usado para autorizar el acceso, y se
    # inyecta como atributo suelto antes de serializar. El frontend lo usa
    # para mostrar/ocultar la pantalla de Supervisor sin depender de a qué
    # tipo de estación física se conectó la sesión.
    can_supervise: bool = False
