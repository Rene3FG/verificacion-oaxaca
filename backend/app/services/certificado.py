"""HU-061/HU-062: determinación del tipo de certificado y generación del
documento con WeasyPrint.

Regla vigente ('Developer Handoff — Approved Certificate Printing Rules',
confirmada en la revisión del Figma 2026-08-24): un resultado RECHAZADO
(por prueba o por inspección visual) es la única parte que se infiere sola
— un solo tipo posible, RECHAZO. Un resultado APROBADO no tiene regla de
elegibilidad automática entre Particular/Doble Cero/Intensivo todavía; la
selección correcta queda bajo responsabilidad del Operador de Impresión."""

import datetime
import html as _html

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from weasyprint import HTML

from app.models.enums import ResultadoFinal, ResultadoInspeccionVisual, TipoCertificado
from app.models.inspeccion_visual import InspeccionVisual
from app.models.resultado_prueba import ResultadoPrueba
from app.models.vehiculo import Vehiculo
from app.models.verificacion import Verificacion
from app.services.semestre import ZONA_OAXACA


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


# --- Sobreimpresión sobre papel preimpreso (plantillas del cliente, 2026-10-05) ---
#
# El cliente compartió las plantillas Word que usa hoy el sistema de
# verificación (`Particular.doc` para gasolina, `IntensivoDie.doc` para
# diésel). Son formatos de SOBREIMPRESIÓN: solo escriben los datos sobre el
# papel del certificado (que ya trae el diseño), repetidos 3 veces por hoja
# A4 (tres talones), y la 2ª copia lleva además la placa en grande aparte.
#
# Las coordenadas (puntos tipográficos, origen arriba-izquierda) se midieron
# del render de LibreOffice de esas plantillas — Word puede desplazar unos
# puntos, por eso existen `certificado_offset_x_mm`/`certificado_offset_y_mm`
# en `cat_parametros_sistema` para calibrar contra el papel real sin tocar
# código. Supuestos (reversibles, ver CLAUDE.md):
# - el layout depende del MÉTODO (diésel → Intensivo, todo lo demás →
#   Particular); el texto "PARTICULAR" fijo de la plantilla se reemplaza por
#   el tipo real (Particular/Doble Cero/Intensivo/Rechazo), porque no hay
#   plantilla propia de Doble Cero ni de Rechazo;
# - `<NombrePropietario> <ApellidoPatPro> <ApellidoMatPro>` ← `razon_social`
#   (no se captura el nombre separado), `<PoblacionPro>` ← colonia,
#   `<Serie1>` ← NIV, `<SubMarca>` ← línea del vehículo;
# - `<CertificadoAnt>`, `<Multa>`, `<TOTPOT5024>`/`<TOTPOT2540>` no se
#   capturan en el sistema → quedan en blanco;
# - `<FOLIO>` NO se imprime por defecto (regla del cliente 2026-10-01: el
#   folio viene preimpreso); `certificado_imprime_folio=true` lo activa.

_PT_POR_MM = 72 / 25.4

# anclaje: "l" = x es el borde izquierdo, "r" = borde derecho, "c" = centro.
# 5º valor opcional: ancho disponible (pt) antes del campo siguiente de la
# misma fila — un texto más largo se imprime con letra más chica en vez de
# encimarse (p. ej. "OAXACA DE JUAREZ" en el hueco de municipio).
_LAYOUT_PARTICULAR = {
    # (dx, dy del encabezado, dy del bloque inferior) por copia: en la
    # plantilla las 3 copias no son traslaciones exactas entre sí.
    "copias": ((0.0, 0.0, 0.0), (0.0, 238.4, 243.9), (-2.9, 501.5, 505.6)),
    "y_bloque_inferior": 190.0,
    "placa_grande": (500.0, 457.8),
    "campos": [
        ("nombre", "l", 16.1, 106.4, 230), ("tarjeta", "l", 250.0, 106.4, 95),
        ("placa", "l", 349.2, 106.4, 82), ("marca", "l", 435.5, 106.4, 140),
        ("calle", "l", 16.1, 130.3, 280), ("serie", "l", 300.1, 130.3, 125),
        ("submarca", "l", 429.4, 130.3, 85), ("tipo", "c", 545.8, 130.3),
        ("poblacion", "l", 16.1, 155.8, 222), ("cp", "l", 241.2, 155.3, 60),
        ("estado", "l", 304.5, 155.8, 100), ("municipio", "l", 408.3, 155.8, 58),
        ("modelo", "l", 468.3, 155.8, 42), ("semestre", "c", 545.5, 155.3),
        ("cvv_linea", "c", 104.5, 197.8), ("equipo_marca", "c", 93.0, 209.6),
        ("equipo_numero", "c", 93.0, 221.0), ("certificado_anterior", "c", 93.0, 232.1),
        ("multa", "c", 93.0, 243.9), ("fecha", "c", 93.0, 255.3),
        ("horas", "c", 93.0, 266.6), ("folio", "c", 93.0, 278.0),
    ],
    "etiquetas": [
        ("HC ppm", 189.5, 198.7), ("CO%", 189.5, 210.2), ("CO2%", 189.5, 221.5),
        ("CO+CO2%", 189.5, 233.0), ("O2", 189.5, 244.5), ("NOx ppm", 189.5, 255.8),
        ("Km/h", 189.5, 267.2),
    ],
    # (campo de la fase, y): RALENTÍ alineado a la derecha en x=293.6,
    # CRUCERO centrado en x=330.3 — igual que las columnas de la plantilla.
    "lecturas": [
        ("hc_ppm", 198.3), ("co_pct", 209.6), ("co2_pct", 221.0),
        ("co_co2_pct", 232.6), ("o2_pct", 243.9), ("nox_ppm", 255.3),
        ("speed_kph", 266.6), ("potencia", 278.0),
    ],
}

_LAYOUT_INTENSIVO = {
    "copias": ((0.0, 0.0, 0.0), (2.3, 258.4, 264.3), (2.3, 510.0, 514.3)),
    "y_bloque_inferior": 150.0,
    "placa_grande": (497.0, 428.0),
    "campos": [
        ("nombre", "l", 10.9, 61.0, 230), ("tarjeta", "l", 244.7, 61.0, 95),
        ("placa", "l", 344.0, 61.0, 82), ("marca", "l", 430.2, 61.0, 140),
        ("calle", "l", 10.9, 84.9, 280), ("serie", "l", 294.9, 84.9, 125),
        ("submarca", "l", 424.2, 84.9, 85), ("tipo", "c", 540.5, 84.9),
        ("poblacion", "l", 10.9, 110.4, 222), ("cp", "l", 236.0, 109.9, 60),
        ("estado", "l", 299.3, 110.4, 100), ("municipio", "l", 403.0, 110.4, 58),
        ("modelo", "l", 463.0, 110.4, 42), ("semestre", "c", 540.5, 109.9),
        ("cvv_linea", "c", 89.5, 152.6), ("equipo_marca", "c", 87.7, 164.0),
        ("equipo_numero", "c", 87.7, 175.3), ("certificado_anterior", "c", 87.7, 186.9),
        ("multa", "c", 87.7, 198.5), ("fecha", "c", 87.7, 210.1),
        ("horas", "c", 87.7, 221.5), ("folio", "c", 87.7, 232.6),
        ("coeficiente", "r", 288.5, 198.0),
    ],
    "etiquetas": [
        ("COEFICIENTE", 184.3, 186.4), ("DE", 184.3, 198.9), ("ABSORCION m-1", 184.3, 209.6),
    ],
    "lecturas": [],
}

_ETIQUETA_TIPO = {
    "PARTICULAR": "PARTICULAR",
    "DOBLE_CERO": "DOBLE CERO",
    "INTENSIVO": "INTENSIVO",
    "RECHAZO": "RECHAZO",
}

CONFIG_CERTIFICADO_DEFAULT = {
    "clave_centro": "CVV-06",
    "marca_equipo": "OBERTECH",
    "numero_equipo": "001",
    "imprime_folio": False,
    "offset_x_mm": 0.0,
    "offset_y_mm": 0.0,
}


async def cargar_config_certificado(db: AsyncSession) -> dict:
    """Lee de `cat_parametros_sistema` los datos fijos del centro que las
    plantillas traían escritos a mano (CVV-06, OBERTECH, 001) y la
    calibración de márgenes. Se resuelve aquí para que
    `generar_pdf_certificado` siga siendo pura (sin base de datos)."""

    from app.services.parametros import get_parametro

    return {
        "clave_centro": await get_parametro(db, "certificado_clave_centro"),
        "marca_equipo": await get_parametro(db, "certificado_marca_equipo"),
        "numero_equipo": await get_parametro(db, "certificado_numero_equipo"),
        "imprime_folio": (await get_parametro(db, "certificado_imprime_folio")) == "true",
        "offset_x_mm": float(await get_parametro(db, "certificado_offset_x_mm")),
        "offset_y_mm": float(await get_parametro(db, "certificado_offset_y_mm")),
    }


def _a_oaxaca(momento: datetime.datetime | None) -> datetime.datetime | None:
    if momento is None:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=datetime.timezone.utc)
    return momento.astimezone(ZONA_OAXACA)


def _txt(valor) -> str:
    return "" if valor is None else _html.escape(str(valor))


def _num(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float):
        return f"{valor:g}"
    return str(valor)


def _texto_semestre(semestre: int | None, anio: int) -> str:
    if semestre == 1:
        return f"1er Semestre {anio}"
    if semestre == 2:
        return f"2do Semestre {anio}"
    return ""


# Ancho promedio de un carácter de Arial/Liberation Sans en mayúsculas, como
# fracción del tamaño de letra — estimación conservadora para decidir cuándo
# reducir la letra (WeasyPrint no expone la medición antes de maquetar).
_ANCHO_CARACTER_EM = 0.62
_TAMANO_LETRA_PT = 8.0
_TAMANO_MINIMO_PT = 5.0


def _div(
    texto: str, anclaje: str, x: float, y: float, clase: str = "", ancho_max: float | None = None
) -> str:
    if not texto:
        return ""
    extra = ""
    if ancho_max is not None:
        estimado = len(_html.unescape(texto)) * _ANCHO_CARACTER_EM * _TAMANO_LETRA_PT
        if estimado > ancho_max:
            tamano = max(_TAMANO_MINIMO_PT, _TAMANO_LETRA_PT * ancho_max / estimado)
            extra = f"font-size:{tamano:.1f}pt;"
        extra += f"max-width:{ancho_max:.0f}pt;overflow:hidden;"
    if anclaje == "l":
        estilo = f"left:{x:.1f}pt;"
    elif anclaje == "r":
        estilo = f"left:{x - 200:.1f}pt;width:200pt;text-align:right;"
    else:
        estilo = f"left:{x - 100:.1f}pt;width:200pt;text-align:center;"
    return f'<div class="c {clase}" style="{estilo}{extra}top:{y:.1f}pt;">{texto}</div>'


def generar_pdf_certificado(
    verificacion: Verificacion,
    vehiculo: Vehiculo,
    proyeccion: dict,
    *,
    resultado_prueba: ResultadoPrueba | None = None,
    config: dict | None = None,
) -> bytes:
    return HTML(
        string=html_certificado(
            verificacion, vehiculo, proyeccion, resultado_prueba=resultado_prueba, config=config
        )
    ).write_pdf()


def html_certificado(
    verificacion: Verificacion,
    vehiculo: Vehiculo,
    proyeccion: dict,
    *,
    resultado_prueba: ResultadoPrueba | None = None,
    config: dict | None = None,
) -> str:
    """'Certificate Result Projection Contract v1' (sección 4): las lecturas
    y el tipo se sobreimprimen EXCLUSIVAMENTE desde `proyeccion` — el
    snapshot congelado en `print_jobs.certificate_projection_json` (o su
    equivalente al vuelo para la vista previa). Los datos del expediente
    (propietario, placa, NIV...) no forman parte del contrato y se leen del
    expediente/vehículo directo, igual que antes. `resultado_prueba` solo
    aporta fecha/hora de fin de la prueba; `config` viene de
    `cargar_config_certificado` (None = valores por defecto)."""

    cfg = {**CONFIG_CERTIFICADO_DEFAULT, **(config or {})}
    metodo = proyeccion.get("method")
    layout = _LAYOUT_INTENSIVO if metodo == "DIESEL_OPACITY" else _LAYOUT_PARTICULAR
    fields = proyeccion.get("fields") or {}

    generado = proyeccion.get("generated_at")
    momento_generado = (
        _a_oaxaca(datetime.datetime.fromisoformat(generado)) if generado else None
    ) or datetime.datetime.now(ZONA_OAXACA)
    inicio = _a_oaxaca(getattr(verificacion, "created_at", None))
    fin = _a_oaxaca(resultado_prueba.finished_at if resultado_prueba else None) or momento_generado

    nombre = vehiculo.razon_social
    calle = " ".join(
        p for p in (vehiculo.propietario_calle, vehiculo.propietario_numero_exterior) if p
    )
    horas = " / ".join(m.strftime("%H:%M") for m in (inicio, fin) if m is not None)
    valores = {
        "nombre": _txt(nombre),
        "tarjeta": _txt(vehiculo.tarjeta_circulacion),
        "placa": _txt(verificacion.placa),
        "marca": _txt(vehiculo.marca),
        "calle": _txt(calle or None),
        "serie": _txt(vehiculo.niv),
        "submarca": _txt(vehiculo.linea),
        "tipo": _txt(_ETIQUETA_TIPO.get(proyeccion.get("certificate_type") or "", "")),
        "poblacion": _txt(vehiculo.propietario_colonia),
        "cp": _txt(vehiculo.propietario_codigo_postal),
        "estado": _txt(vehiculo.propietario_estado),
        "municipio": _txt(vehiculo.propietario_municipio),
        "modelo": _txt(vehiculo.modelo),
        "semestre": _txt(_texto_semestre(proyeccion.get("semestre"), momento_generado.year)),
        "cvv_linea": _txt(f"{cfg['clave_centro']}  Línea: {verificacion.linea_id}"),
        "equipo_marca": _txt(cfg["marca_equipo"]),
        "equipo_numero": _txt(cfg["numero_equipo"]),
        "certificado_anterior": "",
        "multa": "",
        "fecha": fin.strftime("%d/%m/%Y"),
        "horas": _txt(horas),
        "folio": _txt(verificacion.folio_externo) if cfg["imprime_folio"] else "",
        "coeficiente": _txt(_num(fields.get("coefficient_absorption_final_k_m1"))),
    }

    piezas = []
    ox = cfg["offset_x_mm"] * _PT_POR_MM
    oy = cfg["offset_y_mm"] * _PT_POR_MM
    for indice, (dx_copia, dy_encabezado, dy_bloque) in enumerate(layout["copias"]):
        dx = ox + dx_copia

        def dy(y: float) -> float:
            return oy + (dy_bloque if y >= layout["y_bloque_inferior"] else dy_encabezado)

        for campo, anclaje, x, y, *ancho in layout["campos"]:
            piezas.append(
                _div(valores[campo], anclaje, x + dx, y + dy(y), ancho_max=ancho[0] if ancho else None)
            )
        if metodo:
            for etiqueta, x, y in layout["etiquetas"]:
                piezas.append(_div(_txt(etiqueta), "l", x + dx, y + dy(y)))
            for campo, y in layout["lecturas"]:
                for fase, anclaje, x in (("ralenti", "r", 293.6), ("crucero", "c", 330.3)):
                    v = (fields.get(fase) or {}).get(campo)
                    piezas.append(_div(_txt(_num(v)), anclaje, x + dx, y + dy(y)))
        if indice == 1:
            px, py = layout["placa_grande"]
            piezas.append(_div(valores["placa"], "l", px + ox, py + oy, "grande"))

    html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          @page {{ size: A4; margin: 0; }}
          body {{ margin: 0; font-family: Arial, "Liberation Sans", sans-serif; font-size: 8pt; }}
          .c {{ position: absolute; line-height: 10.4pt; white-space: nowrap; }}
          .grande {{ font-size: 10.5pt; line-height: 13pt; font-weight: bold; }}
        </style>
      </head>
      <body>{"".join(piezas)}</body>
    </html>
    """
    return html
