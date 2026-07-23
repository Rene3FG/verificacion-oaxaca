from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import FuenteDatos


class Vehiculo(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "vehiculos"

    placa: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    niv: Mapped[str | None] = mapped_column(String(30))
    marca: Mapped[str | None] = mapped_column(String(60))
    linea: Mapped[str | None] = mapped_column(String(60))
    modelo: Mapped[int | None] = mapped_column()
    tipo_vehiculo: Mapped[str | None] = mapped_column(String(60))
    combustible: Mapped[str | None] = mapped_column(String(30))
    razon_social: Mapped[str | None] = mapped_column(String(200))
    fuente_datos: Mapped[FuenteDatos] = mapped_column(
        Enum(FuenteDatos, name="fuente_datos"), default=FuenteDatos.MANUAL
    )
