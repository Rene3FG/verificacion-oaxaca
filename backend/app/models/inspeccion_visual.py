import uuid

from sqlalchemy import JSON, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ResultadoInspeccionVisual


class InspeccionVisual(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "inspeccion_visual"

    verificacion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verificaciones.id"), nullable=False
    )
    resultado: Mapped[ResultadoInspeccionVisual] = mapped_column(
        Enum(ResultadoInspeccionVisual, name="resultado_inspeccion_visual"),
        nullable=False,
    )
    checklist_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    causales_rechazo: Mapped[dict | None] = mapped_column(JSON)
    operador_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
