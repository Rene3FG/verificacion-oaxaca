"""Cliente SIOX (consulta pública de placa en pagoTenencia).

Request capturado por ingeniería inversa contra
https://siox.finanzasoaxaca.gob.mx/pagoTenencia: POST
application/x-www-form-urlencoded a busquedaVehiculo.htm con
placa=<PLACA>&serie= (o al revés para buscar por VIN). Sin CSRF ni cookies de
sesión — endpoint público sin estado. La respuesta es un fragmento HTML (no
JSON); un vehículo inexistente responde 200 con el texto "No existe un
vehiculo con serie o placa ingresada" en vez del bloque de datos.

Cuidado: el HTML de SIOX reutiliza id="labelVersion" para tres campos
distintos (LINEA, VERSIÓN y MOTOR), y el id="labelLinea" en realidad contiene
el valor de MARCA. Los ids no son selectores confiables — se parsea por el
texto del label de campo (p.ej. "MARCA:") emparejado con el label vecino.
"""

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings

NOT_FOUND_TEXT = "No existe un vehiculo con serie o placa ingresada"

FIELD_MAP = {
    "NÚMERO DE SERIE": "niv",
    "ESTATUS": "estatus",
    "PLACAS": "placa",
    "MODELO": "modelo",
    "CLASIFICACIÓN": "tipo_vehiculo",
    "MARCA": "marca",
    "LINEA": "linea",
    "VERSIÓN": "version",
    "MOTOR": "motor",
}


class SioxConsultaResultado:
    def __init__(self, status: str, raw: dict | None, normalized: dict | None):
        self.status = status  # "EXITOSA" | "SIN_DATOS" | "ERROR"
        self.raw = raw
        self.normalized = normalized


def _parse_respuesta(html: str) -> dict[str, str] | None:
    soup = BeautifulSoup(html, "html.parser")
    if NOT_FOUND_TEXT in soup.get_text():
        return None

    datos: dict[str, str] = {}
    for div in soup.find_all("div"):
        labels = div.find_all("label", recursive=False)
        if len(labels) == 2 and "control-label" in labels[0].get("class", []):
            campo = labels[0].get_text(strip=True).rstrip(":")
            key = FIELD_MAP.get(campo)
            if key:
                datos[key] = labels[1].get_text(strip=True)
    return datos or None


def _normalizar(datos: dict[str, str], placa_consultada: str) -> dict:
    modelo = datos.get("modelo")
    return {
        "placa": datos.get("placa", placa_consultada),
        "niv": datos.get("niv"),
        "marca": datos.get("marca"),
        "linea": datos.get("linea"),
        "modelo": int(modelo) if modelo and modelo.isdigit() else None,
        "tipo_vehiculo": datos.get("tipo_vehiculo"),
        "estatus": datos.get("estatus"),
        "version": datos.get("version"),
        "motor": datos.get("motor"),
    }


async def consultar_placa(placa: str) -> SioxConsultaResultado:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{settings.siox_base_url}/busquedaVehiculo.htm",
                data={"placa": placa, "serie": ""},
            )
            response.raise_for_status()
    except httpx.HTTPError:
        return SioxConsultaResultado(status="ERROR", raw=None, normalized=None)

    datos = _parse_respuesta(response.text)
    if datos is None:
        return SioxConsultaResultado(
            status="SIN_DATOS", raw={"html": response.text}, normalized=None
        )

    return SioxConsultaResultado(
        status="EXITOSA",
        raw={"html": response.text},
        normalized=_normalizar(datos, placa),
    )
