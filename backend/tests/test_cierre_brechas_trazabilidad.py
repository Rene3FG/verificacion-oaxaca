"""Pruebas que cierran brechas de la matriz de trazabilidad (corte
2026-10-20): HU-027, HU-034, HU-088 y HU-089. No cambian comportamiento;
fijan lo que el código ya hace y que ninguna prueba cubría."""

from sqlalchemy import select

from app.models.enums import EstadoVerificacion, StationType, TipoPrueba
from app.models.event_log import EventLog
from app.models.resultado_obd_sbd import ResultadoObdSbd
from app.services.inspeccion_visual import CHECKLIST_INSPECCION_VISUAL
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa


def _checklist(**overrides) -> dict:
    checklist = {clave: "BUENO" for clave in CHECKLIST_INSPECCION_VISUAL}
    checklist.update(overrides)
    return checklist


async def _sesion_prueba(db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    return await crear_sesion_activa(db_session, estacion=estacion)


async def _rechazar_inspeccion(client, db_session):
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE
    )
    await db_session.commit()
    resp = await client.post(
        f"/api/inspeccion/{expediente.id}",
        json={"checklist": _checklist(neumaticos="MALO")},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    return sesion, expediente


async def test_transicion_guarda_estado_anterior_nuevo_usuario_hora_y_causales(client, db_session):
    """HU-027."""
    sesion, expediente = await _rechazar_inspeccion(client, db_session)

    eventos = (
        await db_session.execute(
            select(EventLog).where(
                EventLog.verificacion_id == expediente.id,
                EventLog.estado_nuevo == EstadoVerificacion.INSPECCION_VISUAL_RECHAZADA,
            )
        )
    ).scalars().all()
    assert len(eventos) == 1
    ev = eventos[0]
    assert ev.estado_anterior == EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE
    assert ev.usuario_id == sesion.user_id
    assert ev.created_at is not None
    assert ev.detalle_json["causales"] == ["neumaticos"]


async def test_visual_rechazada_no_ofrece_obd_y_va_directo_a_impresion(client, db_session):
    """HU-034."""
    sesion, expediente = await _rechazar_inspeccion(client, db_session)
    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO

    for ruta in ("evaluar", "solicitar"):
        resp = await client.post(
            f"/api/obd/{ruta}/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
        )
        assert resp.status_code == 409, (ruta, resp.text)

    filas = (
        await db_session.execute(
            select(ResultadoObdSbd).where(ResultadoObdSbd.verificacion_id == expediente.id)
        )
    ).scalars().all()
    assert filas == []
    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO


async def test_expediente_conserva_estado_y_datos_al_retomarlo(client, db_session):
    """HU-088: un expediente a medias se vuelve a consultar con su estado y
    datos intactos, desde otra sesión de la misma estación."""
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.PRUEBA_CONFIGURADA,
        placa="RET0001",
        combustible_validado="GASOLINA",
    )
    expediente.tipo_prueba_final = TipoPrueba.DINAMICA
    await db_session.commit()

    otra = await crear_sesion_activa(
        db_session,
        estacion=await crear_estacion(
            db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
        ),
    )
    resp = await client.get(
        f"/api/expedientes/{expediente.id}", headers={"X-Session-Id": str(otra.id)}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["estado"] == EstadoVerificacion.PRUEBA_CONFIGURADA.value
    assert body["placa"] == "RET0001"
    assert body["combustible_validado"] == "GASOLINA"
    assert body["tipo_prueba_final"] == TipoPrueba.DINAMICA.value
    assert body["linea_id"] == 1 and body["centro_id"] == "OAX-01"
    assert body["updated_at"]


async def test_resultado_final_no_se_reemplaza_sin_flujo_autorizado(client, db_session):
    """HU-089: con el resultado ya guardado (PENDIENTE_IMPRESION), un
    segundo POST responde 409 y no cambia el estado."""
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.PENDIENTE_IMPRESION,
        combustible_validado="GASOLINA",
    )
    expediente.tipo_prueba_final = TipoPrueba.DINAMICA
    await db_session.commit()

    resp = await client.post(
        f"/api/pruebas/resultado/{expediente.id}",
        json={"normalized_payload": {}},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409
    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.PENDIENTE_IMPRESION
