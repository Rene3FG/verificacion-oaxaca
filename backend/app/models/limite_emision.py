from sqlalchemy import Enum, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import FaseLectura, MetodoPrueba


class LimiteEmision(Base, UUIDPKMixin, TimestampMixin):
    """Catálogo de límites de emisión por método/fase/parámetro
    ('Certificate Result Projection Contract v1', sección 4). Reemplaza la
    elección manual de `resultado` por el operador: `evaluar_resultado`
    (app.services.evaluacion_prueba) compara las lecturas normalizadas
    contra estas filas.

    Los valores reales de la NOM (042 gasolina, 045 diésel) NO se cargan
    aquí por decisión explícita de esta sesión (2026-08-31) — fabricar un
    umbral regulatorio sin la tabla oficial sería peor que dejarlo vacío.
    Sin una fila para un método/fase/parámetro dado, `evaluar_resultado`
    rechaza con 409 ("límites no configurados"), nunca inventa ni cae a
    selección manual — mismo patrón que "Sin folio disponible" en
    `folio_inventario.py`. Administración carga esta tabla vía
    `POST /api/pruebas/limites-emision` cuando tenga la tabla oficial."""

    __tablename__ = "cat_limites_emision"
    __table_args__ = (
        UniqueConstraint(
            "metodo", "fase", "parametro", name="uq_limite_emision_metodo_fase_parametro"
        ),
    )

    metodo: Mapped[MetodoPrueba] = mapped_column(
        Enum(MetodoPrueba, name="metodo_prueba"), nullable=False
    )
    fase: Mapped[FaseLectura | None] = mapped_column(
        Enum(FaseLectura, name="fase_lectura"), nullable=True
    )
    parametro: Mapped[str] = mapped_column(String(40), nullable=False)
    valor_maximo: Mapped[float] = mapped_column(Float, nullable=False)
