import datetime
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import EstadoVerificacion, ResultadoFinal, TipoPrueba


class Verificacion(Base, UUIDPKMixin, TimestampMixin):
    """El expediente. Toda transición de `estado` debe pasar por el servicio
    de máquina de estados (app.services.state_machine); nunca UPDATE directo."""

    __tablename__ = "verificaciones"

    vehiculo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehiculos.id"), nullable=False
    )
    placa: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    centro_id: Mapped[str] = mapped_column(String(60), nullable=False)
    linea_id: Mapped[int] = mapped_column(nullable=False)
    operador_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    capture_workstation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workstations.id")
    )
    test_workstation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workstations.id")
    )
    print_workstation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workstations.id")
    )

    estado: Mapped[EstadoVerificacion] = mapped_column(
        Enum(EstadoVerificacion, name="estado_verificacion"),
        default=EstadoVerificacion.CREADO,
        nullable=False,
    )
    combustible_validado: Mapped[str | None] = mapped_column(String(30))
    tipo_prueba_final: Mapped[TipoPrueba | None] = mapped_column(
        Enum(TipoPrueba, name="tipo_prueba")
    )
    resultado_final: Mapped[ResultadoFinal | None] = mapped_column(
        Enum(ResultadoFinal, name="resultado_final")
    )
    certificado_tipo: Mapped[str | None] = mapped_column(String(60))
    folio_externo: Mapped[str | None] = mapped_column(String(60))
    folio_asignado_at: Mapped[datetime.datetime | None] = mapped_column()
    cerrado_at: Mapped[datetime.datetime | None] = mapped_column()

    vehiculo: Mapped["Vehiculo"] = relationship()
