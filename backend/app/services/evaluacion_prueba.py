"""'Certificate Result Projection Contract v1' (revisión Figma 2026-08-24,
sección 4), implicación explícita: "el resultado APROBADO/RECHAZADO debe
calcularse en Prueba comparando lecturas contra limits_applied — no ser una
elección manual del operador". Este módulo hace esa comparación; el
operador ya no manda `resultado` en `POST /api/pruebas/resultado`.

Sin límites cargados en `LimiteEmision` para un método/fase/parámetro, se
rechaza con `LimitesNoConfigurados` (409) — nunca se inventa un umbral ni
se cae de vuelta a selección manual, mismo patrón que "Sin folio
disponible" en `app.services.folio_inventario`."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import FaseLectura, MetodoPrueba, ResultadoPruebaEnum
from app.models.limite_emision import LimiteEmision
from app.schemas.prueba import (
    PARAMETROS_CON_LIMITE,
    NormalizedPayloadDiesel,
    NormalizedPayloadGasolina,
)


class LimitesNoConfigurados(Exception):
    pass


def _en_rango_anio(anio: int | None, desde: int | None, hasta: int | None) -> bool:
    """NOM-041 estratifica los límites por año-modelo (p. ej. Tabla 1:
    1990 y anteriores / 1991 y posteriores). Si el vehículo no tiene
    año-modelo capturado, solo matchean filas sin acotar (desde y hasta
    ambos NULL) — nunca se asume un año para poder ubicarlo en un rango."""
    if anio is None:
        return desde is None and hasta is None
    if desde is not None and anio < desde:
        return False
    if hasta is not None and anio > hasta:
        return False
    return True


def _en_rango_peso(peso_kg: float | None, desde: float | None, hasta: float | None) -> bool:
    """Mismo criterio que `_en_rango_anio`, sobre `peso_bruto_vehicular_kg`
    (NOM-045 diésel, 2026-09-02). Si el vehículo no tiene peso capturado,
    solo matchean filas sin acotar — nunca se asume un peso para poder
    ubicarlo en un bracket."""
    if peso_kg is None:
        return desde is None and hasta is None
    if desde is not None and peso_kg < desde:
        return False
    if hasta is not None and peso_kg > hasta:
        return False
    return True


async def _limites_por_fase(
    db: AsyncSession,
    metodo: MetodoPrueba,
    fase: FaseLectura | None,
    *,
    anio_modelo: int | None = None,
    peso_bruto_kg: float | None = None,
) -> dict[str, float]:
    """Filtra por año-modelo (NOM-041 gasolina) y por peso bruto (NOM-045
    diésel) a la vez: cada norma solo estratifica por su propio eje, así
    que las filas de la otra dejan esas columnas en NULL/NULL y matchean
    siempre que el llamador correspondiente no les pase ese parámetro."""
    filas = (
        await db.execute(
            select(LimiteEmision).where(
                LimiteEmision.metodo == metodo, LimiteEmision.fase == fase
            )
        )
    ).scalars().all()
    return {
        fila.parametro: fila.valor_maximo
        for fila in filas
        if _en_rango_anio(anio_modelo, fila.anio_modelo_desde, fila.anio_modelo_hasta)
        and _en_rango_peso(peso_bruto_kg, fila.peso_bruto_desde_kg, fila.peso_bruto_hasta_kg)
    }


def _validar_completos(
    limites: dict[str, float], parametros: tuple[str, ...], etiqueta: str
) -> list[str]:
    return [f"{etiqueta}.{parametro}" for parametro in parametros if parametro not in limites]


async def evaluar_gasolina(
    db: AsyncSession,
    metodo: MetodoPrueba,
    payload: NormalizedPayloadGasolina,
    anio_modelo: int | None,
) -> tuple[ResultadoPruebaEnum, dict, dict]:
    limites_ralenti = await _limites_por_fase(
        db, metodo, FaseLectura.RALENTI, anio_modelo=anio_modelo
    )
    limites_crucero = await _limites_por_fase(
        db, metodo, FaseLectura.CRUCERO, anio_modelo=anio_modelo
    )

    parametros = PARAMETROS_CON_LIMITE[metodo]
    faltantes = _validar_completos(limites_ralenti, parametros, "ralenti") + _validar_completos(
        limites_crucero, parametros, "crucero"
    )
    if faltantes:
        raise LimitesNoConfigurados(
            f"Límites de emisión no configurados para {metodo.value}: {', '.join(faltantes)}. "
            "Contactar a Administración para cargar el catálogo (POST /api/pruebas/limites-emision)."
        )

    excedidos: dict[str, dict] = {}
    for etiqueta, lectura, limites in (
        ("ralenti", payload.ralenti, limites_ralenti),
        ("crucero", payload.crucero, limites_crucero),
    ):
        for parametro in parametros:
            valor = getattr(lectura, parametro)
            limite = limites[parametro]
            if valor > limite:
                excedidos[f"{etiqueta}.{parametro}"] = {"valor": valor, "limite": limite}

    resultado = ResultadoPruebaEnum.RECHAZADO if excedidos else ResultadoPruebaEnum.APROBADO
    limits_applied = {"ralenti": limites_ralenti, "crucero": limites_crucero}
    return resultado, limits_applied, excedidos


async def evaluar_diesel(
    db: AsyncSession,
    metodo: MetodoPrueba,
    payload: NormalizedPayloadDiesel,
    peso_bruto_kg: float | None,
) -> tuple[ResultadoPruebaEnum, dict, dict]:
    # NOM-045 estratifica por peso bruto vehicular, no por año-modelo (ver
    # docstring de LimiteEmision) — se recibe `peso_bruto_kg`, no
    # `anio_modelo`, a diferencia de evaluar_gasolina.
    limites = await _limites_por_fase(db, metodo, None, peso_bruto_kg=peso_bruto_kg)
    parametros = PARAMETROS_CON_LIMITE[metodo]
    faltantes = _validar_completos(limites, parametros, "diesel")
    if faltantes:
        raise LimitesNoConfigurados(
            f"Límites de emisión no configurados para {metodo.value}: {', '.join(faltantes)}. "
            "Contactar a Administración para cargar el catálogo (POST /api/pruebas/limites-emision)."
        )

    valor = payload.coefficient_absorption_final_k_m1
    limite = limites["coefficient_absorption_final_k_m1"]
    excedidos = {}
    if valor > limite:
        excedidos["coefficient_absorption_final_k_m1"] = {"valor": valor, "limite": limite}

    resultado = ResultadoPruebaEnum.RECHAZADO if excedidos else ResultadoPruebaEnum.APROBADO
    return resultado, limites, excedidos
