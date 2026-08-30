import datetime
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import EstadoVerificacion, ResultadoFinal, TipoPrueba
from app.schemas.vehiculo import VehiculoRead


class ExpedienteCreate(BaseModel):
    """centro_id, linea_id y operador_id NO se aceptan aquí: se resuelven
    server-side desde la sesión de la estación de Captura (get_current_session).
    Aceptarlos del cliente permitiría crear un expediente en una línea o a
    nombre de un usuario distinto al que realmente está operando."""

    placa: str


class ExpedienteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    placa: str
    centro_id: str
    linea_id: int
    estado: EstadoVerificacion
    combustible_validado: str | None
    tipo_prueba_final: TipoPrueba | None
    resultado_final: ResultadoFinal | None
    certificado_tipo: str | None
    folio_externo: str | None
    folio_asignado_at: datetime.datetime | None
    cerrado_at: datetime.datetime | None
    hora_salida: datetime.datetime | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ExpedienteCompleto(ExpedienteRead):
    """Objeto completo que reciben Prueba e Impresión — regla de negocio #6:
    el módulo de prueba recibe el expediente COMPLETO, nunca solo placa."""

    vehiculo: VehiculoRead
