"""Catálogos de solo lectura que las vistas de captura necesitan para que
los nombres coincidan con los que el certificado convierte a clave (ver
`app.services.catalogo_inegi`) y para elegir la carrocería de la Tabla 1
de potencia (ver `app.services.potencia_dinamometro`)."""

from fastapi import APIRouter, Depends

from app.api.deps import SessionContext, get_current_session
from app.services.catalogo_inegi import ENTIDADES, municipios_oaxaca
from app.services.potencia_dinamometro import CLASIFICACIONES_CARROCERIA

router = APIRouter(prefix="/api/catalogos", tags=["catalogos"])


@router.get("/entidades")
async def listar_entidades(session: SessionContext = Depends(get_current_session)) -> list[dict]:
    return [{"clave": clave, "nombre": nombre} for clave, nombre in ENTIDADES.items()]


@router.get("/municipios")
async def listar_municipios(session: SessionContext = Depends(get_current_session)) -> list[dict]:
    """Municipios de Oaxaca (clave INEGI de 3 dígitos + nombre oficial)."""

    return municipios_oaxaca()


@router.get("/carrocerias")
async def listar_carrocerias(session: SessionContext = Depends(get_current_session)) -> list[dict]:
    return [
        {"clave": clave, "nombre": nombre} for clave, nombre in CLASIFICACIONES_CARROCERIA.items()
    ]
