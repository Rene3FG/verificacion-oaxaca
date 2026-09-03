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


_ETIQUETAS_METODO = {
    "GAS_STATIC": "Método estático (gasolina)",
    "GAS_DYNAMIC": "Método dinámico (gasolina)",
    "DIESEL_OPACITY": "Opacidad (diésel)",
}


def _fila_fase_gasolina(etiqueta: str, fase: dict | None) -> str:
    fase = fase or {}

    def valor(campo: str, sufijo: str = "") -> str:
        v = fase.get(campo)
        return f"{v}{sufijo}" if v is not None else "—"

    return f"""
      <tr>
        <td style="padding: 4px 8px;">{etiqueta}</td>
        <td style="padding: 4px 8px;">{valor("hc_ppm", " ppm")}</td>
        <td style="padding: 4px 8px;">{valor("co_pct", " %")}</td>
        <td style="padding: 4px 8px;">{valor("co2_pct", " %")}</td>
        <td style="padding: 4px 8px;">{valor("co_co2_pct", " %")}</td>
        <td style="padding: 4px 8px;">{valor("o2_pct", " %")}</td>
        <td style="padding: 4px 8px;">{valor("nox_ppm", " ppm")}</td>
        <td style="padding: 4px 8px;">{valor("speed_kph", " km/h")}</td>
      </tr>
    """


def _bloque_mediciones_html(proyeccion: dict) -> str:
    """Sección 4, bloques 02 (gasolina RALENTÍ/CRUCERO)/04 (diésel): el
    único bloque de mediciones que se sobreimprime en el certificado, leído
    exclusivamente de `proyeccion["fields"]` — nunca de
    `ResultadoPrueba.valores_medidos_json` directo, ese es el punto del
    contrato (fuente única, snapshot congelado). Vacío cuando el expediente
    nunca pasó por Prueba (rechazo por inspección visual) o el método no
    tiene mapping aprobado — `generar_proyeccion_certificado` ya deja
    `method`/`fields` vacíos en esos casos, no hay nada que renderizar."""

    metodo = proyeccion.get("method")
    fields = proyeccion.get("fields") or {}
    if not metodo or not fields:
        return ""

    if metodo == "DIESEL_OPACITY":
        k = fields.get("coefficient_absorption_final_k_m1")
        valor = f"{k}" if k is not None else "—"
        return f"""
        <table style="border-collapse: collapse; width: 100%; margin-top: 12px;">
          <tr><th colspan="2" style="text-align:left; border-bottom: 1px solid #999;">Opacidad</th></tr>
          <tr>
            <td style="padding: 4px 8px;">Coeficiente de absorción final K (m&#8315;&#185;)</td>
            <td style="padding: 4px 8px;"><strong>{valor}</strong></td>
          </tr>
        </table>
        """

    return f"""
    <table style="border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 0.9em;">
      <tr>
        <th style="text-align:left; border-bottom: 1px solid #999;">Fase</th>
        <th style="text-align:left; border-bottom: 1px solid #999;">HC</th>
        <th style="text-align:left; border-bottom: 1px solid #999;">CO</th>
        <th style="text-align:left; border-bottom: 1px solid #999;">CO2</th>
        <th style="text-align:left; border-bottom: 1px solid #999;">CO+CO2</th>
        <th style="text-align:left; border-bottom: 1px solid #999;">O2</th>
        <th style="text-align:left; border-bottom: 1px solid #999;">NOx</th>
        <th style="text-align:left; border-bottom: 1px solid #999;">Vel.</th>
      </tr>
      {_fila_fase_gasolina("Ralentí", fields.get("ralenti"))}
      {_fila_fase_gasolina("Crucero", fields.get("crucero"))}
    </table>
    """


def generar_pdf_certificado(
    verificacion: Verificacion, vehiculo: Vehiculo, proyeccion: dict
) -> bytes:
    """'Certificate Result Projection Contract v1' (sección 4): sobreimprime
    EXCLUSIVAMENTE desde `proyeccion` — el snapshot congelado en
    `print_jobs.certificate_projection_json` para la impresión definitiva
    (`_imprimir_y_registrar`), o su equivalente generado al vuelo sin
    persistir para la vista previa (`vista_previa_certificado`, "no es la
    impresión definitiva"). El resto de los datos del expediente (placa,
    NIV, marca, modelo) no forma parte del contrato de proyección — se
    sigue leyendo del expediente/vehículo directo, igual que antes."""

    tipo_certificado = proyeccion.get("certificate_type") or "—"
    resultado = proyeccion.get("evaluation_result") or verificacion.resultado_final or "—"
    semestre = proyeccion.get("semestre")
    metodo_etiqueta = _ETIQUETAS_METODO.get(proyeccion.get("method"), "—")
    bloque_mediciones = _bloque_mediciones_html(proyeccion)

    html = f"""
    <html>
      <head><meta charset="utf-8" /></head>
      <body style="font-family: sans-serif;">
        <h1>Certificado de Verificación Vehicular</h1>
        <p><strong>Tipo:</strong> {tipo_certificado}</p>
        <p><strong>Folio:</strong> {verificacion.folio_externo or "—"}</p>
        <p><strong>Semestre:</strong> {semestre or "—"}</p>
        <p><strong>Expediente:</strong> {verificacion.id}</p>
        <p><strong>Placa:</strong> {verificacion.placa}</p>
        <p><strong>Marca / línea:</strong> {vehiculo.marca or "—"} {vehiculo.linea or ""}</p>
        <p><strong>Modelo:</strong> {vehiculo.modelo or "—"}</p>
        <p><strong>Combustible:</strong> {verificacion.combustible_validado or "—"}</p>
        <p><strong>Método de prueba:</strong> {metodo_etiqueta}</p>
        <p><strong>Resultado final:</strong> {resultado}</p>
        {bloque_mediciones}
      </body>
    </html>
    """
    return HTML(string=html).write_pdf()
