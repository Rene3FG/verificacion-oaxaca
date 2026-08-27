from app.models.enums import EstadoVerificacion, StationType
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa


async def _sesion_prueba(db_session, *, line_id: int = 1):
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=line_id
    )
    return await crear_sesion_activa(db_session, estacion=estacion)


async def test_inspeccion_aprobada_transiciona_a_visual_aprobada(client, db_session):
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/inspeccion/{expediente.id}",
        json={"resultado": "APROBADA", "checklist_json": {"luces": True, "frenos": True}},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.INSPECCION_VISUAL_APROBADA


async def test_inspeccion_rechazada_salta_a_pendiente_impresion_rechazo(client, db_session):
    """Regla de negocio #3: rechazo visual salta OBD y prueba dinámica, va
    directo a la cola propia de impresión de rechazo (revisión Figma
    2026-08-24, sección 14 punto 3 — antes compartía cola con el aprobado)."""

    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/inspeccion/{expediente.id}",
        json={
            "resultado": "RECHAZADA",
            "checklist_json": {"luces": False},
            "causales_rechazo": {"causa": "luces deficientes"},
        },
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO


async def test_inspeccion_desde_estacion_captura_responde_403(client, db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/inspeccion/{expediente.id}",
        json={"resultado": "APROBADA", "checklist_json": {}},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_inspeccion_expediente_otra_linea_responde_403(client, db_session):
    sesion = await _sesion_prueba(db_session, line_id=1)
    expediente = await crear_expediente(
        db_session, linea_id=2, estado=EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/inspeccion/{expediente.id}",
        json={"resultado": "APROBADA", "checklist_json": {}},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403
