"""'Certificate Result Projection Contract v1' (sección 4, bloques 02/04).
Prueba unitaria directa de `generar_pdf_certificado` (sin HTTP, sin
WeasyPrint de por medio más que generar bytes reales) — verifica que el
layout lee de `proyeccion["fields"]`, no de datos crudos, y no rompe en
los huecos documentados del contrato (rechazo sin ResultadoPrueba, método
sin mapping). Ver test_impresion.py para la generación/uso del snapshot
vía los endpoints reales (vista previa e imprimir)."""

import uuid

from app.models.enums import EstadoVerificacion
from app.models.vehiculo import Vehiculo
from app.models.verificacion import Verificacion
from app.services.certificado import generar_pdf_certificado


def _verificacion(**kwargs) -> Verificacion:
    return Verificacion(
        id=uuid.uuid4(),
        vehiculo_id=uuid.uuid4(),
        placa="TST0001",
        centro_id="OAX-01",
        linea_id=1,
        estado=EstadoVerificacion.PENDIENTE_IMPRESION,
        folio_externo="OAX-000001",
        combustible_validado="GASOLINA",
        **kwargs,
    )


def _vehiculo(**kwargs) -> Vehiculo:
    return Vehiculo(id=uuid.uuid4(), placa="TST0001", marca="Nissan", linea="Tsuru", modelo=2015, **kwargs)


def test_pdf_gasolina_incluye_bloque_ralenti_crucero():
    proyeccion = {
        "certificate_type": "PARTICULAR",
        "semestre": 2,
        "method": "GAS_DYNAMIC",
        "evaluation_result": "APROBADO",
        "fields": {
            "ralenti": {
                "hc_ppm": 50,
                "co_pct": 0.5,
                "co2_pct": 13.0,
                "co_co2_pct": 13.5,
                "o2_pct": 1.0,
                "nox_ppm": None,
                "speed_kph": None,
            },
            "crucero": {
                "hc_ppm": 40,
                "co_pct": 0.4,
                "co2_pct": 13.2,
                "co_co2_pct": 13.6,
                "o2_pct": 0.9,
                "nox_ppm": None,
                "speed_kph": None,
            },
        },
    }

    pdf = generar_pdf_certificado(_verificacion(), _vehiculo(), proyeccion)

    assert pdf.startswith(b"%PDF")


def test_pdf_diesel_incluye_coeficiente_de_absorcion():
    proyeccion = {
        "certificate_type": "PARTICULAR",
        "semestre": 1,
        "method": "DIESEL_OPACITY",
        "evaluation_result": "APROBADO",
        # Solo el coeficiente entra al certificado (sección 4, bloque 04) —
        # el resto de las lecturas diésel se queda en valores_medidos_json,
        # nunca en `fields`.
        "fields": {"coefficient_absorption_final_k_m1": 1.2},
    }

    pdf = generar_pdf_certificado(_verificacion(), _vehiculo(), proyeccion)

    assert pdf.startswith(b"%PDF")


def test_pdf_rechazo_por_inspeccion_visual_sin_bloque_de_mediciones():
    """Hueco documentado del contrato: sin ResultadoPrueba, `method`/
    `fields` llegan vacíos (generar_proyeccion_certificado) — el layout no
    debe fabricar un bloque de mediciones ni romper."""

    proyeccion = {
        "certificate_type": "RECHAZO",
        "semestre": None,
        "method": None,
        "evaluation_result": "RECHAZADO",
        "fields": {},
    }

    pdf = generar_pdf_certificado(_verificacion(), _vehiculo(), proyeccion)

    assert pdf.startswith(b"%PDF")


def test_pdf_no_imprime_el_folio(monkeypatch):
    """Regla del cliente (2026-10-01): el folio viene preimpreso en el papel
    del certificado; el sistema no debe sobreimprimirlo."""

    capturado = {}

    class _HTML:
        def __init__(self, string):
            capturado["html"] = string

        def write_pdf(self):
            return b"%PDF"

    monkeypatch.setattr("app.services.certificado.HTML", _HTML)

    generar_pdf_certificado(_verificacion(), _vehiculo(), {"certificate_type": "PARTICULAR"})

    assert "OAX-000001" not in capturado["html"]
    assert "Folio" not in capturado["html"]


def test_pdf_escapa_html_de_campos_de_texto_libre(monkeypatch):
    """Placa/marca/línea vienen de captura o SIOX: no deben interpretarse
    como HTML (p. ej. <img src=file:///...>) al pasar por WeasyPrint."""

    capturado = {}

    class _HTML:
        def __init__(self, string):
            capturado["html"] = string

        def write_pdf(self):
            return b"%PDF"

    monkeypatch.setattr("app.services.certificado.HTML", _HTML)
    verificacion = _verificacion()
    verificacion.placa = '<img src="file:///etc/passwd">'
    vehiculo = Vehiculo(marca="<b>X</b>", linea="A&B", modelo=2020)

    generar_pdf_certificado(verificacion, vehiculo, {"certificate_type": "PARTICULAR"})

    assert "<img" not in capturado["html"]
    assert "&lt;img" in capturado["html"]
    assert "<b>X</b>" not in capturado["html"]
    assert "A&amp;B" in capturado["html"]


def _capturar_html(monkeypatch) -> dict:
    capturado = {}

    class _HTML:
        def __init__(self, string):
            capturado["html"] = string

        def write_pdf(self):
            return b"%PDF"

    monkeypatch.setattr("app.services.certificado.HTML", _HTML)
    return capturado


def _vehiculo_completo() -> Vehiculo:
    return _vehiculo(
        niv="3N1EB31S0ZK000001",
        razon_social="JUAN PEREZ LOPEZ",
        tarjeta_circulacion="TC-998877",
        propietario_estado="OAXACA",
        propietario_municipio="OAXACA DE JUAREZ",
        propietario_codigo_postal="68000",
        propietario_colonia="CENTRO",
        propietario_calle="REFORMA",
        propietario_numero_exterior="101",
    )


def test_plantilla_particular_tres_copias_con_lecturas_y_placa_grande(monkeypatch):
    """Plantilla `Particular.doc` del cliente (2026-10-05): sobreimpresión
    en 3 copias por hoja, lecturas RALENTÍ/CRUCERO, tipo real en vez del
    texto fijo, datos fijos del centro y la placa en grande en la 2ª copia."""

    capturado = _capturar_html(monkeypatch)
    proyeccion = {
        "certificate_type": "DOBLE_CERO",
        "semestre": 2,
        "method": "GAS_DYNAMIC",
        "generated_at": "2026-10-05T18:00:00+00:00",
        "fields": {
            "ralenti": {"hc_ppm": 51, "co_pct": 0.31, "co2_pct": 14.2, "co_co2_pct": 14.51,
                        "o2_pct": 0.8, "nox_ppm": 610, "speed_kph": 24},
            "crucero": {"hc_ppm": 42, "co_pct": 0.22, "co2_pct": 14.4, "co_co2_pct": 14.62,
                        "o2_pct": 0.7, "nox_ppm": 590, "speed_kph": 40},
        },
    }

    generar_pdf_certificado(_verificacion(), _vehiculo_completo(), proyeccion)
    html = capturado["html"]

    for texto in ("JUAN PEREZ LOPEZ", "TC-998877", "3N1EB31S0ZK000001", "REFORMA 101",
                  "DOBLE CERO", "2do Semestre 2026", "CVV-06  Línea: 1", "OBERTECH",
                  "14.51", "14.62", "610", "NOx ppm"):
        assert html.count(texto) == 3, texto
    assert "PARTICULAR" not in html
    assert html.count("TST0001") == 4  # 3 copias + placa grande
    assert 'class="c grande"' in html
    assert "COEFICIENTE" not in html


def test_plantilla_intensivo_para_diesel(monkeypatch):
    capturado = _capturar_html(monkeypatch)
    proyeccion = {
        "certificate_type": "INTENSIVO",
        "semestre": 1,
        "method": "DIESEL_OPACITY",
        "generated_at": "2026-03-01T18:00:00+00:00",
        "fields": {"coefficient_absorption_final_k_m1": 1.27},
    }

    generar_pdf_certificado(_verificacion(), _vehiculo_completo(), proyeccion)
    html = capturado["html"]

    assert html.count("1.27") == 3
    assert html.count("ABSORCION m-1") == 3
    assert html.count("1er Semestre 2026") == 3
    assert "HC ppm" not in html


def test_config_imprime_folio_y_calibracion(monkeypatch):
    """`certificado_imprime_folio=true` vuelve a sobreimprimir el folio
    (la regla vigente es no hacerlo); el offset desplaza todo el layout."""

    capturado = _capturar_html(monkeypatch)
    proyeccion = {"certificate_type": "PARTICULAR", "method": "GAS_STATIC", "fields": {}}

    generar_pdf_certificado(_verificacion(), _vehiculo(), proyeccion)
    assert "OAX-000001" not in capturado["html"]
    sin_offset = capturado["html"]

    generar_pdf_certificado(
        _verificacion(), _vehiculo(), proyeccion,
        config={"imprime_folio": True, "offset_x_mm": 10, "clave_centro": "CVV-11"},
    )
    assert capturado["html"].count("OAX-000001") == 3
    assert "CVV-11" in capturado["html"]
    assert "left:349.2pt" in sin_offset and "left:377.5pt" in capturado["html"]
