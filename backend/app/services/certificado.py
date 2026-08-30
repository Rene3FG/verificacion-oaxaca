"""HU-061/HU-062: determinación del tipo de certificado y generación del
documento con WeasyPrint.

Regla vigente ('Developer Handoff — Approved Certificate Printing Rules',
confirmada en la revisión del Figma 2026-08-24): un resultado RECHAZADO
(por prueba o por inspección visual) es la única parte que se infiere sola
— un solo tipo posible, RECHAZO. Un resultado APROBADO no tiene regla de
elegibilidad automática entre Particular/Doble Cero/Intensivo todavía; la
selección correcta queda bajo responsabilidad del Operador de Impresión."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from weasyprint import HTML

from app.models.enums import ResultadoFinal, ResultadoInspeccionVisual, TipoCertificado
from app.models.inspeccion_visual import InspeccionVisual
from app.models.vehiculo import Vehiculo
from app.models.verificacion import Verificacion


class TipoCertificadoIndeterminado(Exception):
    pass


class TipoCertificadoRequiereSeleccionManual(Exception):
    pass


# Sección 7 del handoff (revisión Figma 2026-08-24): campos de propietario/
# domicilio y del vehículo que el certificado exige. Opcionales al capturar
# (ver app.models.vehiculo), obligatorios solo al momento de imprimir —
# `campos_obligatorios_faltantes` es lo que hace cumplir eso.
CAMPOS_OBLIGATORIOS_CERTIFICADO = {
    "tarjeta_circulacion": "Número de tarjeta de circulación",
    "propietario_estado": "Estado",
    "propietario_municipio": "Municipio",
    "propietario_codigo_postal": "Código postal",
    "propietario_colonia": "Colonia",
    "propietario_calle": "Calle",
    "propietario_numero_exterior": "Número exterior",
    "pbv": "Peso bruto vehicular (PBV)",
    "traccion": "Tracción",
}


def campos_obligatorios_faltantes(vehiculo: Vehiculo) -> list[str]:
    """Nombres legibles (no de columna) de los campos obligatorios del
    certificado que el vehículo todavía no tiene capturados."""

    return [
        etiqueta
        for campo, etiqueta in CAMPOS_OBLIGATORIOS_CERTIFICADO.items()
        if not getattr(vehiculo, campo)
    ]


async def determinar_tipo_certificado(
    db: AsyncSession,
    verificacion: Verificacion,
    tipo_certificado_manual: TipoCertificado | None = None,
) -> TipoCertificado:
    if verificacion.resultado_final == ResultadoFinal.RECHAZADO:
        return TipoCertificado.RECHAZO

    inspeccion = (
        await db.execute(
            select(InspeccionVisual)
            .where(InspeccionVisual.verificacion_id == verificacion.id)
            .order_by(InspeccionVisual.created_at.desc())
        )
    ).scalars().first()
    if inspeccion is not None and inspeccion.resultado == ResultadoInspeccionVisual.RECHAZADA:
        return TipoCertificado.RECHAZO

    if verificacion.resultado_final == ResultadoFinal.APROBADO:
        if tipo_certificado_manual is None:
            raise TipoCertificadoRequiereSeleccionManual(
                "Resultado aprobado: seleccione manualmente Particular, Doble Cero o Intensivo."
            )
        if tipo_certificado_manual == TipoCertificado.RECHAZO:
            raise TipoCertificadoRequiereSeleccionManual(
                "No se puede asignar el tipo RECHAZO a un expediente aprobado."
            )
        return tipo_certificado_manual

    raise TipoCertificadoIndeterminado(
        f"No se pudo determinar el tipo de certificado para el expediente {verificacion.id}"
    )


def generar_pdf_certificado(
    verificacion: Verificacion, vehiculo: Vehiculo, tipo_certificado: str
) -> bytes:
    """Contenido mínimo de trazabilidad — no es el layout final del
    certificado oficial ('Certificate Result Projection Contract v1' en el
    Figma define el contrato completo de sobreimpresión, pendiente de
    implementar)."""

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
