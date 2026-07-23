import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import EstadoFolioAssignment


class FolioAssignment(Base, UUIDPKMixin, TimestampMixin):
    """Trazabilidad LOCAL del folio recibido. Esta tabla NO administra
    inventario de folios; el inventario vive en el sistema externo."""

    __tablename__ = "folio_assignments"

    verificacion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verificaciones.id"), nullable=False
    )
    folio_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folio_requests.id"), nullable=False
    )
    folio: Mapped[str] = mapped_column(String(60), nullable=False)
    tipo_certificado: Mapped[str] = mapped_column(String(60), nullable=False)
    asignado_por: Mapped[str | None] = mapped_column(String(120))
    estatus: Mapped[EstadoFolioAssignment] = mapped_column(
        Enum(EstadoFolioAssignment, name="estado_folio_assignment"),
        default=EstadoFolioAssignment.ASIGNADO,
        nullable=False,
    )
