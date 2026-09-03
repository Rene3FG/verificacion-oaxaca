from sqlalchemy import select

from app.models.enums import (
    EstadoVerificacion,
    FaseLectura,
    MetodoPrueba,
    StationType,
    TipoPrueba,
)
from app.models.event_log import EventLog
from app.models.limite_emision import LimiteEmision
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa, crear_sesion_supervisor

LECTURA_GASOLINA_OK = {"hc_ppm": 50, "co_pct": 0.3, "co2_pct": 10.0, "o2_pct": 1.0}
LECTURA_GASOLINA_EXCEDIDA = {"hc_ppm": 999, "co_pct": 0.3, "co2_pct": 10.0, "o2_pct": 1.0}

LIMITES_GASOLINA_DEFAULT = {"hc_ppm": 200, "co_pct": 1.0, "co2_pct": 16.0, "o2_pct": 2.0}


async def _sesion_prueba(db_session, *, line_id: int = 1):
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=line_id
    )
    return await crear_sesion_activa(db_session, estacion=estacion)


async def _cargar_limites(db_session, metodo: MetodoPrueba, fase: FaseLectura | None, valores: dict):
    for parametro, valor_maximo in valores.items():
        db_session.add(
            LimiteEmision(metodo=metodo, fase=fase, parametro=parametro, valor_maximo=valor_maximo)
        )
    await db_session.commit()


async def _cargar_limites_gasolina(db_session, metodo: MetodoPrueba):
    await _cargar_limites(db_session, metodo, FaseLectura.RALENTI, LIMITES_GASOLINA_DEFAULT)
    await _cargar_limites(db_session, metodo, FaseLectura.CRUCERO, LIMITES_GASOLINA_DEFAULT)


def _payload_gasolina(*, crucero_excedido: bool = False) -> dict:
    return {
        "ralenti": LECTURA_GASOLINA_OK,
        "crucero": LECTURA_GASOLINA_EXCEDIDA if crucero_excedido else LECTURA_GASOLINA_OK,
    }


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
        json={"normalized_payload": {}},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 409
    assert "combustible" in resp.json()["detail"].lower()


async def test_guardar_resultado_con_combustible_validado_ok(client, db_session):
    """'Certificate Result Projection Contract v1' (sección 4): el
    resultado ya no lo elige el operador — se calcula comparando
    `normalized_payload` contra los límites configurados."""

    sesion = await _sesion_prueba(db_session)
    await _cargar_limites_gasolina(db_session, MetodoPrueba.GAS_DYNAMIC)
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
        json={"normalized_payload": _payload_gasolina()},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["estado_expediente"] == EstadoVerificacion.PENDIENTE_IMPRESION.value


async def test_guardar_resultado_rechazado_va_a_cola_de_rechazo(client, db_session):
    """Revisión Figma 2026-08-24, sección 14 punto 3: un rechazo por prueba
    (no solo por inspección visual) también va a su propia cola
    PENDIENTE_DE_IMPRESION_RECHAZO, distinta de la de un aprobado. El
    rechazo ahora lo produce una lectura que excede el límite configurado,
    no una elección manual del operador."""

    sesion = await _sesion_prueba(db_session)
    await _cargar_limites_gasolina(db_session, MetodoPrueba.GAS_DYNAMIC)
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
        json={"normalized_payload": _payload_gasolina(crucero_excedido=True)},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 200
    assert (
        resp.json()["estado_expediente"]
        == EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO.value
    )


async def test_guardar_resultado_sin_limites_configurados_responde_409(client, db_session):
    """Sin `LimiteEmision` cargado para el método, el servidor rechaza en
    vez de inventar un umbral o caer a selección manual — mismo patrón que
    'Sin folio disponible' en folios."""

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
        json={"normalized_payload": _payload_gasolina()},
        headers={"X-Session-Id": str(sesion.id)},
    )

    assert resp.status_code == 409
    assert "Límites de emisión no configurados" in resp.json()["detail"]


async def test_guardar_resultado_diesel_evalua_coeficiente_de_absorcion(client, db_session):
    sesion = await _sesion_prueba(db_session)
    await _cargar_limites(
        db_session,
        MetodoPrueba.DIESEL_OPACITY,
        None,
        {"coefficient_absorption_final_k_m1": 0.5},
    )
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.PRUEBA_EN_PROCESO,
        combustible_validado="DIESEL",
    )
    expediente.tipo_prueba_final = TipoPrueba.OPACIDAD
    db_session.add(expediente)
    await db_session.commit()

    resp_aprobado = await client.post(
        f"/api/pruebas/resultado/{expediente.id}",
        json={"normalized_payload": {"coefficient_absorption_final_k_m1": 0.35}},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_aprobado.status_code == 200
    assert resp_aprobado.json()["estado_expediente"] == EstadoVerificacion.PENDIENTE_IMPRESION.value

    expediente2 = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.PRUEBA_EN_PROCESO,
        combustible_validado="DIESEL",
    )
    expediente2.tipo_prueba_final = TipoPrueba.OPACIDAD
    db_session.add(expediente2)
    await db_session.commit()

    resp_rechazado = await client.post(
        f"/api/pruebas/resultado/{expediente2.id}",
        json={"normalized_payload": {"coefficient_absorption_final_k_m1": 0.9}},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_rechazado.status_code == 200
    assert (
        resp_rechazado.json()["estado_expediente"]
        == EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO.value
    )


async def test_guardar_resultado_diesel_estratifica_por_peso_bruto(client, db_session):
    """NOM-045 (2026-09-02): igual que NOM-041 estratifica por año-modelo,
    diésel estratifica por `peso_bruto_vehicular_kg` — mismo mecanismo
    (`_en_rango_peso`), valores de prueba (no la tabla oficial, todavía sin
    cargar)."""

    sesion = await _sesion_prueba(db_session)
    db_session.add_all(
        [
            LimiteEmision(
                metodo=MetodoPrueba.DIESEL_OPACITY,
                fase=None,
                parametro="coefficient_absorption_final_k_m1",
                valor_maximo=0.5,
                peso_bruto_desde_kg=None,
                peso_bruto_hasta_kg=3856,
            ),
            LimiteEmision(
                metodo=MetodoPrueba.DIESEL_OPACITY,
                fase=None,
                parametro="coefficient_absorption_final_k_m1",
                valor_maximo=0.7,
                peso_bruto_desde_kg=3857,
                peso_bruto_hasta_kg=None,
            ),
        ]
    )
    await db_session.commit()

    expediente_ligero = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.PRUEBA_EN_PROCESO,
        combustible_validado="DIESEL",
        peso_bruto_vehicular_kg=3000,
    )
    expediente_ligero.tipo_prueba_final = TipoPrueba.OPACIDAD
    db_session.add(expediente_ligero)
    await db_session.commit()

    # 0.6 excede el límite del bracket ligero (0.5) pero no el pesado (0.7)
    resp_ligero = await client.post(
        f"/api/pruebas/resultado/{expediente_ligero.id}",
        json={"normalized_payload": {"coefficient_absorption_final_k_m1": 0.6}},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_ligero.status_code == 200
    assert (
        resp_ligero.json()["estado_expediente"]
        == EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO.value
    )

    expediente_pesado = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.PRUEBA_EN_PROCESO,
        combustible_validado="DIESEL",
        peso_bruto_vehicular_kg=4000,
    )
    expediente_pesado.tipo_prueba_final = TipoPrueba.OPACIDAD
    db_session.add(expediente_pesado)
    await db_session.commit()

    resp_pesado = await client.post(
        f"/api/pruebas/resultado/{expediente_pesado.id}",
        json={"normalized_payload": {"coefficient_absorption_final_k_m1": 0.6}},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_pesado.status_code == 200
    assert resp_pesado.json()["estado_expediente"] == EstadoVerificacion.PENDIENTE_IMPRESION.value

    # Sin peso capturado no se asume ningún bracket — rechaza en vez de
    # adivinar, mismo criterio que año-modelo faltante en gasolina.
    expediente_sin_peso = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.PRUEBA_EN_PROCESO,
        combustible_validado="DIESEL",
    )
    expediente_sin_peso.tipo_prueba_final = TipoPrueba.OPACIDAD
    db_session.add(expediente_sin_peso)
    await db_session.commit()

    resp_sin_peso = await client.post(
        f"/api/pruebas/resultado/{expediente_sin_peso.id}",
        json={"normalized_payload": {"coefficient_absorption_final_k_m1": 0.1}},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_sin_peso.status_code == 409
    assert "Límites de emisión no configurados" in resp_sin_peso.json()["detail"]


async def test_limites_emision_diesel_no_admite_anio_modelo(client, db_session):
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.PRUEBA)
    resp = await client.post(
        "/api/pruebas/limites-emision",
        json={
            "metodo": "DIESEL_OPACITY",
            "parametro": "coefficient_absorption_final_k_m1",
            "valor_maximo": 0.5,
            "anio_modelo_desde": 2000,
        },
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 422


async def test_limites_emision_gasolina_no_admite_peso_bruto(client, db_session):
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.PRUEBA)
    resp = await client.post(
        "/api/pruebas/limites-emision",
        json={
            "metodo": "GAS_DYNAMIC",
            "fase": "RALENTI",
            "parametro": "hc_ppm",
            "valor_maximo": 200,
            "peso_bruto_desde_kg": 1000,
        },
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 422


async def test_guardar_resultado_tipo_prueba_sin_metodo_responde_409(client, db_session):
    """TipoPrueba.ALTERNA no tiene método de proyección aprobado (sección
    4) — bloquear en vez de adivinar."""

    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.PRUEBA_EN_PROCESO,
        combustible_validado="GASOLINA",
    )
    expediente.tipo_prueba_final = TipoPrueba.ALTERNA
    db_session.add(expediente)
    await db_session.commit()

    resp = await client.post(
        f"/api/pruebas/resultado/{expediente.id}",
        json={"normalized_payload": {}},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409


async def test_guardar_resultado_payload_invalido_responde_422(client, db_session):
    sesion = await _sesion_prueba(db_session)
    await _cargar_limites_gasolina(db_session, MetodoPrueba.GAS_DYNAMIC)
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
        json={"normalized_payload": {"ralenti": {"hc_ppm": 50}}},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 422


async def test_limites_emision_upsert_requiere_supervisor(client, db_session):
    sesion = await _sesion_prueba(db_session)
    resp = await client.post(
        "/api/pruebas/limites-emision",
        json={
            "metodo": "GAS_DYNAMIC",
            "fase": "RALENTI",
            "parametro": "hc_ppm",
            "valor_maximo": 200,
        },
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_limites_emision_upsert_y_listado(client, db_session):
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.PRUEBA)

    resp_alta = await client.post(
        "/api/pruebas/limites-emision",
        json={
            "metodo": "GAS_DYNAMIC",
            "fase": "RALENTI",
            "parametro": "hc_ppm",
            "valor_maximo": 200,
        },
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp_alta.status_code == 200

    resp_update = await client.post(
        "/api/pruebas/limites-emision",
        json={
            "metodo": "GAS_DYNAMIC",
            "fase": "RALENTI",
            "parametro": "hc_ppm",
            "valor_maximo": 250,
        },
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp_update.status_code == 200

    resp_listado = await client.get(
        "/api/pruebas/limites-emision",
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp_listado.status_code == 200
    filas = resp_listado.json()
    # No se filtra por len(filas) == 1: la tabla real de NOM-041 (24 filas,
    # ver app/seed_limites_nom041.py) puede ya estar cargada en la misma
    # base que usan las pruebas (mismo criterio documentado para
    # seed_demo.py). Se busca la fila propia de este test por su
    # combinación exacta metodo+fase+parametro+año (sin acotar, la única
    # que este test pudo haber creado).
    fila_propia = [
        f
        for f in filas
        if f["metodo"] == "GAS_DYNAMIC"
        and f["fase"] == "RALENTI"
        and f["parametro"] == "hc_ppm"
        and f["anio_modelo_desde"] is None
        and f["anio_modelo_hasta"] is None
    ]
    assert len(fila_propia) == 1
    assert fila_propia[0]["valor_maximo"] == 250


async def test_limites_emision_diesel_no_admite_fase(client, db_session):
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.PRUEBA)
    resp = await client.post(
        "/api/pruebas/limites-emision",
        json={
            "metodo": "DIESEL_OPACITY",
            "fase": "RALENTI",
            "parametro": "coefficient_absorption_final_k_m1",
            "valor_maximo": 0.5,
        },
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 422


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
        json={"normalized_payload": {}},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409

    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.PRUEBA_CONFIGURADA
