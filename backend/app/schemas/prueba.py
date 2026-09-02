from pydantic import BaseModel

from app.models.enums import MetodoPrueba, TipoPrueba

# 'Certificate Result Projection Contract v1' (sección 4): reemplaza el
# editor libre de pares clave/valor. Solo estos campos entran a la
# sobreimpresión del certificado; cualquier otro dato de equipo (RPM,
# lambda, potencia, carga, dilution_factor) se recibe/audita aparte, sin
# columna dedicada, tal como indica el contrato ("permanecen como
# evidencia técnica y solo entrarán al certificado si una versión futura
# del layout los requiere explícitamente").
METODO_POR_TIPO_PRUEBA = {
    TipoPrueba.DINAMICA: MetodoPrueba.GAS_DYNAMIC,
    TipoPrueba.ESTATICA: MetodoPrueba.GAS_STATIC,
    TipoPrueba.OPACIDAD: MetodoPrueba.DIESEL_OPACITY,
}

# Parámetros con límite exigible por método (sección 4, bloques 02/03/04).
# NOx y velocidad son opcionales en el contrato ("si NOx o Km/h no
# aplican, dejar la posición vacía; nunca fabricar 0") — no participan en
# la evaluación de aprobado/rechazado. `co2_pct` se sigue leyendo (entra al
# certificado como parte de co_co2_pct), pero NOM-041 no define un "co2_pct
# máximo" — define un rango de dilución CO+CO2 (13%-16,5%), algo distinto
# a un límite de emisión por parámetro; decisión 2026-09-01: sacarlo de
# aquí hasta decidir cómo representar ese rango, en vez de inventar un
# máximo que la norma no da. NOx/lambda (también exigidos por la Tabla 1
# dinámica) tampoco están representados todavía — ver CLAUDE.md.
PARAMETROS_CON_LIMITE = {
    MetodoPrueba.GAS_STATIC: ("hc_ppm", "co_pct", "o2_pct"),
    MetodoPrueba.GAS_DYNAMIC: ("hc_ppm", "co_pct", "o2_pct"),
    MetodoPrueba.DIESEL_OPACITY: ("coefficient_absorption_final_k_m1",),
}


class LecturaFaseGasolina(BaseModel):
    hc_ppm: float
    co_pct: float
    co2_pct: float
    o2_pct: float
    nox_ppm: float | None = None
    speed_kph: float | None = None


class NormalizedPayloadGasolina(BaseModel):
    """Fases canónicas del método (sección 4, bloques 02/03): IDLE/PAS_5024
    -> columna física RALENTÍ; CRUISE/PAS_2540 -> columna física CRUCERO."""

    ralenti: LecturaFaseGasolina
    crucero: LecturaFaseGasolina


class NormalizedPayloadDiesel(BaseModel):
    """Solo `coefficient_absorption_final_k_m1` llega al certificado
    impreso (sección 4, bloque 04). El resto se conserva como
    evidencia/auditoría en `valores_medidos_json`, nunca se sobreimprime."""

    coefficient_absorption_final_k_m1: float
    engine_temp_c: float | None = None
    rpm_idle: float | None = None
    rpm_governed_max: float | None = None
    opacity_pct: float | None = None
    rpm_peak: float | None = None
    aceleraciones: list[dict] | None = None


class MetodoSinMapeo(Exception):
    """TipoPrueba sin método de proyección aprobado (hoy solo ALTERNA) —
    Preview/Print debe bloquearse por configuración, nunca inferir un
    mapping (sección 4, nota de pie del contrato)."""


def metodo_de(tipo_prueba: TipoPrueba | None) -> MetodoPrueba:
    metodo = METODO_POR_TIPO_PRUEBA.get(tipo_prueba) if tipo_prueba else None
    if metodo is None:
        raise MetodoSinMapeo(
            f"El tipo de prueba {tipo_prueba} no tiene un método de proyección "
            "de certificado aprobado; Preview/Print quedan bloqueados por "
            "configuración."
        )
    return metodo
