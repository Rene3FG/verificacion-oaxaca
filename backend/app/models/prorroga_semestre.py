import datetime
import uuid

from sqlalchemy import Date, Identity, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class ProrrogaSemestre(Base, UUIDPKMixin, TimestampMixin):
    """Sección 5 del handoff (revisión Figma 2026-08-24): "prórroga global
    del 1er periodo" — Supervisor define una `fecha_final` hasta la cual
    se imprime Semestre 1 para todos los vehículos, sin importar la fecha
    real (no se contempla prórroga del 2º periodo). Auditable por
    requisito explícito ("motivo, fecha final, usuario y fecha/hora"), así
    que cada configuración nueva es su propia fila (append-only, nunca se
    actualiza una existente) — quién y cuándo la definió es parte del
    dato, no solo el valor vigente.

    No hay columna `activa`: el estado se deriva siempre comparando
    `fecha_final` contra la fecha de hoy (ver
    `app.services.semestre.obtener_prorroga_activa`) — configurar una
    fila nueva con `fecha_final` en el pasado es la forma de desactivar la
    prórroga antes de tiempo, sin necesitar un estado aparte que se pueda
    desincronizar de la fecha.

    `orden` (IDENTITY, mismo patrón que `Folio.orden`) es el desempate real
    de "la más reciente": `now()` en Postgres es estable dentro de una
    misma transacción (`transaction_timestamp()`), así que dos filas
    insertadas en la misma transacción comparten `created_at` — un caso
    real, no hipotético, cuando dos llamadas seguidas a
    `POST /api/supervision/semestre/prorroga` caen en el mismo test o en
    la misma request."""

    __tablename__ = "prorroga_semestre"

    orden: Mapped[int] = mapped_column(Identity(always=False), nullable=False, unique=True)
    fecha_final: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    motivo: Mapped[str] = mapped_column(String(500), nullable=False)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
