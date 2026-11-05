import uuid

from sqlalchemy import JSON, CheckConstraint, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import EstadoVerificacion


class EventLog(Base, UUIDPKMixin, TimestampMixin):
    """Bitácora funcional del expediente. Toda transición de estado escrita
    por app.services.state_machine genera una fila aquí.

    X7-c (2026-11-04): también guarda las acciones administrativas
    (usuarios, permisos, parámetros, equipos, folios), que no pertenecen a
    ningún expediente. Esas filas llevan `verificacion_id = NULL`,
    `modulo = "administracion"` y el centro en `centro_id`. El CHECK impide
    que un evento operativo se quede sin expediente por error."""

    __tablename__ = "event_log"
    __table_args__ = (
        CheckConstraint(
            "verificacion_id IS NOT NULL OR modulo = 'administracion'",
            name="ck_event_log_expediente_o_admin",
        ),
    )

    verificacion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verificaciones.id"), nullable=True
    )
    # Centro donde ocurrió. Obligatorio en los eventos administrativos (no
    # hay expediente del cual sacarlo); en los operativos se llena en la
    # migración y, si falta, la auditoría lo toma del expediente.
    centro_id: Mapped[str | None] = mapped_column(String(60))
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
