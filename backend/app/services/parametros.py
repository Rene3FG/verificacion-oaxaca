"""Lectura de parámetros de negocio configurables desde `cat_parametros_sistema`.

Regla de negocio #4 y convención de código: valores como obd_modelo_minimo
NUNCA deben quedar como constantes en el código; siempre se leen de BD."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalogos import CatParametroSistema

DEFAULTS = {
    "obd_modelo_minimo": "2006",
    "gasolina_prueba_default": "dinamica",
    "gasolina_permite_cambio_estatica": "true",
    "folios_origen": "sistema_externo",
}


async def get_parametro(db: AsyncSession, clave: str) -> str:
    result = await db.execute(
        select(CatParametroSistema).where(CatParametroSistema.clave == clave)
    )
    parametro = result.scalar_one_or_none()
    if parametro is not None:
        return parametro.valor
    if clave in DEFAULTS:
        return DEFAULTS[clave]
    raise KeyError(f"Parámetro de sistema no encontrado: {clave}")


async def obd_aplica(
    db: AsyncSession,
    *,
    inspeccion_aprobada: bool,
    tipo_vehiculo: str,
    combustible: str,
    modelo: int,
) -> bool:
    """Regla de negocio #4: OBD/SBD aplica solo si la inspección visual fue
    aprobada, el tipo de unidad es 'vehiculo', el combustible es gasolina y
    el modelo es >= obd_modelo_minimo (parámetro configurable)."""

    if not inspeccion_aprobada:
        return False
    if tipo_vehiculo.lower() != "vehiculo":
        return False
    if combustible.lower() != "gasolina":
        return False

    modelo_minimo = int(await get_parametro(db, "obd_modelo_minimo"))
    return modelo >= modelo_minimo
