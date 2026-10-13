import uuid

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import FuenteDatos
from app.services.potencia_dinamometro import CLASIFICACIONES_CARROCERIA


class VehiculoBase(BaseModel):
    placa: str
    niv: str | None = None
    marca: str | None = None
    linea: str | None = None
    modelo: int | None = None
    tipo_vehiculo: str | None = None
    combustible: str | None = None
    razon_social: str | None = None
    entidad_federativa: str | None = None
    tarjeta_circulacion: str | None = None
    propietario_estado: str | None = None
    propietario_municipio: str | None = None
    propietario_codigo_postal: str | None = None
    propietario_colonia: str | None = None
    propietario_calle: str | None = None
    propietario_numero_exterior: str | None = None
    propietario_poblacion: str | None = None
    pbv: str | None = None
    traccion: str | None = None
    peso_bruto_vehicular_kg: float | None = None
    numero_cilindros: int | None = None
    clasificacion_carroceria: str | None = None


def _validar_cilindros(valor: int | None) -> int | None:
    if valor is not None and not 1 <= valor <= 16:
        raise ValueError("El número de cilindros debe estar entre 1 y 16.")
    return valor


def _validar_clasificacion(valor: str | None) -> str | None:
    if valor is not None and valor not in CLASIFICACIONES_CARROCERIA:
        raise ValueError(
            "Clasificación de carrocería inválida; opciones: "
            + ", ".join(CLASIFICACIONES_CARROCERIA)
        )
    return valor


class VehiculoCreate(VehiculoBase):
    fuente_datos: FuenteDatos = FuenteDatos.MANUAL


class VehiculoRead(VehiculoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fuente_datos: FuenteDatos


class VehiculoUpdate(BaseModel):
    """Todos los campos opcionales: PATCH parcial. Se distingue "no enviado"
    de "enviado como null" con `exclude_unset=True` en el router — solo los
    campos presentes en el payload se tocan."""

    niv: str | None = None
    marca: str | None = None
    linea: str | None = None
    modelo: int | None = None
    tipo_vehiculo: str | None = None
    combustible: str | None = None
    razon_social: str | None = None
    entidad_federativa: str | None = None
    tarjeta_circulacion: str | None = None
    propietario_estado: str | None = None
    propietario_municipio: str | None = None
    propietario_codigo_postal: str | None = None
    propietario_colonia: str | None = None
    propietario_calle: str | None = None
    propietario_numero_exterior: str | None = None
    propietario_poblacion: str | None = None
    pbv: str | None = None
    traccion: str | None = None
    peso_bruto_vehicular_kg: float | None = None
    numero_cilindros: int | None = None
    clasificacion_carroceria: str | None = None

    @field_validator("numero_cilindros")
    @classmethod
    def validar_cilindros(cls, valor: int | None) -> int | None:
        return _validar_cilindros(valor)

    @field_validator("clasificacion_carroceria")
    @classmethod
    def validar_clasificacion(cls, valor: str | None) -> str | None:
        return _validar_clasificacion(valor)
