import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.auth import MAX_PASSWORD_BYTES, validar_politica_password


def _validar_bytes(v: str | None) -> str | None:
    if v is not None and len(v.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"La contraseña no puede exceder {MAX_PASSWORD_BYTES} bytes.")
    if v is not None:
        validar_politica_password(v)
    return v


_CLAVE_TECNICO = re.compile(r"^[A-Z0-9-]{1,20}$")


def _normalizar_clave_tecnico(v: str | None) -> str | None:
    """Mayúsculas y sin espacios; vacío equivale a quitar la clave."""
    if v is None:
        return None
    v = v.strip().upper()
    if v == "":
        return None
    if not _CLAVE_TECNICO.match(v):
        raise ValueError(
            "La clave de técnico solo admite letras, números y guiones (máximo 20)."
        )
    return v


class UsuarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    nombre_completo: str
    is_active: bool
    clave_tecnico: str | None = None
    must_change_password: bool = False


class UsuarioCreate(BaseModel):
    username: str = Field(min_length=3, max_length=60)
    password: str = Field(min_length=8, max_length=100)
    nombre_completo: str = Field(min_length=1, max_length=200)
    clave_tecnico: str | None = None

    _pw = field_validator("password")(_validar_bytes)
    _clave = field_validator("clave_tecnico")(_normalizar_clave_tecnico)

    @model_validator(mode="after")
    def _no_igual_al_usuario(self):
        if self.password.lower() == self.username.lower():
            raise ValueError("La contraseña no puede ser igual al usuario.")
        validar_politica_password(self.password, username=self.username)
        return self


class UsuarioUpdate(BaseModel):
    nombre_completo: str | None = Field(default=None, min_length=1, max_length=200)
    # Restablecer contraseña: el Supervisor la fija, nunca se devuelve.
    password: str | None = Field(default=None, min_length=8, max_length=100)
    is_active: bool | None = None
    # Enviar null o "" quita la clave; omitir el campo la deja igual.
    clave_tecnico: str | None = None

    _pw = field_validator("password")(_validar_bytes)
    _clave = field_validator("clave_tecnico")(_normalizar_clave_tecnico)


class CambioPasswordPropio(BaseModel):
    """X6-b: el propio usuario cambia su contraseña; exige la actual."""

    password_actual: str = Field(min_length=1, max_length=100)
    password_nueva: str = Field(min_length=8, max_length=100)

    _pw = field_validator("password_nueva")(_validar_bytes)
