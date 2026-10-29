"""Claves geoestadísticas de INEGI para el certificado (respuesta del
cliente, 2026-10-09): en "Mpio." va la clave del municipio (Oaxaca de
Juárez → 67) y en "Estado" la clave de la entidad (Oaxaca → 20), mientras
que "Población" va en texto.

Los 2 478 municipios de las 32 entidades vienen del Marco Geoestadístico de
INEGI (`gaia.inegi.org.mx/wscatgeo/v2/mgem/{entidad}`; Oaxaca descargado
2026-10-12, el resto 2026-10-28, misma fuente) en
`app/data/municipios_mexico.json`, indexado por clave de entidad. Un
propietario con domicilio en otro estado también imprime la clave de su
municipio.

Las claves no se guardan en `Vehiculo`: se derivan del nombre al imprimir,
así que Captura debe elegir el nombre del catálogo (`GET
/api/catalogos/municipios`) para que coincida."""

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

CLAVE_OAXACA = "20"

ENTIDADES = {
    "01": "Aguascalientes",
    "02": "Baja California",
    "03": "Baja California Sur",
    "04": "Campeche",
    "05": "Coahuila de Zaragoza",
    "06": "Colima",
    "07": "Chiapas",
    "08": "Chihuahua",
    "09": "Ciudad de México",
    "10": "Durango",
    "11": "Guanajuato",
    "12": "Guerrero",
    "13": "Hidalgo",
    "14": "Jalisco",
    "15": "México",
    "16": "Michoacán de Ocampo",
    "17": "Morelos",
    "18": "Nayarit",
    "19": "Nuevo León",
    "20": "Oaxaca",
    "21": "Puebla",
    "22": "Querétaro",
    "23": "Quintana Roo",
    "24": "San Luis Potosí",
    "25": "Sinaloa",
    "26": "Sonora",
    "27": "Tabasco",
    "28": "Tamaulipas",
    "29": "Tlaxcala",
    "30": "Veracruz de Ignacio de la Llave",
    "31": "Yucatán",
    "32": "Zacatecas",
}

# Nombres cortos/comunes que el operador o SIOX pueden escribir.
_ALIAS_ENTIDAD = {
    "COAHUILA": "05",
    "CDMX": "09",
    "DISTRITO FEDERAL": "09",
    "ESTADO DE MEXICO": "15",
    "EDO DE MEXICO": "15",
    "MICHOACAN": "16",
    "VERACRUZ": "30",
}


def _normalizar(texto: str) -> str:
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_acentos.upper().replace(".", " ").split())


@lru_cache(maxsize=1)
def _municipios_por_entidad() -> dict[str, list[dict]]:
    ruta = Path(__file__).resolve().parent.parent / "data" / "municipios_mexico.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


def municipios(clave_ent: str) -> list[dict]:
    """Municipios de una entidad ('20' → los 570 de Oaxaca); [] si no existe."""

    return _municipios_por_entidad().get(clave_ent, [])


def municipios_oaxaca() -> list[dict]:
    return municipios(CLAVE_OAXACA)


@lru_cache(maxsize=32)
def _indice_municipios(clave_ent: str) -> dict[str, str]:
    return {_normalizar(m["nombre"]): m["clave"] for m in municipios(clave_ent)}


@lru_cache(maxsize=1)
def _indice_entidades() -> dict[str, str]:
    indice = {_normalizar(nombre): clave for clave, nombre in ENTIDADES.items()}
    indice.update(_ALIAS_ENTIDAD)
    return indice


def clave_entidad(nombre: str | None) -> str | None:
    """'Oaxaca' → '20'. Acepta también la clave ya escrita ('20')."""

    if not nombre or not nombre.strip():
        return None
    texto = nombre.strip()
    if texto.isdigit() and texto.zfill(2) in ENTIDADES:
        return texto.zfill(2)
    return _indice_entidades().get(_normalizar(texto))


def clave_municipio(nombre: str | None, entidad: str | None) -> str | None:
    """'Oaxaca de Juárez' (entidad Oaxaca) → '067'. Sin entidad capturada
    se asume Oaxaca (el sistema opera en el estado); entidad no reconocida
    → None."""

    if not nombre or not nombre.strip():
        return None
    clave_ent = clave_entidad(entidad) if entidad else CLAVE_OAXACA
    if clave_ent is None:
        return None
    texto = nombre.strip()
    if texto.isdigit():
        clave = texto.zfill(3)
        return clave if any(m["clave"] == clave for m in municipios(clave_ent)) else None
    return _indice_municipios(clave_ent).get(_normalizar(texto))


def clave_impresa(clave: str | None) -> str:
    """Las claves se imprimen sin ceros a la izquierda, igual que el sistema
    en operación ('067' → '67', '20' → '20')."""

    return str(int(clave)) if clave else ""
