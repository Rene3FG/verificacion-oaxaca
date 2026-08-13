import datetime

from app.models.enums import EstadoVerificacion, FuenteDatos, StationType
from app.models.event_log import EventLog
from app.models.integration_log import IntegrationLog
from app.models.siox_consulta import EstadoSioxConsulta, SioxConsulta
from app.models.vehiculo import Vehiculo
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


async def test_consultar_exitosa_actualiza_vehiculo_y_marca_fuente_siox(
    client, db_session, monkeypatch
):
    """HU-012: la respuesta normalizada se mapea a las columnas del
    vehículo y su fuente_datos pasa a SIOX; estatus/version/motor no tienen
    columna propia y solo quedan en siox_consultas."""

    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(db_session, linea_id=1)
    await db_session.commit()

    _mock_consultar_placa(
        monkeypatch,
        SioxConsultaResultado(
            status="EXITOSA",
            raw={"html": "<div>...</div>"},
            normalized={
                "placa": expediente.placa,
                "niv": "3N1CN8AE1PL835483",
                "marca": "NISSAN MEXICANA, S.A. DE C.V.",
                "linea": "VERSA",
                "modelo": 2023,
                "tipo_vehiculo": "AUTOMOVIL",
                "estatus": "ACTIVO",
                "version": "SR CVT 1.6 LTS",
                "motor": "HR16",
            },
        ),
    )

    resp = await client.post(
        f"/api/siox/consultar/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )
    assert resp.status_code == 200

    vehiculo = await db_session.get(Vehiculo, expediente.vehiculo_id)
    assert vehiculo.niv == "3N1CN8AE1PL835483"
    assert vehiculo.marca == "NISSAN MEXICANA, S.A. DE C.V."
    assert vehiculo.linea == "VERSA"
    assert vehiculo.modelo == 2023
    assert vehiculo.tipo_vehiculo == "AUTOMOVIL"
    assert vehiculo.fuente_datos == FuenteDatos.SIOX

    evento = (await db_session.execute(
        EventLog.__table__.select().where(
            EventLog.verificacion_id == expediente.id,
            EventLog.evento == "datos_siox_importados",
        )
    )).mappings().one()
    assert set(evento["detalle_json"]["campos_actualizados"]) == {
        "niv",
        "marca",
        "linea",
        "modelo",
        "tipo_vehiculo",
    }


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


async def test_reintento_de_consulta_no_transiciona_pero_se_audita(
    client, db_session, monkeypatch
):
    """HU-014: la transición CREADO -> DATOS_SIOX_CONSULTADOS solo ocurre en
    el primer intento; un reintento no debe forzar una transición inválida,
    pero sí debe quedar auditado en event_log con su número de intento."""

    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(db_session, linea_id=1)
    await db_session.commit()

    _mock_consultar_placa(
        monkeypatch, SioxConsultaResultado(status="ERROR", raw=None, normalized=None)
    )

    primer_intento = await client.post(
        f"/api/siox/consultar/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )
    assert primer_intento.status_code == 200
    assert primer_intento.json()["intento"] == 1

    segundo_intento = await client.post(
        f"/api/siox/consultar/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )
    assert segundo_intento.status_code == 200
    body = segundo_intento.json()
    assert body["intento"] == 2
    # No hubo transición inválida: el expediente sigue en el mismo estado.
    assert body["estado_expediente"] == EstadoVerificacion.DATOS_SIOX_CONSULTADOS.value

    eventos = (
        await db_session.execute(
            EventLog.__table__.select()
            .where(
                EventLog.verificacion_id == expediente.id,
                EventLog.evento == "siox_consulta_intentada",
            )
            .order_by(EventLog.created_at)
        )
    ).mappings().all()
    assert len(eventos) == 2
    assert [e["detalle_json"]["intento"] for e in eventos] == [1, 2]
    assert eventos[1]["estado_anterior"] == EstadoVerificacion.DATOS_SIOX_CONSULTADOS
    assert eventos[1]["estado_nuevo"] == EstadoVerificacion.DATOS_SIOX_CONSULTADOS


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


async def test_historial_consultas_ordena_mas_reciente_primero(
    client, db_session, monkeypatch
):
    """HU-013: cada intento debe quedar visible en el historial, sin
    exponer response_raw en la lista."""

    sesion = await _sesion_captura(db_session)
    expediente = await crear_expediente(db_session, linea_id=1)
    await db_session.commit()

    _mock_consultar_placa(
        monkeypatch,
        SioxConsultaResultado(status="SIN_DATOS", raw={"html": "no existe"}, normalized=None),
    )
    await client.post(
        f"/api/siox/consultar/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )

    # `created_at` usa server_default=func.now(), que en Postgres es la hora
    # de INICIO DE TRANSACCIÓN, no del statement. Esta fixture comparte una
    # sola transacción para todo el test, así que ambas consultas nacerían
    # con el mismo created_at si no se atrasa la primera a mano; en
    # producción cada request tiene su propia transacción y esto no aplica.
    primera = (
        await db_session.execute(SioxConsulta.__table__.select())
    ).mappings().one()
    await db_session.execute(
        SioxConsulta.__table__.update()
        .where(SioxConsulta.id == primera["id"])
        .values(created_at=primera["created_at"] - datetime.timedelta(hours=1))
    )

    _mock_consultar_placa(
        monkeypatch,
        SioxConsultaResultado(
            status="EXITOSA",
            raw={"html": "<div>...</div>"},
            normalized={"placa": expediente.placa, "marca": "NISSAN", "modelo": 2023},
        ),
    )
    await client.post(
        f"/api/siox/consultar/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )

    resp = await client.get(
        f"/api/siox/consultas/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["status"] == "EXITOSA"
    assert body[0]["response_normalized"]["marca"] == "NISSAN"
    assert body[1]["status"] == "SIN_DATOS"
    assert "response_raw" not in body[0]
    assert body[0]["consultado_por"] == str(sesion.user_id)


async def test_historial_consultas_desde_estacion_de_prueba_responde_403(client, db_session):
    estacion = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    expediente = await crear_expediente(db_session, linea_id=1)
    await db_session.commit()

    resp = await client.get(
        f"/api/siox/consultas/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )

    assert resp.status_code == 403


async def test_historial_consultas_expediente_de_otra_linea_responde_403(client, db_session):
    sesion = await _sesion_captura(db_session, line_id=1)
    expediente_ajeno = await crear_expediente(db_session, linea_id=2)
    await db_session.commit()

    resp = await client.get(
        f"/api/siox/consultas/{expediente_ajeno.id}", headers={"X-Session-Id": str(sesion.id)}
    )

    assert resp.status_code == 403


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
