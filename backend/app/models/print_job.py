import datetime
import uuid

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import EstadoPrintJob


class PrintJob(Base, UUIDPKMixin, TimestampMixin):
    """Cola de impresión transaccional. `estado` cubre todo el ciclo desde
    pendiente hasta impreso, incluyendo la espera del folio externo."""

    __tablename__ = "print_jobs"

    verificacion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verificaciones.id"), nullable=False
    )
    tipo_documento: Mapped[str] = mapped_column(String(60), nullable=False)
    estado: Mapped[EstadoPrintJob] = mapped_column(
        Enum(EstadoPrintJob, name="estado_print_job"),
        default=EstadoPrintJob.PENDIENTE,
        nullable=False,
    )
    requiere_folio: Mapped[bool] = mapped_column(Boolean, default=True)
    folio_externo: Mapped[str | None] = mapped_column(String(60))
    intentos: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    printed_at: Mapped[datetime.datetime | None] = mapped_column()

    # 'Certificate Result Projection Contract v1' (sección 4): snapshot
    # inmutable generado antes del primer clic en Imprimir, antes de
    # llamar a la impresora. Se conserva sin cambios en cada reintento
    # técnico (mismo folio, misma impresión fallida); solo una reimpresión
    # AUTORIZADA (folio dañado, corrección de tipo post-impresión) lo
    # regenera, y únicamente para los campos de folio/tipo — el resultado
    # técnico (`test_result_id`, lecturas, evaluation_result) viene de
    # `ResultadoPrueba`, que nunca se reescribe.
    certificate_projection_json: Mapped[dict | None] = mapped_column(JSON)
    projection_version: Mapped[str | None] = mapped_column(String(20))
    layout_version: Mapped[str | None] = mapped_column(String(20))
