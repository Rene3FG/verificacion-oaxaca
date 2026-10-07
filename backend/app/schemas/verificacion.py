import datetime
import re
import uuid

from pydantic import BaseModel, ConfigDict, computed_field, field_validator

from app.models.enums import EstadoVerificacion, ResultadoFinal, TipoPrueba
from app.schemas.vehiculo import VehiculoRead


class ExpedienteCreate(BaseModel):
    """centro_id, linea_id y operador_id NO se aceptan aquí: se resuelven
    server-side desde la sesión de la estación de Captura (get_current_session).
    Aceptarlos del cliente permitiría crear un expediente en una línea o a
    nombre de un usuario distinto al que realmente está operando."""

    placa: str

    @field_validator("placa")
    @classmethod
    def validar_placa(cls, valor: str) -> str:
        """HU-010: formato mínimo, no el catálogo oficial de placas por
        entidad — 5 a 10 caracteres entre letras, dígitos y guiones, con al
        menos un dígito. Se normaliza a mayúsculas sin espacios para que la
        misma placa no se registre de dos formas (HU-089 compara por placa)."""

        placa = re.sub(r"\s+", "", valor or "").upper()
        if not re.fullmatch(r"[A-Z0-9-]{5,10}", placa) or not re.search(r"\d", placa):
            raise ValueError(
                "Placa inválida: de 5 a 10 letras, números o guiones, con al menos un número."
            )
        return placa


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
    tipo_verificacion: str | None
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def tipo_certificado_sugerido(self) -> str | None:
        """HU-053: solo RECHAZO se sugiere — es el único tipo que el sistema
        determina solo. Para aprobados, Particular/Doble Cero/Intensivo queda
        bajo responsabilidad del operador (handoff, sin validación de
        elegibilidad), así que no se sugiere ninguno."""

        if (
            self.estado == EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO
            or self.resultado_final == ResultadoFinal.RECHAZADO
        ):
            return "RECHAZO"
        return None
