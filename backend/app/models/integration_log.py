import uuid

from sqlalchemy import JSON, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
import enum


class IntegrationDirection(str, enum.Enum):
    REQUEST = "request"
    RESPONSE = "response"


class IntegrationStatus(str, enum.Enum):
    OK = "OK"
    ERROR = "error"


class IntegrationLog(Base, UUIDPKMixin, TimestampMixin):
    """Bitácora técnica de TODA integración externa (SIOX, OBD, equipo de
    prueba, sistema de folios). Regla de negocio #13: nunca opcional."""

    __tablename__ = "integration_logs"

    verificacion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verificaciones.id")
    )
    integration_name: Mapped[str] = mapped_column(String(60), nullable=False)
    direction: Mapped[IntegrationDirection] = mapped_column(
        Enum(IntegrationDirection, name="integration_direction"), nullable=False
    )
    payload: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[IntegrationStatus] = mapped_column(
        Enum(IntegrationStatus, name="integration_status"), nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)
