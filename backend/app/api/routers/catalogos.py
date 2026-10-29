"""Catálogos de solo lectura que las vistas de captura necesitan para que
los nombres coincidan con los que el certificado convierte a clave (ver
`app.services.catalogo_inegi`) y para elegir la carrocería de la Tabla 1
de potencia (ver `app.services.potencia_dinamometro`)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import SessionContext, get_current_session
from app.services.catalogo_inegi import CLAVE_OAXACA, ENTIDADES, clave_entidad, municipios
from app.services.potencia_dinamometro import CLASIFICACIONES_CARROCERIA

router = APIRouter(prefix="/api/catalogos", tags=["catalogos"])


@router.get("/entidades")
async def listar_entidades(session: SessionContext = Depends(get_current_session)) -> list[dict]:
    return [{"clave": clave, "nombre": nombre} for clave, nombre in ENTIDADES.items()]


@router.get("/municipios")
async def listar_municipios(
    entidad: str | None = None, session: SessionContext = Depends(get_current_session)
) -> list[dict]:
    """Municipios de una entidad (clave INEGI de 3 dígitos + nombre oficial).
    `entidad` acepta clave ('21') o nombre ('Puebla'); sin ella, Oaxaca."""

    clave_ent = clave_entidad(entidad) if entidad else CLAVE_OAXACA
    if clave_ent is None:
        raise HTTPException(status_code=422, detail=f"Entidad no reconocida: {entidad}")
    return municipios(clave_ent)


@router.get("/carrocerias")
async def listar_carrocerias(session: SessionContext = Depends(get_current_session)) -> list[dict]:
    return [
        {"clave": clave, "nombre": nombre} for clave, nombre in CLASIFICACIONES_CARROCERIA.items()
    ]
