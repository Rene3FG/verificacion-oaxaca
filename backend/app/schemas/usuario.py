import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.auth import MAX_PASSWORD_BYTES


def _validar_bytes(v: str | None) -> str | None:
    if v is not None and len(v.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"La contraseña no puede exceder {MAX_PASSWORD_BYTES} bytes.")
    return v


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

    _pw = field_validator("password")(_validar_bytes)


class UsuarioUpdate(BaseModel):
    nombre_completo: str | None = Field(default=None, min_length=1, max_length=200)
    # Restablecer contraseña: el Supervisor la fija, nunca se devuelve.
    password: str | None = Field(default=None, min_length=8, max_length=100)
    is_active: bool | None = None

    _pw = field_validator("password")(_validar_bytes)
