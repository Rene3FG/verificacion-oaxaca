from app.models.enums import EstadoVerificacion, StationType, TipoPrueba
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa


async def _sesion_prueba(db_session, *, line_id: int = 1):
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=line_id
    )
    return await crear_sesion_activa(db_session, estacion=estacion)


async def test_guardar_resultado_sin_combustible_validado_responde_409(client, db_session):
    """HU-017: Prueba también rechaza un expediente sin combustible
    validado, en vez de guardar el resultado con combustible vacío."""

    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.PRUEBA_EN_PROCESO,
        combustible_validado=None,
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/pruebas/resultado/{expediente.id}",
        json={"resultado": "APROBADO", "valores_medidos_json": {}},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 409
    assert "combustible" in resp.json()["detail"].lower()


async def test_guardar_resultado_con_combustible_validado_ok(client, db_session):
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.PRUEBA_EN_PROCESO,
        combustible_validado="GASOLINA",
    )
    expediente.tipo_prueba_final = TipoPrueba.DINAMICA
    db_session.add(expediente)
    await db_session.commit()

    resp = await client.post(
        f"/api/pruebas/resultado/{expediente.id}",
        json={"resultado": "APROBADO", "valores_medidos_json": {}},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["estado_expediente"] == EstadoVerificacion.PENDIENTE_IMPRESION.value
