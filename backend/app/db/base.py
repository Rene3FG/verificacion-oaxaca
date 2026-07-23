import datetime
import uuid

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    # Todo Mapped[datetime.datetime] usa TIMESTAMP WITH TIME ZONE por
    # default; el resto del código siempre construye datetimes en UTC
    # tz-aware (datetime.now(datetime.timezone.utc)) y Postgres rechaza
    # mezclar naive/aware en la misma columna.
    type_annotation_map = {
        datetime.datetime: DateTime(timezone=True),
    }


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
