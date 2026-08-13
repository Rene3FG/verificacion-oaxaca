from sqlalchemy import select

from app.models.enums import EstadoFolioRequest, EstadoVerificacion, StationType
from app.models.folio_assignment import FolioAssignment
from app.models.folio_request import FolioRequest
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa


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


def _mock_sistema_externo_exitoso(monkeypatch, *, folio="F-0001", ref="EXT-1"):
    async def _fake(payload: dict) -> dict:
        return {"folio": folio, "external_reference_id": ref, "status": "asignado"}

    monkeypatch.setattr(
        "app.api.routers.folios._consultar_sistema_externo_folios", _fake
    )


async def test_reintentar_solicitud_cinco_veces_produce_un_solo_folio(
    client, db_session, monkeypatch
):
    """El sistema externo de folios es un stub en este proyecto (no hay
    integración real definida), pero la idempotencia del lado del sistema
    de verificación sí debe sostenerse: 5 llamadas a /solicitar con éxito
    deben producir un único FolioRequest ASIGNADO y una única
    FolioAssignment, nunca cinco folios distintos."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    _mock_sistema_externo_exitoso(monkeypatch)

    for _ in range(5):
        resp = await client.post(
            f"/api/folios/solicitar/{expediente.id}",
            params={"tipo_certificado": "APROBACION"},
            headers={"X-Session-Id": str(sesion.id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["folio"] == "F-0001"
        assert body["estado_expediente"] == EstadoVerificacion.FOLIO_ASIGNADO.value

    solicitudes = (
        await db_session.execute(
            select(FolioRequest).where(FolioRequest.verificacion_id == expediente.id)
        )
    ).scalars().all()
    assert len(solicitudes) == 1
    assert solicitudes[0].status == EstadoFolioRequest.ASIGNADO
    assert solicitudes[0].request_payload["solicitud_id"] == str(solicitudes[0].id)

    asignaciones = (
        await db_session.execute(
            select(FolioAssignment).where(FolioAssignment.verificacion_id == expediente.id)
        )
    ).scalars().all()
    assert len(asignaciones) == 1
    assert asignaciones[0].folio == "F-0001"

    await db_session.refresh(expediente)
    assert expediente.folio_externo == "F-0001"


async def test_solicitud_fallida_no_impide_reintento_posterior_exitoso(
    client, db_session, monkeypatch
):
    """Un primer intento con error (el stub por default) no debe dejar el
    expediente varado: un reintento posterior con éxito sí asigna folio,
    y solo ese segundo intento queda ASIGNADO."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp_error = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "APROBACION"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_error.status_code == 200
    assert resp_error.json()["estado_expediente"] == EstadoVerificacion.FOLIO_ERROR.value

    _mock_sistema_externo_exitoso(monkeypatch, folio="F-0002")

    resp_ok = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "APROBACION"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["folio"] == "F-0002"
    assert resp_ok.json()["estado_expediente"] == EstadoVerificacion.FOLIO_ASIGNADO.value

    asignaciones = (
        await db_session.execute(
            select(FolioAssignment).where(FolioAssignment.verificacion_id == expediente.id)
        )
    ).scalars().all()
    assert len(asignaciones) == 1
    assert asignaciones[0].folio == "F-0002"


async def test_solicitar_segundo_tipo_con_folio_ya_asignado_responde_409(
    client, db_session, monkeypatch
):
    """Regresión: pedir un tipo de certificado distinto mientras el
    expediente ya está en FOLIO_ASIGNADO (por otro tipo) tiraba un
    TransitionNotAllowed sin manejar (500) en vez de un 409 limpio."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    _mock_sistema_externo_exitoso(monkeypatch, folio="F-APROBACION")
    resp1 = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "APROBACION"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp1.json()["estado_expediente"] == EstadoVerificacion.FOLIO_ASIGNADO.value

    resp2 = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "RECHAZO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp2.status_code == 409


async def test_folio_de_otro_expediente_no_se_reutiliza(client, db_session, monkeypatch):
    """La deduplicación de HU-066/HU-071 filtra por verificacion_id Y
    tipo_certificado: dos expedientes distintos pidiendo el mismo tipo de
    certificado nunca deben compartir folio ni FolioRequest."""

    sesion = await _sesion_impresion(db_session)
    expediente_a = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    expediente_b = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    _mock_sistema_externo_exitoso(monkeypatch, folio="F-A")
    resp_a = await client.post(
        f"/api/folios/solicitar/{expediente_a.id}",
        params={"tipo_certificado": "APROBACION"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_a.json()["folio"] == "F-A"

    _mock_sistema_externo_exitoso(monkeypatch, folio="F-B")
    resp_b = await client.post(
        f"/api/folios/solicitar/{expediente_b.id}",
        params={"tipo_certificado": "APROBACION"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_b.json()["folio"] == "F-B"

    asignaciones = (
        await db_session.execute(
            select(FolioAssignment).where(
                FolioAssignment.verificacion_id.in_([expediente_a.id, expediente_b.id])
            )
        )
    ).scalars().all()
    assert {a.verificacion_id: a.folio for a in asignaciones} == {
        expediente_a.id: "F-A",
        expediente_b.id: "F-B",
    }
