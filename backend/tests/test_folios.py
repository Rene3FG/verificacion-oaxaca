from sqlalchemy import select

from app.models.enums import EstadoFolio, EstadoVerificacion, ResultadoFinal, StationType
from app.models.folio import Folio, FolioLote
from tests.conftest import (
    crear_estacion,
    crear_expediente,
    crear_sesion_activa,
    crear_sesion_supervisor,
)


async def _sesion_impresion(db_session, *, allowed_line_ids=None):
    estacion = await crear_estacion(
        db_session,
        station_type=StationType.IMPRESION,
        center_id="OAX-01",
        line_id=None,
        is_centralized=True,
        allowed_line_ids=allowed_line_ids or [1],
    )
    return await crear_sesion_activa(db_session, estacion=estacion)


async def _registrar_lote(
    client, sesion_supervisor, *, tipo_certificado="PARTICULAR", folio_inicio="OAX-000001", folio_fin="OAX-000003"
):
    return await client.post(
        "/api/folios/lotes",
        params={
            "tipo_certificado": tipo_certificado,
            "folio_inicio": folio_inicio,
            "folio_fin": folio_fin,
        },
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )


async def test_registrar_lote_crea_folios_disponibles_en_orden(client, db_session):
    sesion = await crear_sesion_supervisor(db_session)

    resp = await _registrar_lote(client, sesion, folio_inicio="OAX-000010", folio_fin="OAX-000012")
    assert resp.status_code == 200
    assert resp.json()["cantidad"] == 3

    folios = (
        await db_session.execute(select(Folio).order_by(Folio.orden))
    ).scalars().all()
    assert [f.folio for f in folios] == ["OAX-000010", "OAX-000011", "OAX-000012"]
    assert all(f.estatus == EstadoFolio.DISPONIBLE for f in folios)

    lote = (await db_session.execute(select(FolioLote))).scalar_one()
    assert lote.cantidad == 3
    assert lote.registrado_por == sesion.user_id


async def test_registrar_lote_sin_supervisor_responde_403(client, db_session):
    estacion = await crear_estacion(db_session, station_type=StationType.IMPRESION)
    sesion = await crear_sesion_activa(db_session, estacion=estacion)

    resp = await _registrar_lote(client, sesion)
    assert resp.status_code == 403


async def test_registrar_lote_duplicado_responde_422(client, db_session):
    sesion = await crear_sesion_supervisor(db_session)

    resp1 = await _registrar_lote(client, sesion, folio_inicio="OAX-000020", folio_fin="OAX-000022")
    assert resp1.status_code == 200

    resp2 = await _registrar_lote(client, sesion, folio_inicio="OAX-000021", folio_fin="OAX-000023")
    assert resp2.status_code == 422


async def test_registrar_lote_con_rango_invalido_responde_422(client, db_session):
    sesion = await crear_sesion_supervisor(db_session)

    resp = await _registrar_lote(client, sesion, folio_inicio="OAX-000050", folio_fin="RCH-000060")
    assert resp.status_code == 422


async def test_solicitar_folio_toma_el_siguiente_disponible_del_tipo(client, db_session):
    sesion_supervisor = await crear_sesion_supervisor(db_session)
    await _registrar_lote(
        client, sesion_supervisor, tipo_certificado="PARTICULAR",
        folio_inicio="OAX-000001", folio_fin="OAX-000003",
    )

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "PARTICULAR"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["folio"] == "OAX-000001"
    assert resp.json()["estado_expediente"] == EstadoVerificacion.FOLIO_ASIGNADO.value

    await db_session.refresh(expediente)
    assert expediente.folio_externo == "OAX-000001"
    assert expediente.folio_asignado_at is not None

    folio_asignado = (
        await db_session.execute(select(Folio).where(Folio.folio == "OAX-000001"))
    ).scalar_one()
    assert folio_asignado.estatus == EstadoFolio.ASIGNADO
    assert folio_asignado.verificacion_id == expediente.id


async def test_reintentar_solicitud_cinco_veces_produce_un_solo_folio_asignado(
    client, db_session
):
    """El inventario es local ahora, pero la idempotencia sigue siendo una
    regla de negocio: reintentar /solicitar no debe tomar un folio nuevo
    del inventario en cada llamada."""

    sesion_supervisor = await crear_sesion_supervisor(db_session)
    await _registrar_lote(
        client, sesion_supervisor, tipo_certificado="PARTICULAR",
        folio_inicio="OAX-000001", folio_fin="OAX-000005",
    )

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    folios_recibidos = set()
    for _ in range(5):
        resp = await client.post(
            f"/api/folios/solicitar/{expediente.id}",
            params={"tipo_certificado": "PARTICULAR"},
            headers={"X-Session-Id": str(sesion.id)},
        )
        assert resp.status_code == 200
        folios_recibidos.add(resp.json()["folio"])

    assert folios_recibidos == {"OAX-000001"}

    asignados = (
        await db_session.execute(
            select(Folio).where(Folio.estatus == EstadoFolio.ASIGNADO)
        )
    ).scalars().all()
    assert len(asignados) == 1


async def test_folio_de_otro_expediente_no_se_reutiliza(client, db_session):
    sesion_supervisor = await crear_sesion_supervisor(db_session)
    await _registrar_lote(
        client, sesion_supervisor, tipo_certificado="PARTICULAR",
        folio_inicio="OAX-000001", folio_fin="OAX-000002",
    )

    sesion = await _sesion_impresion(db_session)
    expediente_a = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    expediente_b = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp_a = await client.post(
        f"/api/folios/solicitar/{expediente_a.id}",
        params={"tipo_certificado": "PARTICULAR"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    resp_b = await client.post(
        f"/api/folios/solicitar/{expediente_b.id}",
        params={"tipo_certificado": "PARTICULAR"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_a.json()["folio"] == "OAX-000001"
    assert resp_b.json()["folio"] == "OAX-000002"


async def test_solicitar_segundo_tipo_con_folio_ya_asignado_responde_409(
    client, db_session
):
    """Regresión: pedir un tipo de certificado distinto mientras el
    expediente ya está en FOLIO_ASIGNADO (por otro tipo) tiraba un
    TransitionNotAllowed sin manejar (500) en vez de un 409 limpio."""

    sesion_supervisor = await crear_sesion_supervisor(db_session)
    await _registrar_lote(client, sesion_supervisor, tipo_certificado="PARTICULAR")
    await _registrar_lote(client, sesion_supervisor, tipo_certificado="RECHAZO", folio_inicio="RCH-000001", folio_fin="RCH-000003")

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp1 = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "PARTICULAR"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp1.json()["estado_expediente"] == EstadoVerificacion.FOLIO_ASIGNADO.value

    resp2 = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "RECHAZO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp2.status_code == 409


async def test_sin_folio_disponible_deja_expediente_en_folio_error(client, db_session):
    """Handoff: 'Sin folio disponible' significa que la lista local de ese
    tipo se agotó — no un timeout ni error de red. Sin ningún lote
    registrado, el inventario de INTENSIVO está vacío desde el inicio."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "INTENSIVO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409
    assert "Sin folio disponible" in resp.json()["detail"]

    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.FOLIO_ERROR
    assert expediente.folio_externo is None


async def test_reintento_tras_folio_error_toma_folio_cuando_ya_hay_inventario(
    client, db_session
):
    sesion_supervisor = await crear_sesion_supervisor(db_session)
    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp_error = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "DOBLE_CERO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_error.status_code == 409

    await _registrar_lote(
        client, sesion_supervisor, tipo_certificado="DOBLE_CERO",
        folio_inicio="DBC-000001", folio_fin="DBC-000001",
    )

    resp_ok = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "DOBLE_CERO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["folio"] == "DBC-000001"
    assert resp_ok.json()["estado_expediente"] == EstadoVerificacion.FOLIO_ASIGNADO.value


async def test_inventario_folios_resume_conteos_por_tipo_y_estatus(client, db_session):
    sesion_supervisor = await crear_sesion_supervisor(db_session)
    await _registrar_lote(
        client, sesion_supervisor, tipo_certificado="PARTICULAR",
        folio_inicio="OAX-000001", folio_fin="OAX-000003",
    )

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()
    await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "PARTICULAR"},
        headers={"X-Session-Id": str(sesion.id)},
    )

    resp = await client.get(
        "/api/folios/inventario", headers={"X-Session-Id": str(sesion_supervisor.id)}
    )
    assert resp.status_code == 200
    resumen = {fila["tipo_certificado"]: fila for fila in resp.json()}
    assert resumen["PARTICULAR"]["disponibles"] == 2
    assert resumen["PARTICULAR"]["asignados"] == 1
    assert resumen["RECHAZO"]["disponibles"] == 0


async def test_expediente_completo_llega_a_cerrado(client, db_session):
    """Camino feliz de punta a punta: alta de lote, tipo de certificado
    manual (aprobado), solicitud de folio real del inventario local,
    imprimir, cerrar."""

    sesion_supervisor = await crear_sesion_supervisor(db_session)
    await _registrar_lote(
        client, sesion_supervisor, tipo_certificado="PARTICULAR",
        folio_inicio="OAX-000001", folio_fin="OAX-000001",
    )

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    db_session.add(expediente)
    await db_session.commit()

    resp_certificado = await client.post(
        f"/api/impresion/tipo-certificado/{expediente.id}",
        params={"tipo_certificado": "PARTICULAR"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_certificado.status_code == 200
    assert resp_certificado.json()["certificado_tipo"] == "PARTICULAR"

    resp_folio = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "PARTICULAR"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_folio.status_code == 200
    assert resp_folio.json()["estado_expediente"] == EstadoVerificacion.FOLIO_ASIGNADO.value

    resp_imprimir = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_imprimir.status_code == 200
    assert resp_imprimir.json()["estado_expediente"] == EstadoVerificacion.IMPRESO.value

    resp_cerrar = await client.post(
        f"/api/impresion/cerrar/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_cerrar.status_code == 200
    assert resp_cerrar.json()["estado_expediente"] == EstadoVerificacion.CERRADO.value
