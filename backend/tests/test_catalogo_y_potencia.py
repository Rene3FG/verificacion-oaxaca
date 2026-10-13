"""Claves INEGI (app.services.catalogo_inegi) y potencia del dinamómetro
por norma (app.services.potencia_dinamometro) — respuesta del cliente del
2026-10-09."""

import pytest

from app.services.catalogo_inegi import (
    clave_entidad,
    clave_impresa,
    clave_municipio,
    municipios_oaxaca,
)
from app.services.potencia_dinamometro import potencia_2540, potencia_5024, potencias_por_fase


def test_catalogo_oaxaca_completo():
    municipios = municipios_oaxaca()
    assert len(municipios) == 570
    assert {"clave": "067", "nombre": "Oaxaca de Juárez"} in municipios


@pytest.mark.parametrize(
    "nombre,esperada",
    [("Oaxaca", "20"), ("OAXACA", "20"), ("20", "20"), ("Ciudad de México", "09"),
     ("CDMX", "09"), ("Michoacan", "16"), ("Texas", None), ("", None), (None, None)],
)
def test_clave_entidad(nombre, esperada):
    assert clave_entidad(nombre) == esperada


@pytest.mark.parametrize(
    "nombre,entidad,esperada",
    [("Oaxaca de Juárez", "Oaxaca", "067"), ("OAXACA DE JUAREZ", None, "067"),
     ("oaxaca de juarez", "20", "067"), ("67", "OAXACA", "067"),
     ("Santa Lucía del Camino", "Oaxaca", "390"), ("Oaxaca de Juárez", "Puebla", None),
     ("No existe", "Oaxaca", None), ("999", "Oaxaca", None)],
)
def test_clave_municipio(nombre, entidad, esperada):
    assert clave_municipio(nombre, entidad) == esperada


def test_clave_impresa_sin_ceros():
    assert clave_impresa("067") == "67"
    assert clave_impresa("20") == "20"
    assert clave_impresa(None) == ""


@pytest.mark.parametrize(
    "cilindros,esperada", [(1, 3.5), (4, 3.5), (5, 7.6), (6, 7.6), (7, 9.6), (12, 9.6), (None, None)]
)
def test_potencia_2540_tabla_2(cilindros, esperada):
    assert potencia_2540(cilindros) == esperada


@pytest.mark.parametrize(
    "clasificacion,cilindros,esperada",
    [("SEDAN", 3, 7.9), ("SEDAN", 4, 11.4), ("GUAYIN", 6, 13.8), ("PICK_UP", 8, 19.2),
     ("CERRADA", 4, 13.4), ("MINIVAN", 10, 18.2), ("PLATAFORMA", 5, 17.7),
     ("SEDAN", None, None), (None, 4, None), ("INVENTADA", 4, None)],
)
def test_potencia_5024_tabla_1(clasificacion, cilindros, esperada):
    assert potencia_5024(clasificacion, cilindros) == esperada


def test_potencias_por_fase_columnas_del_certificado():
    # En el certificado real: fase 5024 en la columna RALENTÍ, 2540 en CRUCERO.
    assert potencias_por_fase("CERRADA", 4) == {"ralenti": 13.4, "crucero": 3.5}
    assert potencias_por_fase(None, 4) == {"ralenti": None, "crucero": 3.5}
