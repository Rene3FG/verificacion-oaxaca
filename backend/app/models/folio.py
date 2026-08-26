import datetime
import uuid

from sqlalchemy import Enum, ForeignKey, Identity, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import EstadoFolio, TipoCertificado


class FolioLote(Base, UUIDPKMixin, TimestampMixin):
    """Alta masiva de folios por rango (Developer Handoff, regla crítica #6:
    'El Superadmin registra los folios ... la forma de alta masiva —por
    ejemplo rango o archivo— queda por definir'; este proyecto implementa
    la variante por rango). Cada fila es un lote; los folios individuales
    que produjo viven en `Folio.lote_id`, nunca se borran de aquí aunque el
    lote se agote."""

    __tablename__ = "folio_lotes"

    tipo_certificado: Mapped[TipoCertificado] = mapped_column(
        Enum(TipoCertificado, name="tipo_certificado"), nullable=False
    )
    folio_inicio: Mapped[str] = mapped_column(String(60), nullable=False)
    folio_fin: Mapped[str] = mapped_column(String(60), nullable=False)
    cantidad: Mapped[int] = mapped_column(nullable=False)
    registrado_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cat_usuarios.id"), nullable=False
    )


class Folio(Base, UUIDPKMixin, TimestampMixin):
    """Inventario LOCAL de folios físicos (reemplaza el modelo de 'solicitud
    a sistema externo' de `folio_request`/`folio_assignment` — ver revisión
    del Figma 2026-08-24, regla crítica #6: este sistema es la fuente de
    verdad del inventario, sin sincronización externa).

    `orden` es una IDENTITY de Postgres, no el orden alfabético del string
    `folio` (los folios pueden traer prefijo no numérico) — sirve para que
    'asignar el siguiente folio disponible' sea 'el de menor `orden` con
    estatus DISPONIBLE', tomado con `FOR UPDATE SKIP LOCKED` para que dos
    asignaciones concurrentes del mismo tipo nunca se reparen el mismo
    folio."""

    __tablename__ = "folios"

    lote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folio_lotes.id"), nullable=False
    )
    tipo_certificado: Mapped[TipoCertificado] = mapped_column(
        Enum(TipoCertificado, name="tipo_certificado"), nullable=False
    )
    folio: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    orden: Mapped[int] = mapped_column(Identity(always=False), nullable=False, unique=True)
    estatus: Mapped[EstadoFolio] = mapped_column(
        Enum(EstadoFolio, name="estado_folio"),
        default=EstadoFolio.DISPONIBLE,
        nullable=False,
    )

    verificacion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verificaciones.id")
    )
    asignado_at: Mapped[datetime.datetime | None] = mapped_column()

    danado_at: Mapped[datetime.datetime | None] = mapped_column()
    motivo_danado: Mapped[str | None] = mapped_column(Text)

    invalidado_at: Mapped[datetime.datetime | None] = mapped_column()
    motivo_invalidacion: Mapped[str | None] = mapped_column(Text)

    # Cadena de reimpresión (Developer Handoff, sección 3/5): el folio nuevo
    # que reemplazó a este tras un daño/corrección de tipo posterior a
    # imprimir. Pendiente de cablear en un endpoint — ver CLAUDE.md.
    reemplazado_por_folio_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folios.id")
    )
