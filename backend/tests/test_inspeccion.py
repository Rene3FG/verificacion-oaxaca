"""Checklist real de inspección visual (sección 8 de la revisión del Figma
2026-08-24): 8 puntos con Bueno/Malo/No aplica, resultado determinado por el
backend — cualquier MALO rechaza y esos puntos son las causales."""

from sqlalchemy import select

from app.models.enums import EstadoVerificacion, ResultadoInspeccionVisual, StationType
from app.models.inspeccion_visual import InspeccionVisual
from app.services.inspeccion_visual import CHECKLIST_INSPECCION_VISUAL
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa


def _checklist(**overrides) -> dict:
    checklist = {clave: "BUENO" for clave in CHECKLIST_INSPECCION_VISUAL}
    checklist.update(overrides)
    return checklist


async def _sesion_prueba(db_session, *, line_id: int = 1):
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=line_id
    )
    return await crear_sesion_activa(db_session, estacion=estacion)


async def test_catalogo_checklist_expone_los_8_puntos_reales(client, db_session):
    sesion = await _sesion_prueba(db_session)
    await db_session.commit()

    resp = await client.get(
        "/api/inspeccion/checklist", headers={"X-Session-Id": str(sesion.id)}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 8
    assert {item["clave"] for item in body} == set(CHECKLIST_INSPECCION_VISUAL)


async def test_inspeccion_todo_bueno_o_no_aplica_aprueba(client, db_session):
    """El resultado no lo manda el operador: sin ningún MALO, el backend
    aprueba solo. NO_APLICA no cuenta como falla."""

    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/inspeccion/{expediente.id}",
        json={"checklist": _checklist(componentes_emisiones="NO_APLICA")},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["resultado"] == ResultadoInspeccionVisual.APROBADA.value
    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.INSPECCION_VISUAL_APROBADA

    inspeccion = (
        await db_session.execute(
            select(InspeccionVisual).where(InspeccionVisual.verificacion_id == expediente.id)
        )
    ).scalar_one()
    assert inspeccion.resultado == ResultadoInspeccionVisual.APROBADA
    assert inspeccion.causales_rechazo is None
    assert inspeccion.checklist_json["componentes_emisiones"] == "NO_APLICA"


async def test_inspeccion_con_malo_rechaza_y_guarda_causales(client, db_session):
    """Regla de negocio #3 + sección 8: cualquier punto MALO rechaza; el
    expediente salta a la cola propia de impresión de rechazo y los puntos
    MALO quedan como causales (con etiqueta legible), más las observaciones
    del operador."""

    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/inspeccion/{expediente.id}",
        json={
            "checklist": _checklist(sistema_escape="MALO", neumaticos="MALO"),
            "observaciones": "Escape perforado, llanta delantera lisa",
        },
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["resultado"] == ResultadoInspeccionVisual.RECHAZADA.value
    assert set(body["causales_rechazo"]) == {"sistema_escape", "neumaticos"}
    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO

    inspeccion = (
        await db_session.execute(
            select(InspeccionVisual).where(InspeccionVisual.verificacion_id == expediente.id)
        )
    ).scalar_one()
    assert inspeccion.causales_rechazo["items"] == {
        "sistema_escape": CHECKLIST_INSPECCION_VISUAL["sistema_escape"],
        "neumaticos": CHECKLIST_INSPECCION_VISUAL["neumaticos"],
    }
    assert inspeccion.causales_rechazo["observaciones"] == (
        "Escape perforado, llanta delantera lisa"
    )


async def test_inspeccion_checklist_incompleto_responde_422(client, db_session):
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE
    )
    await db_session.commit()

    checklist = _checklist()
    checklist.pop("neumaticos")
    resp = await client.post(
        f"/api/inspeccion/{expediente.id}",
        json={"checklist": checklist},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 422
    assert "neumaticos" in resp.json()["detail"]


async def test_inspeccion_punto_desconocido_responde_422(client, db_session):
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/inspeccion/{expediente.id}",
        json={"checklist": _checklist(luces="BUENO")},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 422
    assert "luces" in resp.json()["detail"]


async def test_inspeccion_valor_invalido_responde_422(client, db_session):
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/inspeccion/{expediente.id}",
        json={"checklist": _checklist(sistema_escape="REGULAR")},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 422


async def test_inspeccion_fuera_de_estado_pendiente_responde_409(client, db_session):
    """Mismo patrón que pruebas.py/obd.py (2026-08-24): antes de este guard,
    registrar inspección fuera de INSPECCION_VISUAL_PENDIENTE tiraba
    TransitionNotAllowed sin manejar (500)."""

    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.LISTO_PARA_PRUEBA
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/inspeccion/{expediente.id}",
        json={"checklist": _checklist()},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 409


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
        json={"checklist": _checklist()},
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
        json={"checklist": _checklist()},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403
