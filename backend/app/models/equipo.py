import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Equipo(Base, UUIDPKMixin, TimestampMixin):
    """F4 (HU-042/102): equipo físico de una estación de Prueba. Antes
    `ResultadoPrueba.equipo_id`/`ResultadoObdSbd.equipo_id` eran un UUID
    libre que mandaba el cliente, sin catálogo detrás. Ahora el servidor lo
    resuelve con `app.services.equipos.resolver_equipo` según el método.

    `tipo` es texto validado contra `TIPOS_EQUIPO` (no ENUM de Postgres)
    para poder agregar tipos sin migración cuando llegue el adaptador del
    proveedor. Sin DELETE: los resultados lo referencian; se desactiva."""

    __tablename__ = "cat_equipos"

    workstation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workstations.id"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    marca: Mapped[str | None] = mapped_column(String(80))
    modelo: Mapped[str | None] = mapped_column(String(80))
    numero_serie: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
