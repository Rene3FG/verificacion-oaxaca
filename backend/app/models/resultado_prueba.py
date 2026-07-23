import datetime
import uuid

from sqlalchemy import JSON, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ResultadoPruebaEnum, TipoPrueba


class ResultadoPrueba(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "resultados_prueba"

    verificacion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verificaciones.id"), nullable=False
    )
    tipo_prueba: Mapped[TipoPrueba] = mapped_column(
        Enum(TipoPrueba, name="tipo_prueba_resultado"), nullable=False
    )
    combustible: Mapped[str] = mapped_column(String(30), nullable=False)
    resultado: Mapped[ResultadoPruebaEnum | None] = mapped_column(
        Enum(ResultadoPruebaEnum, name="resultado_prueba_enum")
    )
    valores_medidos_json: Mapped[dict | None] = mapped_column(JSON)
    limites_aplicados_json: Mapped[dict | None] = mapped_column(JSON)
    equipo_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    linea_id: Mapped[int] = mapped_column(nullable=False)
    operador_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime.datetime | None] = mapped_column()
    finished_at: Mapped[datetime.datetime | None] = mapped_column()
