"""HU-066/HU-071: el sistema externo de folios no tiene integración real
definida todavía (ver 'Qué sucede con los folios' en el proyecto), así que
`FoliosExternoClient` es un doble configurable, mismo espíritu que
`app.services.siox_client`/`impresora`. A diferencia de esos, el modo no se
monkeypatchea sobre una función de módulo: se inyecta vía
`Depends(get_folios_client)`, y las pruebas lo seleccionan sobrescribiendo
`app.dependency_overrides[get_folios_client]` (limpiado automáticamente al
final de cada prueba por el fixture `client`, ver conftest.py) — así dos
pruebas nunca pueden pisarse el modo entre sí como pasaría con una
variable global compartida.
"""

import enum
import re
import uuid

_FOLIO_PATTERN = re.compile(r"^[A-Z0-9]{1,10}-[A-Z0-9]{1,20}$")


class ModoFolioExterno(str, enum.Enum):
    EXITO = "exito"
    ERROR = "error"
    TIMEOUT = "timeout"
    FOLIO_DUPLICADO = "folio_duplicado"
    FOLIO_INVALIDO = "folio_invalido"


class TimeoutFolioExterno(Exception):
    """El sistema externo de folios no respondió a tiempo."""


class FoliosExternoClient:
    def __init__(self, modo: ModoFolioExterno = ModoFolioExterno.ERROR):
        self.modo = modo

    async def consultar(self, payload: dict) -> dict:
        if self.modo is ModoFolioExterno.TIMEOUT:
            raise TimeoutFolioExterno(
                "El sistema externo de folios no respondió a tiempo"
            )
        if self.modo is ModoFolioExterno.ERROR:
            return {"folio": None, "external_reference_id": None, "status": "error"}
        if self.modo is ModoFolioExterno.FOLIO_DUPLICADO:
            return {
                "folio": None,
                "external_reference_id": None,
                "status": "duplicado",
            }
        if self.modo is ModoFolioExterno.FOLIO_INVALIDO:
            # El sistema externo dice "asignado" pero con un folio que no
            # cumple el formato esperado — caso real de integraciones así,
            # no solo un error de transporte.
            return {
                "folio": "???",
                "external_reference_id": str(uuid.uuid4()),
                "status": "asignado",
            }
        return {
            "folio": f"OAX-{uuid.uuid4().hex[:10].upper()}",
            "external_reference_id": str(uuid.uuid4()),
            "status": "asignado",
        }


def get_folios_client() -> FoliosExternoClient:
    """Default de producción: ERROR — no hay sistema externo real todavía,
    mismo comportamiento observable que el stub anterior. Las pruebas
    sobrescriben esta dependencia para elegir cualquier otro modo."""
    return FoliosExternoClient()


def folio_tiene_formato_valido(folio: str | None) -> bool:
    return bool(folio) and bool(_FOLIO_PATTERN.match(folio))


def mensaje_error_folio(respuesta: dict) -> str:
    status = respuesta.get("status")
    if status == "timeout":
        return "El sistema externo de folios no respondió a tiempo"
    if status == "duplicado":
        return "El sistema externo reporta folio duplicado para este tipo de certificado"
    if status == "asignado":
        return f"Folio recibido con formato inválido: {respuesta.get('folio')!r}"
    return "El sistema externo de folios no respondió"
