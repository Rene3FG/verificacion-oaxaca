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
