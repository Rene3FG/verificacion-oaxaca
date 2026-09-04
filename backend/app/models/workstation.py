import datetime
import uuid

from sqlalchemy import ARRAY, Boolean, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import StationType


class Workstation(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "workstations"

    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    station_type: Mapped[StationType] = mapped_column(
        Enum(StationType, name="station_type"), nullable=False
    )
    center_id: Mapped[str] = mapped_column(String(60), nullable=False)
    line_id: Mapped[int | None] = mapped_column(Integer)
    is_centralized: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_line_ids: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
    device_identifier: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Sección 10 del handoff (revisión Figma 2026-08-24): "Capacidad máxima
    # del dinamómetro, configurable por equipo/línea" — sin valor único
    # global (a diferencia de obd_modelo_minimo), por eso vive aquí y no en
    # cat_parametros_sistema. Solo tiene sentido en estaciones PRUEBA;
    # NULL = sin configurar (no participa en la determinación del tipo de
    # prueba, ver app.api.routers.pruebas.configurar_prueba).
    capacidad_dinamometro_kg: Mapped[float | None] = mapped_column(Float)


class StationSession(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "station_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workstation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workstations.id"), nullable=False
    )
    station_type: Mapped[StationType] = mapped_column(
        Enum(StationType, name="station_type")
    )
    center_id: Mapped[str | None] = mapped_column(String(60))
    line_id: Mapped[int | None] = mapped_column(Integer)
    login_at: Mapped[datetime.datetime | None] = mapped_column()
    logout_at: Mapped[datetime.datetime | None] = mapped_column()
    ip_address: Mapped[str | None] = mapped_column(String(45))
    device_fingerprint: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="activa")


class UserStationPermission(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "user_station_permissions"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    station_type: Mapped[StationType] = mapped_column(
        Enum(StationType, name="station_type")
    )
    center_id: Mapped[str] = mapped_column(String(60), nullable=False)
    line_id: Mapped[int | None] = mapped_column(Integer)
    can_operate: Mapped[bool] = mapped_column(Boolean, default=True)
    can_supervise: Mapped[bool] = mapped_column(Boolean, default=False)
