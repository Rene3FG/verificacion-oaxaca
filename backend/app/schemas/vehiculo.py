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


class VehiculoCreate(VehiculoBase):
    fuente_datos: FuenteDatos = FuenteDatos.MANUAL


class VehiculoRead(VehiculoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fuente_datos: FuenteDatos
