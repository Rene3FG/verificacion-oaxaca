import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import StationType


class PermisoCreate(BaseModel):
    user_id: uuid.UUID
    station_type: StationType
    center_id: str
    line_id: int | None = None
    can_operate: bool = True
    can_supervise: bool = False


class PermisoUpdate(BaseModel):
    """Todos opcionales: PATCH parcial, igual que VehiculoUpdate."""

    line_id: int | None = None
    can_operate: bool | None = None
    can_supervise: bool | None = None


class PermisoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    station_type: StationType
    center_id: str
    line_id: int | None
    can_operate: bool
    can_supervise: bool
