"""F4 (HU-042/102): catálogo de equipos y `equipo_id` resuelto por el servidor."""

from sqlalchemy import select

from app.models.enums import EstadoVerificacion, MetodoPrueba, StationType, TipoPrueba
from app.models.equipo import Equipo
from app.models.resultado_obd_sbd import ResultadoObdSbd
from app.models.resultado_prueba import ResultadoPrueba
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_supervisor
from tests.test_pruebas import _cargar_limites_gasolina, _payload_gasolina, _sesion_prueba


async def _equipo(db_session, sesion, tipo: str, serie: str, **extra) -> Equipo:
    equipo = Equipo(workstation_id=sesion.workstation_id, tipo=tipo, numero_serie=serie, **extra)
    db_session.add(equipo)
    await db_session.commit()
    return equipo


async def _expediente_gasolina_en_proceso(db_session):
    expediente = await crear_expediente(
        db_session,
        linea_id=1,
        estado=EstadoVerificacion.PRUEBA_EN_PROCESO,
        combustible_validado="GASOLINA",
    )
    expediente.tipo_prueba_final = TipoPrueba.DINAMICA
    db_session.add(expediente)
    await db_session.commit()
    return expediente


async def _resultado_de(db_session, expediente) -> ResultadoPrueba:
    return (
        await db_session.execute(
            select(ResultadoPrueba).where(ResultadoPrueba.verificacion_id == expediente.id)
        )
    ).scalar_one()


async def test_alta_edicion_y_listado_de_equipos(client, db_session):
    supervisor = await crear_sesion_supervisor(db_session)
    prueba = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1
    )
    await db_session.commit()
    headers = {"X-Session-Id": str(supervisor.id)}

    resp = await client.post(
        "/api/equipos",
        json={
            "workstation_id": str(prueba.id),
            "tipo": "ANALIZADOR_GASES",
            "marca": "Marca X",
            "numero_serie": "AG-0001",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    equipo_id = resp.json()["id"]
    assert resp.json()["is_active"] is True

    duplicado = await client.post(
        "/api/equipos",
        json={"workstation_id": str(prueba.id), "tipo": "OPACIMETRO", "numero_serie": "AG-0001"},
        headers=headers,
    )
    assert duplicado.status_code == 409

    resp = await client.patch(f"/api/equipos/{equipo_id}", json={"is_active": False}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    listado = await client.get("/api/equipos", params={"workstation_id": str(prueba.id)}, headers=headers)
    assert [e["numero_serie"] for e in listado.json()] == ["AG-0001"]


async def test_alta_de_equipo_valida_estacion_y_tipo(client, db_session):
    supervisor = await crear_sesion_supervisor(db_session)
    captura = await crear_estacion(
        db_session, station_type=StationType.CAPTURA, center_id="OAX-01", line_id=1
    )
    otro_centro = await crear_estacion(
        db_session, station_type=StationType.PRUEBA, center_id="OAX-99", line_id=1
    )
    await db_session.commit()
    headers = {"X-Session-Id": str(supervisor.id)}

    resp = await client.post(
        "/api/equipos",
        json={"workstation_id": str(captura.id), "tipo": "OPACIMETRO", "numero_serie": "OP-1"},
        headers=headers,
    )
    assert resp.status_code == 422

    resp = await client.post(
        "/api/equipos",
        json={"workstation_id": str(otro_centro.id), "tipo": "OPACIMETRO", "numero_serie": "OP-2"},
        headers=headers,
    )
    assert resp.status_code == 404

    resp = await client.post(
        "/api/equipos",
        json={"workstation_id": str(otro_centro.id), "tipo": "TOSTADOR", "numero_serie": "X"},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_equipos_exige_supervisor(client, db_session):
    sesion = await _sesion_prueba(db_session)
    resp = await client.get("/api/equipos", headers={"X-Session-Id": str(sesion.id)})
    assert resp.status_code == 403


async def test_resultado_toma_el_analizador_activo_de_la_estacion(client, db_session):
    sesion = await _sesion_prueba(db_session)
    await _cargar_limites_gasolina(db_session, MetodoPrueba.GAS_DYNAMIC)
    analizador = await _equipo(db_session, sesion, "ANALIZADOR_GASES", "AG-10")
    await _equipo(db_session, sesion, "OPACIMETRO", "OP-10")
    await _equipo(db_session, sesion, "ANALIZADOR_GASES", "AG-11", is_active=False)
    expediente = await _expediente_gasolina_en_proceso(db_session)

    resp = await client.post(
        f"/api/pruebas/resultado/{expediente.id}",
        json={"normalized_payload": _payload_gasolina()},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    assert (await _resultado_de(db_session, expediente)).equipo_id == analizador.id


async def test_resultado_sin_equipo_registrado_queda_sin_equipo(client, db_session):
    sesion = await _sesion_prueba(db_session)
    await _cargar_limites_gasolina(db_session, MetodoPrueba.GAS_DYNAMIC)
    expediente = await _expediente_gasolina_en_proceso(db_session)

    resp = await client.post(
        f"/api/pruebas/resultado/{expediente.id}",
        json={"normalized_payload": _payload_gasolina()},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    assert (await _resultado_de(db_session, expediente)).equipo_id is None


async def test_resultado_rechaza_equipo_de_otra_estacion_o_de_otro_tipo(client, db_session):
    sesion = await _sesion_prueba(db_session)
    ajena = await _sesion_prueba(db_session, line_id=2)
    await _cargar_limites_gasolina(db_session, MetodoPrueba.GAS_DYNAMIC)
    de_otra_linea = await _equipo(db_session, ajena, "ANALIZADOR_GASES", "AG-20")
    opacimetro = await _equipo(db_session, sesion, "OPACIMETRO", "OP-20")
    expediente = await _expediente_gasolina_en_proceso(db_session)

    for equipo in (de_otra_linea, opacimetro):
        resp = await client.post(
            f"/api/pruebas/resultado/{expediente.id}",
            json={"normalized_payload": _payload_gasolina(), "equipo_id": str(equipo.id)},
            headers={"X-Session-Id": str(sesion.id)},
        )
        assert resp.status_code == 422

    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.PRUEBA_EN_PROCESO


async def test_resultado_obd_toma_el_escaner_de_la_estacion(client, db_session):
    sesion = await _sesion_prueba(db_session)
    escaner = await _equipo(db_session, sesion, "ESCANER_OBD", "OBD-1")
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.OBD_SOLICITADO
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/obd/resultado/{expediente.id}",
        json={"resultado": "APROBADO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    fila = (
        await db_session.execute(
            select(ResultadoObdSbd).where(ResultadoObdSbd.verificacion_id == expediente.id)
        )
    ).scalar_one()
    assert fila.equipo_id == escaner.id
