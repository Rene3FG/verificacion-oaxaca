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


async def _limites_por_fase(
    db: AsyncSession, metodo: MetodoPrueba, fase: FaseLectura | None
) -> dict[str, float]:
    filas = (
        await db.execute(
            select(LimiteEmision).where(
                LimiteEmision.metodo == metodo, LimiteEmision.fase == fase
            )
        )
    ).scalars().all()
    return {fila.parametro: fila.valor_maximo for fila in filas}


def _validar_completos(
    limites: dict[str, float], parametros: tuple[str, ...], etiqueta: str
) -> list[str]:
    return [f"{etiqueta}.{parametro}" for parametro in parametros if parametro not in limites]


async def evaluar_gasolina(
    db: AsyncSession, metodo: MetodoPrueba, payload: NormalizedPayloadGasolina
) -> tuple[ResultadoPruebaEnum, dict, dict]:
    limites_ralenti = await _limites_por_fase(db, metodo, FaseLectura.RALENTI)
    limites_crucero = await _limites_por_fase(db, metodo, FaseLectura.CRUCERO)

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
    db: AsyncSession, metodo: MetodoPrueba, payload: NormalizedPayloadDiesel
) -> tuple[ResultadoPruebaEnum, dict, dict]:
    limites = await _limites_por_fase(db, metodo, None)
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
