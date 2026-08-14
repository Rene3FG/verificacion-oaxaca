import uuid

from pydantic import BaseModel, ConfigDict


class UsuarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    nombre_completo: str
    is_active: bool
