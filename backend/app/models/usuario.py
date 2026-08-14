from sqlalchemy import Boolean, String
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
