"""HU-061/HU-062: determinación del tipo de certificado y generación del
documento con WeasyPrint.

El documento de diseño del proyecto que definiría estas reglas y el
contenido exacto del certificado no está en este repo (referenciado desde
`app/seed.py` pero nunca incluido). Las reglas de abajo son una propuesta
razonable a partir de lo que el modelo de datos ya distingue
(resultado_final / InspeccionVisual.resultado) — a confirmar o corregir
contra el diseño real cuando esté disponible."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from weasyprint import HTML

from app.models.enums import ResultadoFinal, ResultadoInspeccionVisual
from app.models.inspeccion_visual import InspeccionVisual
from app.models.vehiculo import Vehiculo
from app.models.verificacion import Verificacion

CERTIFICADO_APROBACION = "APROBACION"
CERTIFICADO_RECHAZO_VISUAL = "RECHAZO_VISUAL"
CERTIFICADO_RECHAZO_PRUEBA = "RECHAZO_PRUEBA"


class TipoCertificadoIndeterminado(Exception):
    pass


async def determinar_tipo_certificado(db: AsyncSession, verificacion: Verificacion) -> str:
    """Regla propuesta: resultado_final manda si existe (viene de Prueba);
    si es None, el expediente solo pudo llegar a Impresión por la vía de
    rechazo en Inspección Visual (regla de negocio #3, salta Prueba)."""

    if verificacion.resultado_final == ResultadoFinal.APROBADO:
        return CERTIFICADO_APROBACION
    if verificacion.resultado_final == ResultadoFinal.RECHAZADO:
        return CERTIFICADO_RECHAZO_PRUEBA

    inspeccion = (
        await db.execute(
            select(InspeccionVisual)
            .where(InspeccionVisual.verificacion_id == verificacion.id)
            .order_by(InspeccionVisual.created_at.desc())
        )
    ).scalars().first()
    if inspeccion is not None and inspeccion.resultado == ResultadoInspeccionVisual.RECHAZADA:
        return CERTIFICADO_RECHAZO_VISUAL

    raise TipoCertificadoIndeterminado(
        f"No se pudo determinar el tipo de certificado para el expediente {verificacion.id}"
    )


def generar_pdf_certificado(
    verificacion: Verificacion, vehiculo: Vehiculo, tipo_certificado: str
) -> bytes:
    """Contenido mínimo de trazabilidad — no es el layout final del
    certificado oficial (eso también depende del documento de diseño)."""

    html = f"""
    <html>
      <head><meta charset="utf-8" /></head>
      <body style="font-family: sans-serif;">
        <h1>Certificado de Verificación Vehicular</h1>
        <p><strong>Tipo:</strong> {tipo_certificado}</p>
        <p><strong>Folio:</strong> {verificacion.folio_externo or "—"}</p>
        <p><strong>Expediente:</strong> {verificacion.id}</p>
        <p><strong>Placa:</strong> {verificacion.placa}</p>
        <p><strong>Marca / línea:</strong> {vehiculo.marca or "—"} {vehiculo.linea or ""}</p>
        <p><strong>Modelo:</strong> {vehiculo.modelo or "—"}</p>
        <p><strong>Combustible:</strong> {verificacion.combustible_validado or "—"}</p>
        <p><strong>Resultado final:</strong> {verificacion.resultado_final or "—"}</p>
      </body>
    </html>
    """
    return HTML(string=html).write_pdf()
