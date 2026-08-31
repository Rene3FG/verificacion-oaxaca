"""'Certificate Result Projection Contract v1' (sección 4). Prueba unitaria
directa del servicio (sin HTTP) para los caminos que no valen la pena
montar por el flujo completo de impresión — ver test_reimpresion.py para
la generación/regeneración vía los endpoints reales."""

import datetime
import uuid

from app.models.enums import EstadoVerificacion, ResultadoPruebaEnum, TipoCertificado, TipoPrueba
from app.models.resultado_prueba import ResultadoPrueba
from app.models.verificacion import Verificacion
from app.services.proyeccion_certificado import calcular_semestre, generar_proyeccion_certificado


def _verificacion(**kwargs) -> Verificacion:
    return Verificacion(
        id=uuid.uuid4(),
        vehiculo_id=uuid.uuid4(),
        placa="TST0001",
        centro_id="OAX-01",
        linea_id=1,
        estado=EstadoVerificacion.PENDIENTE_IMPRESION,
        **kwargs,
    )


def test_rechazo_por_inspeccion_visual_sin_resultado_prueba():
    """El contrato (sección 4) no define un payload de sobreimpresión para
    el camino de rechazo directo por inspección visual (nunca pasa por
    Prueba) — se documenta como hueco del contrato, no se inventa un
    method/fields."""

    verificacion = _verificacion(
        certificado_tipo=TipoCertificado.RECHAZO.value, tipo_prueba_final=None
    )

    proyeccion = generar_proyeccion_certificado(verificacion, None)

    assert proyeccion["method"] is None
    assert proyeccion["layout_version"] is None
    assert proyeccion["fields"] == {}
    assert proyeccion["test_result_id"] is None
    assert proyeccion["evaluation_result"] == "RECHAZADO"
    assert proyeccion["certificate_type"] == TipoCertificado.RECHAZO.value


def test_diesel_solo_sobreimprime_el_coeficiente_de_absorcion():
    verificacion = _verificacion(
        certificado_tipo=TipoCertificado.RECHAZO.value, tipo_prueba_final=TipoPrueba.OPACIDAD
    )
    resultado_prueba = ResultadoPrueba(
        id=uuid.uuid4(),
        verificacion_id=verificacion.id,
        tipo_prueba=TipoPrueba.OPACIDAD,
        combustible="DIESEL",
        resultado=ResultadoPruebaEnum.RECHAZADO,
        valores_medidos_json={
            "coefficient_absorption_final_k_m1": 0.9,
            "engine_temp_c": 85.0,
            "rpm_idle": 800,
        },
        limites_aplicados_json={"coefficient_absorption_final_k_m1": 0.5},
        linea_id=1,
    )

    proyeccion = generar_proyeccion_certificado(verificacion, resultado_prueba)

    assert proyeccion["method"] == "DIESEL_OPACITY"
    assert proyeccion["fields"] == {"coefficient_absorption_final_k_m1": 0.9}
    assert proyeccion["evaluation_result"] == "RECHAZADO"
    assert proyeccion["test_result_id"] == str(resultado_prueba.id)


def test_calcular_semestre():
    assert calcular_semestre(datetime.date(2026, 1, 1)) == 1
    assert calcular_semestre(datetime.date(2026, 6, 30)) == 1
    assert calcular_semestre(datetime.date(2026, 7, 1)) == 2
    assert calcular_semestre(datetime.date(2026, 12, 31)) == 2
