import uuid

from sqlalchemy import JSON, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import EstadoVerificacion


class EventLog(Base, UUIDPKMixin, TimestampMixin):
    """Bitácora funcional del expediente. Toda transición de estado escrita
    por app.services.state_machine genera una fila aquí."""

    __tablename__ = "event_log"

    verificacion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verificaciones.id"), nullable=False
    )
    evento: Mapped[str] = mapped_column(String(120), nullable=False)
    estado_anterior: Mapped[EstadoVerificacion | None] = mapped_column(
        Enum(EstadoVerificacion, name="estado_verificacion")
    )
    estado_nuevo: Mapped[EstadoVerificacion | None] = mapped_column(
        Enum(EstadoVerificacion, name="estado_verificacion")
    )
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    modulo: Mapped[str] = mapped_column(String(30), nullable=False)
    detalle_json: Mapped[dict | None] = mapped_column(JSON)
