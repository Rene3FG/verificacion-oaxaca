from sqlalchemy import Boolean, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class CatUsuario(Base, UUIDPKMixin, TimestampMixin):
    """HU-119: identidad real de quien opera una estación. Antes el login
    solo recibía un user_id sin contraseña (cualquier UUID servía siempre
    que existiera un UserStationPermission para él). Los roles/permisos por
    estación siguen viviendo en UserStationPermission (HU-121); esta tabla
    solo resuelve "quién eres", no "qué puedes hacer"."""

    __tablename__ = "cat_usuarios"

    username: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # NOM-047 punto 5 (B10-b, 2026-10-30): el campo 001 del certificado es
    # el ID del técnico. Opcional porque Supervisores/Administradores no
    # firman pruebas; única entre quienes la tienen (UNIQUE admite varios NULL).
    clave_tecnico: Mapped[str | None] = mapped_column(String(20), unique=True)
    # X6-b: activo al crear el usuario o cuando un supervisor le restablece
    # la contraseña; mientras siga activo la API solo le permite cambiarla
    # (así el supervisor deja de conocer la contraseña definitiva).
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
