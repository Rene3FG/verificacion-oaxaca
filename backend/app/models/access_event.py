import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import AccessEventResultado, StationType


class AccessEvent(Base, UUIDPKMixin, TimestampMixin):
    """Bitácora de intentos de acceso (HU-007), separada de `event_log`
    porque `event_log.verificacion_id` es NOT NULL con FK a `verificaciones`
    y un login denegado no tiene expediente asociado."""

    __tablename__ = "access_events"

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    workstation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workstations.id")
    )
    station_type: Mapped[StationType | None] = mapped_column(
        Enum(StationType, name="station_type")
    )
    center_id: Mapped[str | None] = mapped_column(String(60))
    line_id: Mapped[int | None] = mapped_column(Integer)
    resultado: Mapped[AccessEventResultado] = mapped_column(
        Enum(AccessEventResultado, name="access_event_resultado"), nullable=False
    )
    motivo: Mapped[str | None] = mapped_column(String(200))
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("station_sessions.id")
    )
    ip_address: Mapped[str | None] = mapped_column(String(45))
