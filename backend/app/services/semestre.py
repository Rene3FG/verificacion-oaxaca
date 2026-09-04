"""Sección 5 del handoff: "prórroga global del 1er periodo". Ver
`app.services.proyeccion_certificado.calcular_semestre` para la regla
base de semestre por fecha, que este módulo alimenta con la prórroga
vigente sin acoplar esa función pura a una consulta de base de datos."""

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prorroga_semestre import ProrrogaSemestre


async def obtener_prorroga_activa(db: AsyncSession) -> ProrrogaSemestre | None:
    """La prórroga vigente es la fila más reciente (`orden`, no
    `created_at` — ver docstring de `ProrrogaSemestre`) cuya `fecha_final`
    no ha pasado. Configurar una prórroga nueva con `fecha_final` en el
    pasado es la forma de desactivar la anterior antes de tiempo — no hay
    una columna `activa` separada que se pueda desincronizar de la
    fecha."""

    fila = (
        await db.execute(select(ProrrogaSemestre).order_by(ProrrogaSemestre.orden.desc()))
    ).scalars().first()
    if fila is None:
        return None
    hoy = datetime.datetime.now(datetime.timezone.utc).date()
    return fila if fila.fecha_final >= hoy else None
