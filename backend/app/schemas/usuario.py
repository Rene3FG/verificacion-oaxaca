import uuid

from pydantic import BaseModel, ConfigDict, Field


class UsuarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    nombre_completo: str
    is_active: bool


class UsuarioCreate(BaseModel):
    username: str = Field(min_length=3, max_length=60)
    password: str = Field(min_length=8, max_length=100)
    nombre_completo: str = Field(min_length=1, max_length=200)


class UsuarioUpdate(BaseModel):
    nombre_completo: str | None = Field(default=None, min_length=1, max_length=200)
    # Restablecer contraseña: el Supervisor la fija, nunca se devuelve.
    password: str | None = Field(default=None, min_length=8, max_length=100)
    is_active: bool | None = None
