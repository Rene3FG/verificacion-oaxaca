from sqlalchemy import Enum, Float, String
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

    # Sección 7 del handoff (revisión Figma 2026-08-24): datos de propietario/
    # domicilio y del vehículo que el certificado exige y hoy no se capturan.
    # Opcionales a nivel de esquema; la obligatoriedad se valida al imprimir
    # (ver `app.services.certificado.campos_obligatorios_faltantes`), no al
    # capturar.
    tarjeta_circulacion: Mapped[str | None] = mapped_column(String(60))
    propietario_estado: Mapped[str | None] = mapped_column(String(60))
    propietario_municipio: Mapped[str | None] = mapped_column(String(100))
    propietario_codigo_postal: Mapped[str | None] = mapped_column(String(10))
    propietario_colonia: Mapped[str | None] = mapped_column(String(100))
    propietario_calle: Mapped[str | None] = mapped_column(String(150))
    propietario_numero_exterior: Mapped[str | None] = mapped_column(String(20))
    pbv: Mapped[str | None] = mapped_column(String(30))
    traccion: Mapped[str | None] = mapped_column(String(30))

    # `pbv` (arriba) es texto libre para el certificado impreso, tal cual
    # viene de la tarjeta de circulación (2026-08-30) — no sirve para
    # estratificar límites de emisión por rango de peso (NOM-045 diésel,
    # 2026-09-02). Columna numérica separada, opcional, solo para esa
    # comparación; `pbv` no se toca ni se deriva de aquí.
    peso_bruto_vehicular_kg: Mapped[float | None] = mapped_column(Float)

    fuente_datos: Mapped[FuenteDatos] = mapped_column(
        Enum(FuenteDatos, name="fuente_datos"), default=FuenteDatos.MANUAL
    )
