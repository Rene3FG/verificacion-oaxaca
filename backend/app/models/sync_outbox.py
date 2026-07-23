import datetime
import uuid

from sqlalchemy import JSON, Enum, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import SyncStatus


class SyncOutbox(Base, UUIDPKMixin, TimestampMixin):
    """Cola de sincronización servidor-local -> nube. `entity_uuid` es el
    identificador idempotente: el central deduplica por él, nunca por
    orden de llegada."""

    __tablename__ = "sync_outbox"

    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    operation: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime.datetime | None] = mapped_column()
    sync_status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, name="sync_status"), default=SyncStatus.PENDING
    )
    server_response: Mapped[dict | None] = mapped_column(JSON)
