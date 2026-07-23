import datetime
import uuid

from sqlalchemy import JSON, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import EstadoFolioRequest


class FolioRequest(Base, UUIDPKMixin, TimestampMixin):
    """Solicitud de folio al sistema externo. `id` sirve como identificador
    único idempotente: reintentar la misma solicitud nunca debe crear un
    segundo folio (ver regla de negocio #8 / #12 del proyecto)."""

    __tablename__ = "folio_requests"

    verificacion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verificaciones.id"), nullable=False
    )
    print_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("print_jobs.id")
    )
    tipo_certificado: Mapped[str] = mapped_column(String(60), nullable=False)
    tipo_vehiculo: Mapped[str | None] = mapped_column(String(60))
    request_payload: Mapped[dict | None] = mapped_column(JSON)
    response_payload: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[EstadoFolioRequest] = mapped_column(
        Enum(EstadoFolioRequest, name="estado_folio_request"),
        default=EstadoFolioRequest.SOLICITADO,
        nullable=False,
    )
    folio_recibido: Mapped[str | None] = mapped_column(String(60))
    external_reference_id: Mapped[str | None] = mapped_column(String(120))
    completed_at: Mapped[datetime.datetime | None] = mapped_column()
