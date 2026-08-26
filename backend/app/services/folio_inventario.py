"""Inventario local de folios (revisión Figma 2026-08-24, regla crítica #6:
'Los folios se administran en este sistema ... El backend mantiene el
inventario, asigna el siguiente folio disponible de forma secuencial y
atómica'). Reemplaza `app.services.folios_client`, que simulaba una llamada
a un sistema externo inexistente."""

import datetime
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EstadoFolio, TipoCertificado
from app.models.folio import Folio, FolioLote

_RANGO_PATTERN = re.compile(r"^(?P<prefijo>.*?)(?P<numero>\d+)$")


class RangoDeFolioInvalido(Exception):
    pass


class SinFolioDisponible(Exception):
    def __init__(self, tipo_certificado: TipoCertificado):
        self.tipo_certificado = tipo_certificado
        super().__init__(
            f"Sin folio disponible para el tipo {tipo_certificado.value}. "
            "La lista local de ese tipo se agotó — registre un nuevo lote."
        )


def generar_folios_de_rango(folio_inicio: str, folio_fin: str) -> list[str]:
    """`folio_inicio`/`folio_fin` deben compartir el mismo prefijo y
    terminar en un número (p.ej. 'OAX-000123' .. 'OAX-000450'); genera la
    lista completa e inclusiva, conservando el ancho del cero a la
    izquierda del folio inicial."""

    m_ini = _RANGO_PATTERN.match(folio_inicio)
    m_fin = _RANGO_PATTERN.match(folio_fin)
    if not m_ini or not m_fin:
        raise RangoDeFolioInvalido(
            "folio_inicio y folio_fin deben terminar en un número, p.ej. 'OAX-000123'."
        )
    if m_ini.group("prefijo") != m_fin.group("prefijo"):
        raise RangoDeFolioInvalido("folio_inicio y folio_fin deben compartir el mismo prefijo.")

    ancho = len(m_ini.group("numero"))
    n_ini = int(m_ini.group("numero"))
    n_fin = int(m_fin.group("numero"))
    if n_fin < n_ini:
        raise RangoDeFolioInvalido("folio_fin debe ser mayor o igual que folio_inicio.")

    prefijo = m_ini.group("prefijo")
    return [f"{prefijo}{str(n).zfill(ancho)}" for n in range(n_ini, n_fin + 1)]


async def registrar_lote(
    db: AsyncSession,
    *,
    tipo_certificado: TipoCertificado,
    folio_inicio: str,
    folio_fin: str,
    registrado_por: uuid.UUID,
) -> tuple[FolioLote, list[str]]:
    folios_str = generar_folios_de_rango(folio_inicio, folio_fin)

    existentes = (
        await db.execute(select(Folio.folio).where(Folio.folio.in_(folios_str)))
    ).scalars().all()
    if existentes:
        raise RangoDeFolioInvalido(
            f"Ya existen {len(existentes)} folio(s) registrados en ese rango "
            f"(ej. {existentes[0]})."
        )

    lote = FolioLote(
        tipo_certificado=tipo_certificado,
        folio_inicio=folio_inicio,
        folio_fin=folio_fin,
        cantidad=len(folios_str),
        registrado_por=registrado_por,
    )
    db.add(lote)
    await db.flush()

    for folio_str in folios_str:
        db.add(Folio(lote_id=lote.id, tipo_certificado=tipo_certificado, folio=folio_str))

    return lote, folios_str


async def asignar_siguiente_folio(
    db: AsyncSession, tipo_certificado: TipoCertificado, verificacion_id: uuid.UUID
) -> Folio:
    """Toma el folio DISPONIBLE de menor `orden` para el tipo pedido, con
    `FOR UPDATE SKIP LOCKED`: bajo dos asignaciones concurrentes del mismo
    tipo, cada una toma un folio distinto en vez de bloquearse o repetirlo."""

    folio = (
        await db.execute(
            select(Folio)
            .where(Folio.tipo_certificado == tipo_certificado, Folio.estatus == EstadoFolio.DISPONIBLE)
            .order_by(Folio.orden.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()

    if folio is None:
        raise SinFolioDisponible(tipo_certificado)

    folio.estatus = EstadoFolio.ASIGNADO
    folio.verificacion_id = verificacion_id
    folio.asignado_at = datetime.datetime.now(datetime.timezone.utc)
    db.add(folio)
    return folio
