from fastapi import FastAPI

from app.api.routers import (
    estaciones,
    expedientes,
    folios,
    impresion,
    inspeccion,
    obd,
    pruebas,
    siox,
)

app = FastAPI(title="Sistema de Verificación Vehicular de Oaxaca")

app.include_router(expedientes.router)
app.include_router(siox.router)
app.include_router(inspeccion.router)
app.include_router(obd.router)
app.include_router(pruebas.router)
app.include_router(impresion.router)
app.include_router(folios.router)
app.include_router(estaciones.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
