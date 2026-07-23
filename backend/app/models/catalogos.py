from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class CatalogoSimpleBase(Base, UUIDPKMixin, TimestampMixin):
    """Base abstracta para catálogos clave-valor simples (combustibles,
    tipos de vehículo, tipos de prueba, tipos de certificado, causales de
    rechazo visual, centros, líneas, equipos, normas)."""

    __abstract__ = True

    clave: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CatalogoSimple(CatalogoSimpleBase):
    """Catálogo genérico; en producción cada cat_* de la lista del PDF
    (cat_combustibles, cat_tipos_vehiculo, cat_tipos_prueba, ...) puede
    modelarse como fila de `tipo` + clave, o como tabla propia si necesita
    columnas adicionales."""

    __tablename__ = "catalogos_simples"

    tipo: Mapped[str] = mapped_column(String(60), nullable=False, index=True)


class CatEstadoVerificacion(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "cat_estados_verificacion"

    clave: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    descripcion: Mapped[str] = mapped_column(String(200), nullable=False)
    es_error: Mapped[bool] = mapped_column(Boolean, default=False)


class CatParametroSistema(Base, UUIDPKMixin, TimestampMixin):
    """Parámetros de negocio configurables (obd_modelo_minimo,
    gasolina_prueba_default, etc.). Nunca deben quedar como constantes en
    código — ver regla de negocio #4 y sección 'Convenciones de código'."""

    __tablename__ = "cat_parametros_sistema"

    clave: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    valor: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(300))
