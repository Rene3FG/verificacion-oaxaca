import uuid

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class PrintAttempt(Base, UUIDPKMixin, TimestampMixin):
    """Etapa 12: un intento de impresión es su propia fila inmutable, no un
    contador mutado en `PrintJob.intentos`. Un contador que se incrementa
    (`intentos += 1`) no es idempotente bajo replay de sincronización —
    reenviar el mismo evento dos veces lo duplicaría en el central aunque
    la fila local esté correcta. `PrintJob.intentos` se sigue exponiendo
    como caché (recalculado por conteo, nunca incrementado), igual que
    `SioxConsulta` ya resuelve su "número de intento" contando filas en vez
    de mantener un contador (ver HU-014)."""

    __tablename__ = "print_attempts"

    print_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("print_jobs.id"), nullable=False
    )
    verificacion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verificaciones.id"), nullable=False
    )
    exitoso: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
