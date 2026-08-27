from sqlalchemy import select

from app.models.enums import EstadoVerificacion, StationType, TipoPrueba
from app.models.event_log import EventLog
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


async def test_guardar_resultado_rechazado_va_a_cola_de_rechazo(client, db_session):
    """Revisión Figma 2026-08-24, sección 14 punto 3: un rechazo por prueba
    (no solo por inspección visual) también va a su propia cola
    PENDIENTE_DE_IMPRESION_RECHAZO, distinta de la de un aprobado."""

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
        json={"resultado": "RECHAZADO", "valores_medidos_json": {}},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert (
        resp.json()["estado_expediente"]
        == EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO.value
    )


async def test_configurar_gasolina_propone_dinamica_por_defecto(client, db_session):
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.LISTO_PARA_PRUEBA,
        combustible_validado="GASOLINA",
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/pruebas/configurar/{expediente.id}?tipo_prueba=DINAMICA",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["estado_expediente"] == EstadoVerificacion.PRUEBA_CONFIGURADA.value

    await db_session.refresh(expediente)
    assert expediente.tipo_prueba_final == TipoPrueba.DINAMICA


async def test_configurar_gasolina_directo_a_opacidad_responde_409(client, db_session):
    """Gasolina solo puede cambiar de DINAMICA a ESTATICA (regla #9); saltar
    directo a OPACIDAD no es un cambio válido para este combustible."""

    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.LISTO_PARA_PRUEBA,
        combustible_validado="GASOLINA",
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/pruebas/configurar/{expediente.id}?tipo_prueba=OPACIDAD",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409


async def test_configurar_diesel_propone_opacidad_y_no_admite_cambio(client, db_session):
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.LISTO_PARA_PRUEBA,
        combustible_validado="DIESEL",
    )
    await db_session.commit()

    resp_ok = await client.post(
        f"/api/pruebas/configurar/{expediente.id}?tipo_prueba=OPACIDAD",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["estado_expediente"] == EstadoVerificacion.PRUEBA_CONFIGURADA.value

    expediente2 = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.LISTO_PARA_PRUEBA,
        combustible_validado="DIESEL",
    )
    await db_session.commit()

    resp_cambio = await client.post(
        f"/api/pruebas/configurar/{expediente2.id}?tipo_prueba=DINAMICA",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_cambio.status_code == 409


async def test_cambio_dinamica_a_estatica_queda_auditado(client, db_session):
    """Regla #9: el cambio de DINAMICA a ESTATICA solo se permite con
    cambio_manual=true y motivo, y queda auditado con usuario, motivo y
    fecha en event_log."""

    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.LISTO_PARA_PRUEBA,
        combustible_validado="GASOLINA",
    )
    await db_session.commit()

    resp_sin_motivo = await client.post(
        f"/api/pruebas/configurar/{expediente.id}"
        "?tipo_prueba=ESTATICA&cambio_manual=true",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_sin_motivo.status_code == 409

    resp = await client.post(
        f"/api/pruebas/configurar/{expediente.id}"
        "?tipo_prueba=ESTATICA&cambio_manual=true&motivo=Prueba+dinamometrica+no+disponible",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["estado_expediente"] == EstadoVerificacion.PRUEBA_CONFIGURADA.value

    evento = (
        await db_session.execute(
            select(EventLog).where(
                EventLog.verificacion_id == expediente.id,
                EventLog.evento == "cambio_tipo_prueba_dinamica_a_estatica",
            )
        )
    ).scalar_one()
    assert evento.usuario_id == sesion.user_id
    assert evento.detalle_json["motivo"] == "Prueba dinamometrica no disponible"
    assert evento.created_at is not None


async def test_iniciar_prueba_sin_inspeccion_visual_aprobada_responde_409(client, db_session):
    """Antes tiraba un TransitionNotAllowed sin manejar (500): un expediente
    que nunca pasó por inspección visual/OBD no puede saltarse directo a
    iniciar la prueba."""

    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE,
        combustible_validado="GASOLINA",
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/pruebas/iniciar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409

    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE


async def test_guardar_resultado_sin_prueba_iniciada_no_envia_a_impresion(client, db_session):
    """No se puede enviar a impresión sin resultado guardado: un expediente
    apenas configurado (prueba nunca iniciada) no puede reportar resultado
    ni, por lo tanto, transicionar a PENDIENTE_IMPRESION."""

    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.PRUEBA_CONFIGURADA,
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
    assert resp.status_code == 409

    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.PRUEBA_CONFIGURADA
