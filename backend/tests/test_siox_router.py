from app.models.enums import EstadoVerificacion, StationType
from app.models.integration_log import IntegrationLog
from app.models.siox_consulta import EstadoSioxConsulta, SioxConsulta
from app.services.siox_client import SioxConsultaResultado
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_activa


async def _sesion_captura(db_session, *, line_id: int = 1):
    estacion = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=line_id
    )
    return await crear_sesion_activa(db_session, estacion=estacion)


def _mock_consultar_placa(monkeypatch, resultado: SioxConsultaResultado):
    async def _fake(placa: str) -> SioxConsultaResultado:
        return resultado

    monkeypatch.setattr("app.api.routers.siox.consultar_placa", _fake)


async def test_consultar_exitosa_transiciona_a_datos_siox_importados(
    client, db_session, monkeypatch
):
    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(db_session, linea_id=1)
    await db_session.commit()

    _mock_consultar_placa(
        monkeypatch,
        SioxConsultaResultado(
            status="EXITOSA",
            raw={"html": "<div>...</div>"},
            normalized={"placa": expediente.placa, "marca": "NISSAN", "modelo": 2023},
        ),
    )

    resp = await client.post(
        f"/api/siox/consultar/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "EXITOSA"
    assert body["estado_expediente"] == EstadoVerificacion.DATOS_SIOX_IMPORTADOS.value

    consulta = (await db_session.execute(
        SioxConsulta.__table__.select().where(SioxConsulta.verificacion_id == expediente.id)
    )).mappings().one()
    assert consulta["status"] == EstadoSioxConsulta.EXITOSA
    assert consulta["response_normalized"]["marca"] == "NISSAN"
    assert consulta["consultado_por"] == sesion.user_id

    log = (await db_session.execute(
        IntegrationLog.__table__.select().where(IntegrationLog.verificacion_id == expediente.id)
    )).mappings().one()
    assert log["integration_name"] == "SIOX"


async def test_consultar_sin_datos_no_bloquea_y_permite_captura_manual(
    client, db_session, monkeypatch
):
    """Regla SIOX: SIN_DATOS deja el expediente listo para captura manual,
    nunca lo traba."""

    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(db_session, linea_id=1)
    await db_session.commit()

    _mock_consultar_placa(
        monkeypatch, SioxConsultaResultado(status="SIN_DATOS", raw={"html": "no existe"}, normalized=None)
    )

    resp = await client.post(
        f"/api/siox/consultar/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "SIN_DATOS"
    assert body["estado_expediente"] == EstadoVerificacion.DATOS_SIOX_CONSULTADOS.value

    resp_manual = await client.post(
        f"/api/siox/captura-manual/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )
    assert resp_manual.status_code == 200
    assert (
        resp_manual.json()["estado_expediente"]
        == EstadoVerificacion.DATOS_CAPTURADOS_MANUALMENTE.value
    )


async def test_consultar_error_de_red_no_bloquea(client, db_session, monkeypatch):
    """Timeout/error de conexión con SIOX: el expediente no se cae, solo
    queda en DATOS_SIOX_CONSULTADOS y el operador sigue por captura manual."""

    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(db_session, linea_id=1)
    await db_session.commit()

    _mock_consultar_placa(
        monkeypatch, SioxConsultaResultado(status="ERROR", raw=None, normalized=None)
    )

    resp = await client.post(
        f"/api/siox/consultar/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ERROR"
    assert body["estado_expediente"] == EstadoVerificacion.DATOS_SIOX_CONSULTADOS.value

    log = (await db_session.execute(
        IntegrationLog.__table__.select().where(IntegrationLog.verificacion_id == expediente.id)
    )).mappings().one()
    assert log["status"].value == "error"


async def test_captura_manual_transiciona_estado(client, db_session):
    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(db_session, linea_id=1)
    await db_session.commit()

    resp = await client.post(
        f"/api/siox/captura-manual/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )

    assert resp.status_code == 200
    assert (
        resp.json()["estado_expediente"]
        == EstadoVerificacion.DATOS_CAPTURADOS_MANUALMENTE.value
    )


async def test_consultar_desde_estacion_de_prueba_responde_403(client, db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    expediente = await crear_expediente(db_session, linea_id=1)
    await db_session.commit()

    resp = await client.post(
        f"/api/siox/consultar/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )

    assert resp.status_code == 403


async def test_consultar_expediente_de_otra_linea_responde_403(client, db_session):
    sesion = await _sesion_captura(db_session, line_id=1)
    expediente_ajeno = await crear_expediente(db_session, linea_id=2)
    await db_session.commit()

    resp = await client.post(
        f"/api/siox/consultar/{expediente_ajeno.id}", headers={"X-Session-Id": str(sesion.id)}
    )

    assert resp.status_code == 403
