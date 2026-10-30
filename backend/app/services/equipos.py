"""F4 (HU-042/102): qué equipo físico midió cada resultado.

El servidor resuelve el equipo a partir de la estación de la sesión y del
método; el cliente ya no puede escribir un UUID arbitrario. Sin equipo
registrado en la estación el resultado queda con `equipo_id = NULL` (se
documenta el hueco, nunca se fabrica un equipo)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MetodoPrueba
from app.models.equipo import Equipo

TIPOS_EQUIPO = ("ANALIZADOR_GASES", "DINAMOMETRO", "OPACIMETRO", "ESCANER_OBD")

# El equipo que produce las lecturas que se guardan en el resultado: en
# dinámica el dinamómetro solo aplica carga, quien mide es el analizador.
TIPO_POR_METODO = {
    MetodoPrueba.GAS_STATIC: "ANALIZADOR_GASES",
    MetodoPrueba.GAS_DYNAMIC: "ANALIZADOR_GASES",
    MetodoPrueba.DIESEL_OPACITY: "OPACIMETRO",
}
TIPO_OBD = "ESCANER_OBD"


class EquipoInvalido(Exception):
    """El equipo pedido no existe, está inactivo o es de otra estación/tipo."""


async def resolver_equipo(
    db: AsyncSession,
    *,
    workstation_id: uuid.UUID,
    tipo: str | None,
    solicitado: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Con `solicitado`, valida que sea un equipo activo de esta estación y
    del tipo esperado (`EquipoInvalido` si no). Sin él, toma el único equipo
    activo de ese tipo en la estación; con cero o varios devuelve None (con
    varios no hay forma de saber cuál midió sin que el operador lo diga)."""

    if solicitado is not None:
        equipo = await db.get(Equipo, solicitado)
        if (
            equipo is None
            or not equipo.is_active
            or equipo.workstation_id != workstation_id
            or (tipo is not None and equipo.tipo != tipo)
        ):
            raise EquipoInvalido(
                "El equipo indicado no es un equipo activo de esta estación"
                + (f" de tipo {tipo}." if tipo else ".")
            )
        return equipo.id

    if tipo is None:
        return None
    ids = (
        await db.execute(
            select(Equipo.id).where(
                Equipo.workstation_id == workstation_id,
                Equipo.tipo == tipo,
                Equipo.is_active.is_(True),
            )
        )
    ).scalars().all()
    return ids[0] if len(ids) == 1 else None
