"""Checklist real de inspección visual — sección 8 de la revisión del Figma
(2026-08-24): 8 puntos específicos observados en la pantalla "Captura /
Inspección visual — Pendiente", cada uno con resultado Bueno/Malo/No aplica.
Reemplaza el checklist booleano de 8 puntos que se había propuesto a falta
del documento de diseño (sesión 2026-08-14).

El resultado APROBADA/RECHAZADA ya no lo elige el operador: se determina de
los ítems — cualquier punto en MALO rechaza la inspección, y esos puntos son
las causales de rechazo. Mismo espíritu que el contrato de proyección del
certificado ("no es una elección manual del operador")."""

from app.models.enums import ResultadoInspeccionVisual, ResultadoItemInspeccion

# Clave estable → etiqueta legible. El frontend consume este catálogo vía
# GET /api/inspeccion/checklist, no lo duplica.
CHECKLIST_INSPECCION_VISUAL: dict[str, str] = {
    "sistema_escape": "Sistema de escape: sin fugas",
    "portafiltro_filtro_aire": "Portafiltro y filtro de aire: existen y operan adecuadamente",
    "tapon_aceite": "Tapón del dispositivo de aceite: existe",
    "tapon_combustible": "Tapón de combustible: existe",
    "bayoneta_nivel_aceite": "Bayoneta de nivel de aceite: existe",
    "fugas_fluidos": "Sin fugas de aceite de motor, transmisión o refrigerante",
    "neumaticos": "Neumáticos: dibujo, condición, dimensiones y tipo",
    "componentes_emisiones": "Componentes de control de emisiones: no desconectados",
}


class ChecklistInvalido(Exception):
    pass


def evaluar_checklist(
    checklist: dict[str, ResultadoItemInspeccion],
) -> tuple[ResultadoInspeccionVisual, dict[str, str]]:
    """Valida que el checklist cubra exactamente los 8 puntos del catálogo y
    determina el resultado: cualquier ítem MALO → RECHAZADA, con esos ítems
    (clave → etiqueta) como causales; si no, APROBADA con causales vacías."""

    faltantes = CHECKLIST_INSPECCION_VISUAL.keys() - checklist.keys()
    desconocidos = checklist.keys() - CHECKLIST_INSPECCION_VISUAL.keys()
    if faltantes or desconocidos:
        partes = []
        if faltantes:
            partes.append(f"faltan puntos del checklist: {', '.join(sorted(faltantes))}")
        if desconocidos:
            partes.append(f"puntos desconocidos: {', '.join(sorted(desconocidos))}")
        raise ChecklistInvalido("; ".join(partes))

    causales = {
        clave: CHECKLIST_INSPECCION_VISUAL[clave]
        for clave, resultado in checklist.items()
        if resultado == ResultadoItemInspeccion.MALO
    }
    resultado = (
        ResultadoInspeccionVisual.RECHAZADA if causales else ResultadoInspeccionVisual.APROBADA
    )
    return resultado, causales
