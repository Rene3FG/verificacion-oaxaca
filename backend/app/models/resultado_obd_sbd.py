import datetime
import uuid

from sqlalchemy import JSON, Boolean, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ResultadoPruebaEnum


class ResultadoObdSbd(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "resultados_obd_sbd"

    verificacion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verificaciones.id"), nullable=False
    )
    aplica: Mapped[bool] = mapped_column(Boolean, nullable=False)
    solicitado_at: Mapped[datetime.datetime | None] = mapped_column()
    recibido_at: Mapped[datetime.datetime | None] = mapped_column()
    resultado: Mapped[ResultadoPruebaEnum | None] = mapped_column(
        Enum(ResultadoPruebaEnum, name="resultado_obd_sbd_enum")
    )
    codigos_error: Mapped[dict | None] = mapped_column(JSON)
    datos_raw: Mapped[dict | None] = mapped_column(JSON)
    equipo_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    operador_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
