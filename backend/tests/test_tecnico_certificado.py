"""Campo 001 = técnico (definición del cliente 2026-11-06)."""

import uuid

from app.models.enums import EstadoVerificacion, ResultadoInspeccionVisual
from app.models.inspeccion_visual import InspeccionVisual
from app.models.resultado_prueba import ResultadoPrueba
from app.services.certificado import generar_pdf_certificado
from app.services.tecnico_certificado import resolver_tecnico
from tests.conftest import crear_expediente, crear_usuario
from tests.test_certificado_pdf import _capturar_html, _vehiculo_completo, _verificacion


def _proyeccion(tecnico):
    return {
        "certificate_type": "PARTICULAR", "semestre": 2, "method": None,
        "generated_at": "2026-11-09T18:00:00+00:00", "fields": {}, "technician_id": tecnico,
    }


def test_pdf_imprime_el_tecnico_en_el_campo_001(monkeypatch):
    capturado = _capturar_html(monkeypatch)
    generar_pdf_certificado(_verificacion(), _vehiculo_completo(), _proyeccion("TEC-07"))
    assert capturado["html"].count("TEC-07") == 3


def test_pdf_sin_tecnico_usa_el_parametro_fijo(monkeypatch):
    capturado = _capturar_html(monkeypatch)
    generar_pdf_certificado(_verificacion(), _vehiculo_completo(), _proyeccion(None))
    assert capturado["html"].count(">001<") == 3


async def test_aprobado_toma_al_tecnico_de_la_prueba_con_su_clave(db_session):
    tecnico = await crear_usuario(db_session, username="tecprueba")
    tecnico.clave_tecnico = "T-15"
    exp = await crear_expediente(db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION)
    rp = ResultadoPrueba(verificacion_id=exp.id, operador_id=tecnico.id)
    assert await resolver_tecnico(db_session, exp, rp) == "T-15"


async def test_sin_clave_usa_el_usuario(db_session):
    tecnico = await crear_usuario(db_session, username="sinclave")
    exp = await crear_expediente(db_session, linea_id=1)
    rp = ResultadoPrueba(verificacion_id=exp.id, operador_id=tecnico.id)
    assert await resolver_tecnico(db_session, exp, rp) == "sinclave"


async def test_rechazo_visual_toma_a_quien_hizo_la_inspeccion(db_session):
    inspector = await crear_usuario(db_session, username="inspector1")
    exp = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO
    )
    db_session.add(
        InspeccionVisual(verificacion_id=exp.id, operador_id=inspector.id, resultado=ResultadoInspeccionVisual.RECHAZADA,
                         checklist_json={})
    )
    await db_session.flush()
    assert await resolver_tecnico(db_session, exp, None) == "inspector1"


async def test_sin_operador_registrado_devuelve_none(db_session):
    exp = await crear_expediente(db_session, linea_id=1)
    assert await resolver_tecnico(db_session, exp, None) is None
    rp = ResultadoPrueba(verificacion_id=exp.id, operador_id=uuid.uuid4())
    assert await resolver_tecnico(db_session, exp, rp) is None
