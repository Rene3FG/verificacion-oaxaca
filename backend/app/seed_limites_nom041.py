"""Carga la tabla oficial de NOM-041-SEMARNAT-2015 (límites máximos
permisibles de emisión de gases contaminantes, vehículos en circulación que
usan gasolina) en `cat_limites_emision`.

Fuente: Diario Oficial de la Federación, 10 de junio de 2015, numeral 4.2
(TABLA 1 — Método Dinámico, TABLA 2 — Método Estático). Verificado dos veces
por fetch independiente el 2026-09-23 (PROFEPA PDF + dof.gob.mx, mismos
valores en ambos):
https://www.profepa.gob.mx/innovaportal/file/7251/1/nom-041-semarnat-2015.pdf
https://dof.gob.mx/nota_detalle.php?codigo=5396063&fecha=10/06/2015

HC/CO/O2 (evaluados, ver `app.schemas.prueba.PARAMETROS_CON_LIMITE`) +
NOx/Factor Lambda (cargados en catálogo 2026-09-23, **NO conectados a
evaluar_resultado todavía** — decisión explícita del usuario: el contrato
de integración de hardware, sección "Equipment Integration Contract v1" del
Figma, sigue sin construirse, y conectar estos parámetros ya podría
rechazar pruebas reales de centros cuyo equipo físico no los reporta.
Administración ya puede verlos/corregirlos vía
`POST /api/pruebas/limites-emision`, quedan listos para cuando se decida
volverlos exigibles). NOx solo aplica a método dinámico (TABLA 2 estático
no tiene columna de NOx en la norma).

El rango de dilución CO+CO2 [13%-16,5% vol.] (ambas tablas) se carga aquí
(2026-09-24, migración `a7c4e02f5b1d` agregó `valor_minimo`) como el
parámetro sintético `co_co2_dilucion_pct` — no es un máximo por
contaminante sino un rango de validez de la muestra (co_pct + co2_pct
dentro del rango). **Mismo criterio que NOx/Lambda: se carga en el
catálogo pero NO se conecta a `evaluar_resultado`** — falta decidir qué
pasa con un expediente fuera de rango (¿rechazo igual que un contaminante
excedido, o solo nota de auditoría?), decisión de producto pendiente, no
una cuestión técnica. Aplica a ambos métodos (dinámico y estático), ambas
fases.

RALENTI y CRUCERO se cargan con el MISMO valor: ambas tablas oficiales dan
un solo set de límites por año-modelo (no separan ralentí de crucero) — se
asume que corresponden a los dos modos de una prueba bimodal que comparten
el mismo límite (ver `NormalizedPayloadGasolina`), confirmado con el
usuario antes de cargar.

NOM-045-SEMARNAT-2017 (diésel, opacidad) NO se carga aquí: estratifica por
peso bruto vehicular, no por año-modelo — ver `app.seed_limites_nom045`.

Idempotente: upsert por metodo+fase+parametro+anio_modelo_desde+
anio_modelo_hasta (mismo criterio que `POST /api/pruebas/limites-emision`).

Uso: python -m app.seed_limites_nom041
"""

import asyncio

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.enums import FaseLectura, MetodoPrueba
from app.models.limite_emision import LimiteEmision

# (metodo, anio_modelo_desde, anio_modelo_hasta, hc_ppm, co_pct, o2_pct,
#  nox_ppm, lambda_factor) — nox_ppm es None para GAS_STATIC (la norma no
# mide NOx en método estático).
TABLA_NOM_041 = [
    # TABLA 1 — Método Dinámico
    (MetodoPrueba.GAS_DYNAMIC, None, 1990, 350, 2.5, 2.0, 2500, 1.05),
    (MetodoPrueba.GAS_DYNAMIC, 1991, None, 100, 1.0, 2.0, 1500, 1.05),
    # TABLA 2 — Método Estático
    (MetodoPrueba.GAS_STATIC, None, 1993, 400, 3.0, 2.0, None, 1.05),
    (MetodoPrueba.GAS_STATIC, 1994, None, 100, 1.0, 2.0, None, 1.05),
]

# Rango de dilución CO+CO2, sin estratificar por año-modelo (la norma no lo
# corta por año, a diferencia de HC/CO/O2/NOx) — mismo rango para ambos
# métodos y ambas fases.
DILUCION_CO_CO2_MIN = 13.0
DILUCION_CO_CO2_MAX = 16.5


async def _upsert_limite(
    db,
    *,
    metodo: MetodoPrueba,
    fase: FaseLectura | None,
    parametro: str,
    valor_maximo: float,
    valor_minimo: float | None = None,
    anio_modelo_desde: int | None = None,
    anio_modelo_hasta: int | None = None,
) -> str:
    existente = (
        await db.execute(
            select(LimiteEmision).where(
                LimiteEmision.metodo == metodo,
                LimiteEmision.fase == fase,
                LimiteEmision.parametro == parametro,
                LimiteEmision.anio_modelo_desde == anio_modelo_desde,
                LimiteEmision.anio_modelo_hasta == anio_modelo_hasta,
            )
        )
    ).scalars().first()
    if existente is not None:
        if existente.valor_maximo != valor_maximo or existente.valor_minimo != valor_minimo:
            existente.valor_maximo = valor_maximo
            existente.valor_minimo = valor_minimo
            db.add(existente)
            return "actualizado"
        return "sin_cambio"
    db.add(
        LimiteEmision(
            metodo=metodo,
            fase=fase,
            parametro=parametro,
            valor_maximo=valor_maximo,
            valor_minimo=valor_minimo,
            anio_modelo_desde=anio_modelo_desde,
            anio_modelo_hasta=anio_modelo_hasta,
        )
    )
    return "insertado"


async def cargar_limites_nom041() -> None:
    async with SessionLocal() as db:
        insertados = 0
        actualizados = 0
        for metodo, desde, hasta, hc_ppm, co_pct, o2_pct, nox_ppm, lambda_factor in TABLA_NOM_041:
            valores = {"hc_ppm": hc_ppm, "co_pct": co_pct, "o2_pct": o2_pct, "lambda_factor": lambda_factor}
            if nox_ppm is not None:
                valores["nox_ppm"] = nox_ppm
            for fase in (FaseLectura.RALENTI, FaseLectura.CRUCERO):
                for parametro, valor_maximo in valores.items():
                    resultado = await _upsert_limite(
                        db,
                        metodo=metodo,
                        fase=fase,
                        parametro=parametro,
                        valor_maximo=valor_maximo,
                        anio_modelo_desde=desde,
                        anio_modelo_hasta=hasta,
                    )
                    if resultado == "insertado":
                        insertados += 1
                    elif resultado == "actualizado":
                        actualizados += 1

        for metodo in (MetodoPrueba.GAS_DYNAMIC, MetodoPrueba.GAS_STATIC):
            for fase in (FaseLectura.RALENTI, FaseLectura.CRUCERO):
                resultado = await _upsert_limite(
                    db,
                    metodo=metodo,
                    fase=fase,
                    parametro="co_co2_dilucion_pct",
                    valor_maximo=DILUCION_CO_CO2_MAX,
                    valor_minimo=DILUCION_CO_CO2_MIN,
                )
                if resultado == "insertado":
                    insertados += 1
                elif resultado == "actualizado":
                    actualizados += 1

        await db.commit()
        print(f"NOM-041: {insertados} filas insertadas, {actualizados} actualizadas.")


if __name__ == "__main__":
    asyncio.run(cargar_limites_nom041())
