import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import FuenteDatos


class VehiculoBase(BaseModel):
    placa: str
    niv: str | None = None
    marca: str | None = None
    linea: str | None = None
    modelo: int | None = None
    tipo_vehiculo: str | None = None
    combustible: str | None = None
    razon_social: str | None = None
    tarjeta_circulacion: str | None = None
    propietario_estado: str | None = None
    propietario_municipio: str | None = None
    propietario_codigo_postal: str | None = None
    propietario_colonia: str | None = None
    propietario_calle: str | None = None
    propietario_numero_exterior: str | None = None
    pbv: str | None = None
    traccion: str | None = None
    peso_bruto_vehicular_kg: float | None = None


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
    tarjeta_circulacion: str | None = None
    propietario_estado: str | None = None
    propietario_municipio: str | None = None
    propietario_codigo_postal: str | None = None
    propietario_colonia: str | None = None
    propietario_calle: str | None = None
    propietario_numero_exterior: str | None = None
    pbv: str | None = None
    traccion: str | None = None
    peso_bruto_vehicular_kg: float | None = None
