"""Carga la tabla oficial de NOM-045-SEMARNAT-2017 (límites máximos
permisibles de opacidad de humo, vehículos en circulación con motor a
diésel) en `cat_limites_emision`.

Fuente: Diario Oficial de la Federación, numerales 4.1 (TABLA 1) y 4.2
(TABLA 2).
https://dof.gob.mx/normasOficiales/7015/semarnat4a11_C/semarnat4a11_C.html

**Corrección 2026-09-03**: la sesión 2026-09-02 asumió que NOM-045
estratifica solo por peso bruto vehicular (PBV) — verificado ahora contra
el texto oficial, TABLA 1 y TABLA 2 separan primero por PBV (hasta 3,856 kg
/ mayor a 3,856 kg) y CADA UNA da límites distintos por año-modelo. Se
cargan los 4 brackets (2 PBV × 2 año) con AMBOS ejes a la vez, no solo
peso. Ver docstring de `app.models.limite_emision.LimiteEmision`.

Solo `coefficient_absorption_final_k_m1` participa en la evaluación
(`app.schemas.prueba.PARAMETROS_CON_LIMITE`); el "por ciento de opacidad"
de la tabla oficial es el mismo umbral expresado en otra unidad, no un
parámetro adicional — no se carga por separado (evitar un límite fantasma
que nunca se compara).

El corte "mayor a 3,856 kg" es una desigualdad estricta; `peso_bruto_desde_kg`
usa `3856.01` (no `3856`) para no traslapar con el bracket "hasta 3,856 kg"
de la otra tabla — `_en_rango_peso` es de rango cerrado (`desde <= peso <=
hasta`), así que un vehículo de exactamente 3,856 kg debe caer solo en la
TABLA 1.

Idempotente: upsert por metodo+fase+parametro+anio_modelo_desde+
anio_modelo_hasta+peso_bruto_desde_kg+peso_bruto_hasta_kg (mismo criterio
que `seed_limites_nom041.py`).

Uso: python -m app.seed_limites_nom045
"""

import asyncio

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.enums import MetodoPrueba
from app.models.limite_emision import LimiteEmision

# (peso_desde, peso_hasta, anio_desde, anio_hasta, valor_maximo_k_m1)
TABLA_NOM_045 = [
    # TABLA 1 — PBV hasta 3,856 kg
    (None, 3856, None, 2003, 2.00),
    (None, 3856, 2004, None, 1.50),
    # TABLA 2 — PBV mayor a 3,856 kg
    (3856.01, None, None, 1997, 2.25),
    (3856.01, None, 1998, None, 1.50),
]


async def cargar_limites_nom045() -> None:
    async with SessionLocal() as db:
        insertados = 0
        actualizados = 0
        for peso_desde, peso_hasta, anio_desde, anio_hasta, valor_maximo in TABLA_NOM_045:
            existente = (
                await db.execute(
                    select(LimiteEmision).where(
                        LimiteEmision.metodo == MetodoPrueba.DIESEL_OPACITY,
                        LimiteEmision.fase.is_(None),
                        LimiteEmision.parametro == "coefficient_absorption_final_k_m1",
                        LimiteEmision.anio_modelo_desde == anio_desde,
                        LimiteEmision.anio_modelo_hasta == anio_hasta,
                        LimiteEmision.peso_bruto_desde_kg == peso_desde,
                        LimiteEmision.peso_bruto_hasta_kg == peso_hasta,
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
                        metodo=MetodoPrueba.DIESEL_OPACITY,
                        fase=None,
                        parametro="coefficient_absorption_final_k_m1",
                        valor_maximo=valor_maximo,
                        anio_modelo_desde=anio_desde,
                        anio_modelo_hasta=anio_hasta,
                        peso_bruto_desde_kg=peso_desde,
                        peso_bruto_hasta_kg=peso_hasta,
                    )
                )
                insertados += 1
        await db.commit()
        print(f"NOM-045: {insertados} filas insertadas, {actualizados} actualizadas.")


if __name__ == "__main__":
    asyncio.run(cargar_limites_nom045())
