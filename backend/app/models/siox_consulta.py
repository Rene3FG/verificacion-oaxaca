import uuid

from sqlalchemy import JSON, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
import enum


class EstadoSioxConsulta(str, enum.Enum):
    EXITOSA = "EXITOSA"
    SIN_DATOS = "SIN_DATOS"
    ERROR = "ERROR"


class SioxConsulta(Base, UUIDPKMixin, TimestampMixin):
    """Evidencia de cada consulta al portal público SIOX. Ver también
    `IntegrationLog` para la bitácora técnica genérica de la misma llamada."""

    __tablename__ = "siox_consultas"

    verificacion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verificaciones.id"), nullable=False
    )
    placa: Mapped[str] = mapped_column(String(20), nullable=False)
    url_consulta: Mapped[str | None] = mapped_column(Text)
    request_payload: Mapped[dict | None] = mapped_column(JSON)
    response_raw: Mapped[dict | None] = mapped_column(JSON)
    response_normalized: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[EstadoSioxConsulta] = mapped_column(
        Enum(EstadoSioxConsulta, name="estado_siox_consulta"), nullable=False
    )
    consultado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
