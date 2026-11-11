import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import (
    catalogos,
    equipos,
    estaciones,
    expedientes,
    folios,
    impresion,
    inspeccion,
    obd,
    parametros,
    permisos,
    pruebas,
    siox,
    supervision,
    sync,
    usuarios,
)

from app.core.config import settings
from app.services.sesiones_barrido import barrido_habilitado, bucle_barrido_sesiones
from app.services.sync_auto import bucle_sync_auto, sync_auto_habilitado


@asynccontextmanager
async def lifespan(_: FastAPI):
    tarea = asyncio.create_task(bucle_sync_auto()) if sync_auto_habilitado() else None
    barrido = asyncio.create_task(bucle_barrido_sesiones()) if barrido_habilitado() else None
    try:
        yield
    finally:
        for t in (tarea, barrido):
            if t:
                t.cancel()


# X4-d: en producción no se publica el mapa de la API.
_docs = {} if not settings.es_produccion else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title="Sistema de Verificación Vehicular de Oaxaca", lifespan=lifespan, **_docs)

app.include_router(expedientes.router)
app.include_router(siox.router)
app.include_router(inspeccion.router)
app.include_router(obd.router)
app.include_router(pruebas.router)
app.include_router(impresion.router)
app.include_router(folios.router)
app.include_router(estaciones.router)
app.include_router(permisos.router)
app.include_router(supervision.router)
app.include_router(sync.router)
app.include_router(usuarios.router)
app.include_router(parametros.router)
app.include_router(catalogos.router)
app.include_router(equipos.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
