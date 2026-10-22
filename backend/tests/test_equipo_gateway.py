"""Equipment Integration Contract v1 con el simulador de gateway
(HU-041/043/046/083). El reloj del simulador se inyecta para avanzar la
corrida sin esperar."""

import uuid

import pytest
from sqlalchemy import select

from app.main import app
from app.models.enums import EstadoVerificacion, MetodoPrueba, TipoPrueba
from app.models.event_log import EventLog
from app.models.resultado_prueba import ResultadoPrueba
from app.services.equipo_gateway import (
    EscenarioSimulador,
    EstadoEquipo,
    SimuladorGateway,
    get_equipment_gateway,
)
from tests.conftest import crear_expediente
from tests.test_pruebas import _expediente_en_prueba_dinamica, _sesion_prueba


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def simulador(reloj):
    gw = SimuladorGateway(reloj=reloj)
    app.dependency_overrides[get_equipment_gateway] = lambda: gw
    return gw


def _h(sesion):
    return {"X-Session-Id": str(sesion.id)}


async def test_simulador_recorre_los_estados_de_hu041(reloj):
    gw = SimuladorGateway(reloj=reloj)
    estacion = uuid.uuid4()
    run = uuid.uuid4()
    corrida = await gw.open_session(estacion, run, MetodoPrueba.GAS_DYNAMIC)
    assert corrida.estado == EstadoEquipo.CONECTANDO

    vistos = []
    for t in (1.2, 2.5, 4.2, 4.8, 9.5):
        reloj.t = 1000.0 + t
        vistos.append((await gw.read_data(run)).estado)
    assert vistos == [
        EstadoEquipo.CONECTADO,
        EstadoEquipo.CALIBRANDO,
        EstadoEquipo.LECTURA_RECIBIDA,
        EstadoEquipo.PRUEBA_EN_PROCESO,
        EstadoEquipo.FINALIZADA,
    ]
    final = await gw.read_data(run)
    assert len(final.lecturas) == 6
    assert set(final.resultado) == {"ralenti", "crucero"}
    assert final.resultado["crucero"]["speed_kph"] == 40.0
    assert (await gw.get_status(estacion))[0] == EstadoEquipo.LISTO


async def test_modo_manual_no_ofrece_equipo(client, db_session):
    sesion, expediente = await _expediente_en_prueba_dinamica(db_session)

    resp = await client.get("/api/pruebas/equipo/estado", headers=_h(sesion))
    assert resp.json() == {"modo": "manual", "estado": None, "mensaje_tecnico": None}
    resp = await client.post(f"/api/pruebas/equipo/iniciar/{expediente.id}", headers=_h(sesion))
    assert resp.status_code == 409
    assert (await client.get(f"/api/pruebas/equipo/corrida/{expediente.id}", headers=_h(sesion))).json() is None


@pytest.mark.parametrize(
    "escenario,estado_final",
    [("APROBADO", "PENDIENTE_IMPRESION"), ("RECHAZADO", "PENDIENTE_DE_IMPRESION_RECHAZO")],
)
async def test_resultado_con_lecturas_del_equipo(client, db_session, simulador, reloj, escenario, estado_final):
    sesion, expediente = await _expediente_en_prueba_dinamica(db_session)

    resp = await client.post(
        f"/api/pruebas/equipo/iniciar/{expediente.id}?escenario={escenario}", headers=_h(sesion)
    )
    assert resp.status_code == 200
    run_id = resp.json()["test_run_id"]
    assert resp.json()["estado"] == "CONECTANDO"

    reloj.t += 5.0
    parcial = (await client.get(f"/api/pruebas/equipo/corrida/{expediente.id}", headers=_h(sesion))).json()
    assert parcial["test_run_id"] == run_id
    assert 0 < len(parcial["lecturas"]) < 6
    assert parcial["resultado"] is None

    # Antes de FINALIZADA no hay resultado que guardar.
    resp = await client.post(
        f"/api/pruebas/resultado/{expediente.id}", json={"test_run_id": run_id}, headers=_h(sesion)
    )
    assert resp.status_code == 409

    reloj.t += 10.0
    # normalized_payload se ignora: manda lo que midió el equipo.
    resp = await client.post(
        f"/api/pruebas/resultado/{expediente.id}",
        json={"test_run_id": run_id, "normalized_payload": {"basura": 1}},
        headers=_h(sesion),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["estado_expediente"] == estado_final

    resultado = await db_session.scalar(
        select(ResultadoPrueba).where(ResultadoPrueba.verificacion_id == expediente.id)
    )
    assert resultado.valores_medidos_json["origen_lecturas"] == "EQUIPO"
    assert resultado.valores_medidos_json["test_run_id"] == run_id
    evento = await db_session.scalar(
        select(EventLog).where(
            EventLog.verificacion_id == expediente.id, EventLog.evento == "equipo_corrida_iniciada"
        )
    )
    assert evento.detalle_json["test_run_id"] == run_id
    assert evento.detalle_json["modo"] == "simulador"


async def test_resultado_rechaza_corrida_que_no_es_la_vigente(client, db_session, simulador, reloj):
    sesion, expediente = await _expediente_en_prueba_dinamica(db_session)
    primera = (await client.post(f"/api/pruebas/equipo/iniciar/{expediente.id}", headers=_h(sesion))).json()
    segunda = (await client.post(f"/api/pruebas/equipo/iniciar/{expediente.id}", headers=_h(sesion))).json()
    assert primera["test_run_id"] != segunda["test_run_id"]
    reloj.t += 20.0

    resp = await client.post(
        f"/api/pruebas/resultado/{expediente.id}",
        json={"test_run_id": primera["test_run_id"]},
        headers=_h(sesion),
    )
    assert resp.status_code == 409
    resp = await client.post(
        f"/api/pruebas/resultado/{expediente.id}",
        json={"test_run_id": segunda["test_run_id"]},
        headers=_h(sesion),
    )
    assert resp.status_code == 200


async def test_falla_del_equipo_y_reintento(client, db_session, simulador, reloj):
    """HU-083: el equipo reporta el error; el operador lo registra, el
    expediente vuelve a la cola y la corrida se detiene y se desvincula."""

    sesion, expediente = await _expediente_en_prueba_dinamica(db_session)
    run_id = (await client.post(
        f"/api/pruebas/equipo/iniciar/{expediente.id}?escenario=FALLA", headers=_h(sesion)
    )).json()["test_run_id"]
    reloj.t += 8.0

    corrida = (await client.get(f"/api/pruebas/equipo/corrida/{expediente.id}", headers=_h(sesion))).json()
    assert corrida["estado"] == "ERROR"
    assert "timeout" in corrida["mensaje_tecnico"]
    resp = await client.post(
        f"/api/pruebas/resultado/{expediente.id}", json={"test_run_id": run_id}, headers=_h(sesion)
    )
    assert resp.status_code == 409

    resp = await client.post(
        f"/api/pruebas/interrumpir/{expediente.id}",
        json={"causa": "ERROR_EQUIPO", "motivo": "Analizador sin comunicación",
              "mensaje_tecnico": corrida["mensaje_tecnico"]},
        headers=_h(sesion),
    )
    assert resp.status_code == 200
    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.ERROR_INTEGRACION
    assert expediente.equipo_test_run_id is None

    # HU-054: el reintento es explícito y devuelve el expediente a la cola.
    resp = await client.post(f"/api/pruebas/reintentar/{expediente.id}", headers=_h(sesion))
    assert resp.status_code == 200
    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.LISTO_PARA_PRUEBA
    assert (
        await client.post(f"/api/pruebas/reintentar/{expediente.id}", headers=_h(sesion))
    ).status_code == 409
    evento = await db_session.scalar(
        select(EventLog).where(
            EventLog.verificacion_id == expediente.id, EventLog.evento == "prueba_error_equipo"
        )
    )
    assert evento.detalle_json["test_run_id"] == run_id
    assert (await simulador.read_data(uuid.UUID(run_id))).estado == EstadoEquipo.DESCONECTADO


async def test_diesel_con_lecturas_del_equipo(client, db_session, simulador, reloj):
    sesion = await _sesion_prueba(db_session)
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.PRUEBA_EN_PROCESO,
        combustible_validado="DIESEL",
        modelo=2015,
        peso_bruto_vehicular_kg=3000,
    )
    expediente.tipo_prueba_final = TipoPrueba.OPACIDAD
    await db_session.commit()

    run_id = (await client.post(f"/api/pruebas/equipo/iniciar/{expediente.id}", headers=_h(sesion))).json()["test_run_id"]
    reloj.t += 20.0
    corrida = (await client.get(f"/api/pruebas/equipo/corrida/{expediente.id}", headers=_h(sesion))).json()
    assert corrida["estado"] == "FINALIZADA"
    assert len(corrida["resultado"]["aceleraciones"]) == 3

    resp = await client.post(
        f"/api/pruebas/resultado/{expediente.id}", json={"test_run_id": run_id}, headers=_h(sesion)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["estado_expediente"] == "PENDIENTE_IMPRESION"


async def test_iniciar_lectura_exige_prueba_en_proceso_y_linea_propia(client, db_session, simulador):
    sesion, expediente = await _expediente_en_prueba_dinamica(db_session)
    otra = await _sesion_prueba(db_session, line_id=2)
    resp = await client.post(f"/api/pruebas/equipo/iniciar/{expediente.id}", headers=_h(otra))
    assert resp.status_code == 403
    resp = await client.get(f"/api/pruebas/equipo/corrida/{expediente.id}", headers=_h(otra))
    assert resp.status_code == 403

    expediente.estado = EstadoVerificacion.PRUEBA_CONFIGURADA
    await db_session.commit()
    resp = await client.post(f"/api/pruebas/equipo/iniciar/{expediente.id}", headers=_h(sesion))
    assert resp.status_code == 409

    estado = (await client.get("/api/pruebas/equipo/estado", headers=_h(sesion))).json()
    assert estado == {"modo": "simulador", "estado": "LISTO", "mensaje_tecnico": None}


async def test_iniciar_prueba_exige_equipo_listo(client, db_session, simulador, reloj):
    """HU-044: con el equipo ocupado en otra corrida de la línea, la prueba
    no se inicia; cuando la corrida termina, sí."""

    sesion, expediente = await _expediente_en_prueba_dinamica(db_session)
    await client.post(f"/api/pruebas/equipo/iniciar/{expediente.id}", headers=_h(sesion))

    otro = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PRUEBA_CONFIGURADA, combustible_validado="GASOLINA"
    )
    otro.tipo_prueba_final = TipoPrueba.DINAMICA
    await db_session.commit()

    reloj.t += 2.5
    resp = await client.post(f"/api/pruebas/iniciar/{otro.id}", headers=_h(sesion))
    assert resp.status_code == 409
    assert "CALIBRANDO" in resp.json()["detail"]

    reloj.t += 20.0
    resp = await client.post(f"/api/pruebas/iniciar/{otro.id}", headers=_h(sesion))
    assert resp.status_code == 200
