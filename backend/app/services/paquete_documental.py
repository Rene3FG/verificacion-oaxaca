"""HU-072/HU-074 (Sheet, Etapa 9): paquete documental = certificado +
resultados complementarios (inspección visual, OBD/SBD si aplica, resultado
de la prueba con límites aplicados).

El certificado se sobreimprime sobre papel preimpreso (ver
`app.services.certificado`); los resultados complementarios son un documento
aparte en hoja blanca, por eso se generan por separado y solo se juntan en la
vista previa. Todo se lee de las filas inmutables del expediente — nunca de
datos que capture el operador de Impresión (HU-063)."""

import datetime
import html as _html

from weasyprint import HTML

from app.models.inspeccion_visual import InspeccionVisual
from app.models.resultado_obd_sbd import ResultadoObdSbd
from app.models.resultado_prueba import ResultadoPrueba
from app.models.vehiculo import Vehiculo
from app.models.verificacion import Verificacion
from app.services.inspeccion_visual import CHECKLIST_INSPECCION_VISUAL
from app.services.semestre import ZONA_OAXACA

_TEXTO_ITEM = {"BUENO": "Bueno", "MALO": "Malo", "NO_APLICA": "No aplica"}
_ETIQUETA_PARAMETRO = {
    "hc_ppm": "HC (ppm)",
    "co_pct": "CO (%)",
    "co2_pct": "CO2 (%)",
    "o2_pct": "O2 (%)",
    "nox_ppm": "NOx (ppm)",
    "lambda_factor": "Factor Lambda",
    "speed_kph": "Velocidad (km/h)",
    "coefficient_absorption_final_k_m1": "Coeficiente de absorción K (m-1)",
    "opacity_pct": "Opacidad (%)",
    "engine_temp_c": "Temperatura de motor (°C)",
    "rpm_idle": "RPM ralentí",
    "rpm_governed_max": "RPM gobernado máx.",
    "rpm_peak": "RPM pico",
}


def _e(valor) -> str:
    return "—" if valor is None or valor == "" else _html.escape(str(valor))


def _fecha(momento: datetime.datetime | None) -> str:
    if momento is None:
        return "—"
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=datetime.timezone.utc)
    return momento.astimezone(ZONA_OAXACA).strftime("%d/%m/%Y %H:%M")


def _valor_enum(valor) -> str:
    return getattr(valor, "value", valor) or "—"


def _seccion_inspeccion(inspeccion: InspeccionVisual | None) -> str:
    if inspeccion is None:
        return "<h2>Inspección visual</h2><p>Sin registro.</p>"
    filas = "".join(
        f"<tr><td>{_e(etiqueta)}</td><td>{_e(_TEXTO_ITEM.get((inspeccion.checklist_json or {}).get(clave), (inspeccion.checklist_json or {}).get(clave)))}</td></tr>"
        for clave, etiqueta in CHECKLIST_INSPECCION_VISUAL.items()
    )
    observaciones = (inspeccion.causales_rechazo or {}).get("observaciones")
    return f"""
    <h2>Inspección visual — {_e(_valor_enum(inspeccion.resultado))}</h2>
    <table><tr><th>Punto</th><th>Resultado</th></tr>{filas}</table>
    {f"<p><strong>Observaciones:</strong> {_e(observaciones)}</p>" if observaciones else ""}
    """


def _seccion_obd(obd: ResultadoObdSbd | None) -> str:
    if obd is None:
        return ""
    if not obd.aplica:
        return "<h2>OBD/SBD</h2><p>No aplica para este vehículo.</p>"
    codigos = obd.codigos_error or {}
    raw = obd.datos_raw or {}
    if raw.get("sin_comunicacion"):
        return f"""
    <h2>OBD/SBD — Sin comunicación</h2>
    <p>Solicitado: {_fecha(obd.solicitado_at)} · Intento registrado: {_fecha(obd.recibido_at)}</p>
    <p>Mensaje técnico: {_e(raw.get("mensaje_tecnico"))}</p>
    """
    return f"""
    <h2>OBD/SBD — {_e(_valor_enum(obd.resultado))}</h2>
    <p>Solicitado: {_fecha(obd.solicitado_at)} · Recibido: {_fecha(obd.recibido_at)}</p>
    {f"<p><strong>Códigos:</strong> {_e(codigos)}</p>" if codigos else ""}
    """


def _tabla_lecturas(lecturas: dict, limites: dict) -> str:
    filas = "".join(
        f"<tr><td>{_e(_ETIQUETA_PARAMETRO.get(p, p))}</td><td>{_e(v)}</td><td>{_e(limites.get(p))}</td></tr>"
        for p, v in lecturas.items()
        if not isinstance(v, (dict, list))
    )
    return f"<table><tr><th>Parámetro</th><th>Lectura</th><th>Límite</th></tr>{filas}</table>"


def _seccion_prueba(resultado: ResultadoPrueba | None) -> str:
    if resultado is None:
        return ""
    valores = resultado.valores_medidos_json or {}
    limites = resultado.limites_aplicados_json or {}
    cuerpo = ""
    if "ralenti" in valores or "crucero" in valores:
        for fase, titulo in (("ralenti", "Ralentí"), ("crucero", "Crucero")):
            if isinstance(valores.get(fase), dict):
                lim = limites.get(fase) if isinstance(limites.get(fase), dict) else {}
                cuerpo += f"<h3>{titulo}</h3>{_tabla_lecturas(valores[fase], lim)}"
    else:
        cuerpo = _tabla_lecturas(valores, limites)
    return f"""
    <h2>Prueba de emisiones — {_e(_valor_enum(resultado.resultado))}</h2>
    <p>Tipo: {_e(_valor_enum(resultado.tipo_prueba))} · Combustible: {_e(resultado.combustible)}
       · Inicio: {_fecha(resultado.started_at)} · Fin: {_fecha(resultado.finished_at)}</p>
    {cuerpo}
    <p class="hash">Integridad: {_e(resultado.hash_integridad)}</p>
    """


def html_resultados(
    verificacion: Verificacion,
    vehiculo: Vehiculo,
    *,
    inspeccion: InspeccionVisual | None,
    obd: ResultadoObdSbd | None,
    resultado_prueba: ResultadoPrueba | None,
) -> str:
    return f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          @page {{ size: A4; margin: 18mm; }}
          body {{ font-family: Arial, "Liberation Sans", sans-serif; font-size: 9.5pt; }}
          h1 {{ font-size: 14pt; margin: 0 0 4pt; }}
          h2 {{ font-size: 11pt; margin: 14pt 0 4pt; border-bottom: 1px solid #999; }}
          h3 {{ font-size: 10pt; margin: 8pt 0 2pt; }}
          table {{ border-collapse: collapse; width: 100%; }}
          th, td {{ text-align: left; padding: 2pt 6pt; border-bottom: 1px solid #ddd; }}
          .hash {{ font-size: 7pt; color: #666; }}
        </style>
      </head>
      <body>
        <h1>Resultados de la verificación vehicular</h1>
        <p>Placa: <strong>{_e(verificacion.placa)}</strong> · {_e(vehiculo.marca)} {_e(vehiculo.linea)}
           {_e(vehiculo.modelo)} · NIV: {_e(vehiculo.niv)}<br />
           Centro: {_e(verificacion.centro_id)} · Línea: {_e(verificacion.linea_id)}
           · Expediente: {_e(verificacion.id)}</p>
        {_seccion_inspeccion(inspeccion)}
        {_seccion_obd(obd)}
        {_seccion_prueba(resultado_prueba)}
      </body>
    </html>
    """


def pdf_de_html(html: str) -> bytes:
    return HTML(string=html).write_pdf()


def pdf_paquete(*htmls: str) -> bytes:
    """Une varios documentos (cada uno con su propio @page) en un solo PDF
    — el certificado sin márgenes y los resultados con márgenes normales."""

    documentos = [HTML(string=h).render() for h in htmls]
    paginas = [pagina for doc in documentos for pagina in doc.pages]
    return documentos[0].copy(paginas).write_pdf()
