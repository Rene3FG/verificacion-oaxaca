from app.models.enums import EstadoVerificacion, StationType
from app.services.inspeccion_visual import CHECKLIST_INSPECCION_VISUAL
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa

CHECKLIST_TODO_BUENO = {clave: "BUENO" for clave in CHECKLIST_INSPECCION_VISUAL}


async def _sesion(db_session, *, station_type: StationType, line_id: int | None = 1, **kw):
    estacion = await crear_estacion(
        db_session, station_type=station_type, center_id="OAX-01", line_id=line_id, **kw
    )
    return await crear_sesion_activa(db_session, estacion=estacion)


async def test_pruebas_configurar_desde_captura_responde_403(client, db_session):
    sesion = await _sesion(db_session, station_type=StationType.CAPTURA)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.LISTO_PARA_PRUEBA
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/pruebas/configurar/{expediente.id}?tipo_prueba=DINAMICA",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_impresion_imprimir_desde_prueba_responde_403(client, db_session):
    sesion = await _sesion(db_session, station_type=StationType.PRUEBA)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        params={"print_job_id": "00000000-0000-0000-0000-000000000099"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_impresion_cola_desde_captura_responde_403(client, db_session):
    sesion = await _sesion(
        db_session,
        station_type=StationType.CAPTURA,
        line_id=None,
        is_centralized=True,
        allowed_line_ids=[1],
    )
    await db_session.commit()

    resp = await client.get(
        "/api/impresion/cola", headers={"X-Session-Id": str(sesion.id)}
    )
    assert resp.status_code == 403


async def test_folios_solicitar_desde_captura_responde_403(client, db_session):
    sesion = await _sesion(db_session, station_type=StationType.CAPTURA)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "APROBADO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_folios_solicitar_desde_impresion_no_es_403(client, db_session):
    """Confirma que el guard no bloquea a la estación correcta; sin ningún
    lote de folios registrado, el inventario local está vacío, así que la
    respuesta correcta es 409 (sin folio disponible), nunca un 403 de
    permisos."""

    sesion = await _sesion(
        db_session,
        station_type=StationType.IMPRESION,
        line_id=None,
        is_centralized=True,
        allowed_line_ids=[1],
    )
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "PARTICULAR"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409


async def test_inspeccion_desde_captura_responde_403(client, db_session):
    """Decisión 2026-08-07: Inspección Visual corre en estación de Prueba."""

    sesion = await _sesion(db_session, station_type=StationType.CAPTURA)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/inspeccion/{expediente.id}",
        json={"checklist": CHECKLIST_TODO_BUENO},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_obd_evaluar_desde_impresion_responde_403(client, db_session):
    """Decisión 2026-08-07: OBD/SBD corre en estación de Prueba."""

    sesion = await _sesion(
        db_session,
        station_type=StationType.IMPRESION,
        line_id=None,
        is_centralized=True,
        allowed_line_ids=[1],
    )
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.INSPECCION_VISUAL_APROBADA
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/obd/evaluar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_flujo_completo_captura_a_inspeccion_visual(client, db_session):
    """Regresión del gap encontrado el 2026-08-06: antes de agregar
    /normalizar, este camino completo (SIOX exitoso -> confirmar
    normalización -> inspección visual) era imposible: registrar_inspeccion
    lanzaba TransitionNotAllowed porque nada dejaba el expediente en
    INSPECCION_VISUAL_PENDIENTE."""

    captura = await _sesion(db_session, station_type=StationType.CAPTURA)
    prueba = await _sesion(db_session, station_type=StationType.PRUEBA)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.DATOS_SIOX_IMPORTADOS,
        combustible="GASOLINA",
    )
    await db_session.commit()

    resp_normalizar = await client.post(
        f"/api/expedientes/{expediente.id}/normalizar",
        headers={"X-Session-Id": str(captura.id)},
    )
    assert resp_normalizar.status_code == 200
    assert (
        resp_normalizar.json()["estado"]
        == EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE.value
    )

    resp_inspeccion = await client.post(
        f"/api/inspeccion/{expediente.id}",
        json={"checklist": CHECKLIST_TODO_BUENO},
        headers={"X-Session-Id": str(prueba.id)},
    )
    assert resp_inspeccion.status_code == 200
    assert (
        resp_inspeccion.json()["estado_expediente"]
        == EstadoVerificacion.INSPECCION_VISUAL_APROBADA.value
    )
