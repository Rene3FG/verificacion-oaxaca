from sqlalchemy import Enum, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import FaseLectura, MetodoPrueba


class LimiteEmision(Base, UUIDPKMixin, TimestampMixin):
    """Catálogo de límites de emisión por método/fase/parámetro/año-modelo
    ('Certificate Result Projection Contract v1', sección 4). Reemplaza la
    elección manual de `resultado` por el operador: `evaluar_resultado`
    (app.services.evaluacion_prueba) compara las lecturas normalizadas
    contra estas filas.

    `anio_modelo_desde`/`anio_modelo_hasta` (ambos NULL por defecto = sin
    acotar) reflejan que NOM-041-SEMARNAT-2015 estratifica sus límites por
    año-modelo del vehículo (Tabla 1 dinámico: 1990 y anteriores / 1991 y
    posteriores; Tabla 2 estático: 1993 y anteriores / 1994 y posteriores)
    — agregado 2026-09-01 al cargar la tabla oficial (antes solo existía
    metodo+fase+parametro, sin poder representar el corte por año).
    `evaluar_resultado` elige la fila cuyo rango contiene el año-modelo del
    vehículo; si el vehículo no tiene año-modelo capturado, solo matchean
    filas sin acotar (ambos NULL) — nunca asume un año.

    Los valores reales de NOM-041 (gasolina, cargados 2026-09-01 desde el
    DOF) ya están en esta tabla vía `app/seed_limites_nom041.py`. NOM-045
    (diésel, opacidad) sigue vacío a propósito: su tabla oficial estratifica
    por PESO BRUTO VEHICULAR, no por año-modelo — este esquema todavía no
    tiene esa columna, fabricar un valor sin ella sería peor que dejarlo
    vacío. Sin una fila que matchee para un método/fase/parámetro/año dado,
    `evaluar_resultado` rechaza con 409 ("límites no configurados"), nunca
    inventa ni cae a selección manual — mismo patrón que "Sin folio
    disponible" en `folio_inventario.py`. Administración carga/corrige esta
    tabla vía `POST /api/pruebas/limites-emision`."""

    __tablename__ = "cat_limites_emision"
    __table_args__ = (
        UniqueConstraint(
            "metodo",
            "fase",
            "parametro",
            "anio_modelo_desde",
            "anio_modelo_hasta",
            name="uq_limite_emision_metodo_fase_parametro_anio",
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
    anio_modelo_desde: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anio_modelo_hasta: Mapped[int | None] = mapped_column(Integer, nullable=True)
