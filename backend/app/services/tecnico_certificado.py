"""Campo 001 del certificado = identificador del técnico (NOM-047 punto 5).

Definición del cliente (Don Rubén, 2026-11-06): en un certificado
aprobatorio va el técnico que hizo la prueba de emisiones; en uno de
rechazo, el técnico que emitió el rechazo (fin de la prueba de emisiones o
inspección visual). Se imprime su `clave_tecnico` si la tiene y, si no, su
nombre de usuario. Se resuelve al generar la proyección (que se congela en
el primer clic de Imprimir), así una reimpresión conserva al mismo técnico
aunque después se cambie la clave del usuario.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inspeccion_visual import InspeccionVisual
from app.models.resultado_prueba import ResultadoPrueba
from app.models.usuario import CatUsuario
from app.models.verificacion import Verificacion


async def resolver_tecnico(
    db: AsyncSession,
    verificacion: Verificacion,
    resultado_prueba: ResultadoPrueba | None,
) -> str | None:
    """`None` si el expediente no registra quién hizo la prueba o la
    inspección (datos anteriores a que se guardara `operador_id`); el PDF
    cae entonces al parámetro fijo `certificado_numero_equipo`."""

    operador_id = resultado_prueba.operador_id if resultado_prueba is not None else None
    if operador_id is None and resultado_prueba is None:
        operador_id = (
            await db.execute(
                select(InspeccionVisual.operador_id)
                .where(InspeccionVisual.verificacion_id == verificacion.id)
                .order_by(InspeccionVisual.created_at.desc())
            )
        ).scalars().first()
    if operador_id is None:
        return None
    usuario = await db.get(CatUsuario, operador_id)
    if usuario is None:
        return None
    return usuario.clave_tecnico or usuario.username
