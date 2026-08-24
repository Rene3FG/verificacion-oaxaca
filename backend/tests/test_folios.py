from sqlalchemy import select

from app.api.routers.folios import get_folios_client
from app.main import app
from app.models.enums import (
    EstadoFolioRequest,
    EstadoVerificacion,
    ResultadoFinal,
    StationType,
)
from app.models.folio_assignment import FolioAssignment
from app.models.folio_request import FolioRequest
from app.models.integration_log import IntegrationLog, IntegrationStatus
from app.services.folios_client import FoliosExternoClient, ModoFolioExterno
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


class _ClienteFolioExitoso(FoliosExternoClient):
    """Doble de prueba: siempre asigna el mismo folio fijo, para poder
    aserter contra un valor conocido (el modo EXITO real genera folios
    aleatorios)."""

    def __init__(self, *, folio="F-0001", ref="EXT-1"):
        super().__init__(modo=ModoFolioExterno.EXITO)
        self._folio = folio
        self._ref = ref

    async def consultar(self, payload: dict) -> dict:
        return {"folio": self._folio, "external_reference_id": self._ref, "status": "asignado"}


def _mock_sistema_externo_exitoso(*, folio="F-0001", ref="EXT-1"):
    """El modo se fija sobrescribiendo la dependencia de FastAPI
    (`app.dependency_overrides[get_folios_client]`), no con una variable
    global — el fixture `client` limpia el override al final de cada
    prueba (ver conftest.py), así que dos pruebas nunca se pisan entre sí."""

    app.dependency_overrides[get_folios_client] = lambda: _ClienteFolioExitoso(
        folio=folio, ref=ref
    )


async def test_reintentar_solicitud_cinco_veces_produce_un_solo_folio(
    client, db_session
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

    _mock_sistema_externo_exitoso()

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
    client, db_session
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

    _mock_sistema_externo_exitoso(folio="F-0002")

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
    client, db_session
):
    """Regresión: pedir un tipo de certificado distinto mientras el
    expediente ya está en FOLIO_ASIGNADO (por otro tipo) tiraba un
    TransitionNotAllowed sin manejar (500) en vez de un 409 limpio."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    _mock_sistema_externo_exitoso(folio="F-APROBACION")
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


async def test_folio_de_otro_expediente_no_se_reutiliza(client, db_session):
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

    _mock_sistema_externo_exitoso(folio="F-A")
    resp_a = await client.post(
        f"/api/folios/solicitar/{expediente_a.id}",
        params={"tipo_certificado": "APROBACION"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_a.json()["folio"] == "F-A"

    _mock_sistema_externo_exitoso(folio="F-B")
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


async def test_solicitar_folio_con_exito_asigna_y_pasa_a_folio_asignado(client, db_session):
    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    _mock_sistema_externo_exitoso(folio="F-9001")

    resp = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "APROBACION"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["folio"] == "F-9001"
    assert resp.json()["estado_expediente"] == EstadoVerificacion.FOLIO_ASIGNADO.value

    await db_session.refresh(expediente)
    assert expediente.folio_externo == "F-9001"
    assert expediente.folio_asignado_at is not None


async def test_folio_con_formato_invalido_bloquea_impresion_y_registra_error(
    client, db_session
):
    """El sistema externo puede responder 'asignado' con un folio que no
    cumple el formato esperado — no basta con mirar `status`, hay que
    validar el folio mismo. El expediente debe quedar en FOLIO_ERROR (no
    FOLIO_ASIGNADO), sin folio_externo, y con el error visible en
    integration_logs; imprimir debe seguir bloqueado."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    app.dependency_overrides[get_folios_client] = lambda: FoliosExternoClient(
        modo=ModoFolioExterno.FOLIO_INVALIDO
    )

    resp = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "APROBACION"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["folio"] is None
    assert resp.json()["estado_expediente"] == EstadoVerificacion.FOLIO_ERROR.value

    await db_session.refresh(expediente)
    assert expediente.folio_externo is None

    logs = (
        await db_session.execute(
            select(IntegrationLog).where(IntegrationLog.verificacion_id == expediente.id)
        )
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].status == IntegrationStatus.ERROR
    assert "formato inválido" in logs[0].error_message

    resp_imprimir = await client.post(
        f"/api/impresion/imprimir/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_imprimir.status_code == 409


async def test_folio_timeout_y_duplicado_dejan_expediente_en_folio_error(client, db_session):
    """Timeout y folio duplicado son modos distintos del error genérico,
    pero ambos deben resolver igual desde la perspectiva del expediente:
    FOLIO_ERROR, reintentable, con el motivo correcto en el log."""

    sesion = await _sesion_impresion(db_session)

    expediente_timeout = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    expediente_duplicado = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    app.dependency_overrides[get_folios_client] = lambda: FoliosExternoClient(
        modo=ModoFolioExterno.TIMEOUT
    )
    resp_timeout = await client.post(
        f"/api/folios/solicitar/{expediente_timeout.id}",
        params={"tipo_certificado": "APROBACION"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_timeout.status_code == 200
    assert resp_timeout.json()["estado_expediente"] == EstadoVerificacion.FOLIO_ERROR.value

    log_timeout = (
        await db_session.execute(
            select(IntegrationLog).where(
                IntegrationLog.verificacion_id == expediente_timeout.id
            )
        )
    ).scalar_one()
    assert "no respondió a tiempo" in log_timeout.error_message

    app.dependency_overrides[get_folios_client] = lambda: FoliosExternoClient(
        modo=ModoFolioExterno.FOLIO_DUPLICADO
    )
    resp_dup = await client.post(
        f"/api/folios/solicitar/{expediente_duplicado.id}",
        params={"tipo_certificado": "APROBACION"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_dup.status_code == 200
    assert resp_dup.json()["estado_expediente"] == EstadoVerificacion.FOLIO_ERROR.value

    log_dup = (
        await db_session.execute(
            select(IntegrationLog).where(
                IntegrationLog.verificacion_id == expediente_duplicado.id
            )
        )
    ).scalar_one()
    assert "duplicado" in log_dup.error_message


async def test_expediente_completo_llega_a_cerrado(client, db_session):
    """Camino feliz de punta a punta pasando por el endpoint real de
    solicitud de folio (no por estado inyectado directo en la fixture,
    que es lo que hacían las pruebas de impresión hasta ahora): folio
    exitoso → imprimir → cerrar. Antes de este cambio, ningún expediente
    llegaba a CERRADO habiendo pasado de verdad por /folios/solicitar."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    db_session.add(expediente)
    await db_session.commit()

    _mock_sistema_externo_exitoso(folio="F-CIERRE")

    resp_certificado = await client.post(
        f"/api/impresion/tipo-certificado/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp_certificado.status_code == 200
    tipo_certificado = resp_certificado.json()["certificado_tipo"]

    resp_folio = await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": tipo_certificado},
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
