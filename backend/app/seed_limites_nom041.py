"""Carga la tabla oficial de NOM-041-SEMARNAT-2015 (límites máximos
permisibles de emisión de gases contaminantes, vehículos en circulación que
usan gasolina) en `cat_limites_emision`.

Fuente: Diario Oficial de la Federación, 10 de junio de 2015, numeral 4.2
(TABLA 1 — Método Dinámico, TABLA 2 — Método Estático).
https://www.profepa.gob.mx/innovaportal/file/7251/1/nom-041-semarnat-2015.pdf

Solo HC/CO/O2 (ver `app.schemas.prueba.PARAMETROS_CON_LIMITE` — decisión
2026-09-01: la norma no da un "co2_pct máximo" por sí solo, da un rango de
dilución CO+CO2 [13%-16,5%] que este esquema todavía no representa; NOx y
Factor Lambda, también exigidos por la Tabla 1 dinámica, tampoco están
representados todavía). RALENTI y CRUCERO se cargan con el MISMO valor:
ambas tablas oficiales dan un solo set de límites por año-modelo (no
separan ralentí de crucero) — se asume que corresponden a los dos modos de
una prueba bimodal que comparten el mismo límite (ver
`NormalizedPayloadGasolina`), confirmado con el usuario antes de cargar.

NOM-045-SEMARNAT-2017 (diésel, opacidad) NO se carga aquí: estratifica por
peso bruto vehicular, no por año-modelo, y `cat_limites_emision` todavía no
tiene esa columna — cargar solo el número de opacidad sin poder acotar por
peso sería fabricar un límite que no aplica a todos los vehículos por
igual. Queda pendiente (ver CLAUDE.md).

Idempotente: upsert por metodo+fase+parametro+anio_modelo_desde+
anio_modelo_hasta (mismo criterio que `POST /api/pruebas/limites-emision`).

Uso: python -m app.seed_limites_nom041
"""

import asyncio

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.enums import FaseLectura, MetodoPrueba
from app.models.limite_emision import LimiteEmision

# (metodo, anio_modelo_desde, anio_modelo_hasta, hc_ppm, co_pct, o2_pct)
TABLA_NOM_041 = [
    # TABLA 1 — Método Dinámico
    (MetodoPrueba.GAS_DYNAMIC, None, 1990, 350, 2.5, 2.0),
    (MetodoPrueba.GAS_DYNAMIC, 1991, None, 100, 1.0, 2.0),
    # TABLA 2 — Método Estático
    (MetodoPrueba.GAS_STATIC, None, 1993, 400, 3.0, 2.0),
    (MetodoPrueba.GAS_STATIC, 1994, None, 100, 1.0, 2.0),
]


async def cargar_limites_nom041() -> None:
    async with SessionLocal() as db:
        insertados = 0
        actualizados = 0
        for metodo, desde, hasta, hc_ppm, co_pct, o2_pct in TABLA_NOM_041:
            valores = {"hc_ppm": hc_ppm, "co_pct": co_pct, "o2_pct": o2_pct}
            for fase in (FaseLectura.RALENTI, FaseLectura.CRUCERO):
                for parametro, valor_maximo in valores.items():
                    existente = (
                        await db.execute(
                            select(LimiteEmision).where(
                                LimiteEmision.metodo == metodo,
                                LimiteEmision.fase == fase,
                                LimiteEmision.parametro == parametro,
                                LimiteEmision.anio_modelo_desde == desde,
                                LimiteEmision.anio_modelo_hasta == hasta,
                            )
                        )
                    ).scalars().first()
                    if existente is not None:
                        if existente.valor_maximo != valor_maximo:
                            existente.valor_maximo = valor_maximo
                            db.add(existente)
                            actualizados += 1
                    else:
                        db.add(
                            LimiteEmision(
                                metodo=metodo,
                                fase=fase,
                                parametro=parametro,
                                valor_maximo=valor_maximo,
                                anio_modelo_desde=desde,
                                anio_modelo_hasta=hasta,
                            )
                        )
                        insertados += 1
        await db.commit()
        print(f"NOM-041: {insertados} filas insertadas, {actualizados} actualizadas.")


if __name__ == "__main__":
    asyncio.run(cargar_limites_nom041())
