"""Potencia (BHP) que el dinamómetro aplica en la prueba dinámica de
gasolina — los marcadores `<TOTPOT5024>`/`<TOTPOT2540>` de la plantilla del
cliente. Respuesta del cliente (2026-10-09): "es la potencia aplicada por el
dinamómetro (de acuerdo a la norma, debe asignarla el sistema)".

- Tabla 1 (fase PAS 5024): depende de la clasificación/carrocería del
  vehículo y del número de cilindros.
- Tabla 2 (fase 2540): depende solo del número de cilindros.

En el certificado real del cliente la fase 5024 ocupa la columna RALENTÍ y
la 2540 la de CRUCERO (23.7 / 39.3 km/h), así que así se proyectan.

Son valores de norma transcritos de las tablas que mandó el cliente, no
parámetros de negocio — por eso viven aquí y no en `cat_parametros_sistema`.
Pendiente de aclarar con el cliente: su sistema actual imprimió 7.8 en la
fase 5024 de una Tucson de 4 cilindros, valor que no aparece en la Tabla 1."""

CLASIFICACIONES_CARROCERIA = {
    "SEDAN": "Vehículo de pasajeros — Sedán",
    "GUAYIN": "Vehículo de pasajeros — Guayín",
    "PICK_UP": "Camión ligero (CL1) — Pick up (carrocería abierta)",
    "CERRADA": "CL1-CL4 y uso múltiple o utilitario — Carrocería cerrada",
    "MINIVAN": "Pasajeros, CL1 y uso múltiple o utilitario — Minivan",
    "PLATAFORMA": "CL1 y camión mediano o pesado — Plataforma, panel, van o estaquitas",
}

# Columnas: 1 a 3, 4, 5 a 6, 7 a 8, 9 o más cilindros.
_TABLA_5024 = {
    "SEDAN": (7.9, 11.4, 13.8, 16.4, 16.0),
    "GUAYIN": (8.1, 11.7, 13.8, 16.1, 16.1),
    "PICK_UP": (9.6, 13.1, 16.4, 19.2, 21.1),
    "CERRADA": (10.1, 13.4, 15.5, 19.4, 21.1),
    "MINIVAN": (10.2, 14.1, 15.8, 17.9, 18.2),
    "PLATAFORMA": (10.3, 13.9, 17.7, 19.6, 20.5),
}


def _columna_5024(cilindros: int) -> int:
    if cilindros <= 3:
        return 0
    if cilindros == 4:
        return 1
    if cilindros <= 6:
        return 2
    if cilindros <= 8:
        return 3
    return 4


def potencia_5024(clasificacion: str | None, cilindros: int | None) -> float | None:
    if not clasificacion or not cilindros or cilindros < 1:
        return None
    fila = _TABLA_5024.get(clasificacion)
    return None if fila is None else fila[_columna_5024(cilindros)]


def potencia_2540(cilindros: int | None) -> float | None:
    if not cilindros or cilindros < 1:
        return None
    if cilindros <= 4:
        return 3.5
    if cilindros <= 6:
        return 7.6
    return 9.6


def potencias_por_fase(clasificacion: str | None, cilindros: int | None) -> dict:
    """{'ralenti': BHP fase 5024, 'crucero': BHP fase 2540}; None donde falte
    el dato del vehículo (nunca se asume un valor)."""

    return {
        "ralenti": potencia_5024(clasificacion, cilindros),
        "crucero": potencia_2540(cilindros),
    }
