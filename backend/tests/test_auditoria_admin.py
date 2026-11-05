"""X7-c (auditoría de seguridad 2026-11-04): las acciones administrativas
dejan rastro en `event_log` con `modulo="administracion"` y sin expediente,
y aparecen en la pestaña Auditoría del Supervisor acotadas a su centro."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.enums import StationType
from app.models.event_log import EventLog
from app.models.sync_outbox import SyncOutbox
from app.services.sync import _serializar_event_log
from tests.conftest import crear_estacion, crear_expediente, crear_sesion_supervisor, crear_usuario


async def _eventos_admin(db_session, evento: str | None = None) -> list[EventLog]:
    q = select(EventLog).where(EventLog.modulo == "administracion")
    if evento:
        q = q.where(EventLog.evento == evento)
    return list((await db_session.execute(q.order_by(EventLog.created_at))).scalars().all())


async def _auditoria(client, sesion, **params):
    resp = await client.get(
        "/api/supervision/auditoria", headers={"X-Session-Id": str(sesion.id)}, params=params
    )
    assert resp.status_code == 200
    return resp.json()


async def test_alta_de_usuario_queda_en_auditoria_sin_expediente(client, db_session):
    sup = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    await db_session.commit()

    resp = await client.post(
        "/api/usuarios",
        headers={"X-Session-Id": str(sup.id)},
        json={
            "username": "auditado",
            "password": "clave-segura-1",
            "nombre_completo": "Auditado",
            "clave_tecnico": "T9",
        },
    )
    assert resp.status_code == 201

    [ev] = await _eventos_admin(db_session, "usuario_creado")
    assert ev.verificacion_id is None
    assert ev.centro_id == "OAX-01"
    assert ev.usuario_id == sup.user_id
    assert ev.detalle_json["username"] == "auditado"
    assert ev.detalle_json["clave_tecnico"] == "T9"
    assert "password" not in ev.detalle_json

    body = await _auditoria(client, sup, modulo="administracion")
    fila = next(i for i in body["items"] if i["evento"] == "usuario_creado")
    assert fila["placa"] is None and fila["verificacion_id"] is None
    assert fila["usuario_nombre"] is not None


async def test_restablecer_password_registra_el_hecho_pero_nunca_la_contrasena(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    usuario = await crear_usuario(db_session, username="olvidadizo")
    await db_session.commit()

    resp = await client.patch(
        f"/api/usuarios/{usuario.id}",
        headers={"X-Session-Id": str(sup.id)},
        json={"password": "Nueva-clave-77"},
    )
    assert resp.status_code == 200

    [ev] = await _eventos_admin(db_session, "usuario_password_restablecida")
    texto = str(ev.detalle_json)
    assert "Nueva-clave-77" not in texto and "password_hash" not in texto
    # Solo cambió la contraseña: no debe aparecer un "usuario_editado" vacío
    assert await _eventos_admin(db_session, "usuario_editado") == []


async def test_desactivar_y_reactivar_usuario_quedan_registrados(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    usuario = await crear_usuario(db_session, username="vaiven")
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}

    await client.patch(f"/api/usuarios/{usuario.id}", headers=h, json={"is_active": False})
    await client.patch(f"/api/usuarios/{usuario.id}", headers=h, json={"is_active": True})

    eventos = [e.evento for e in await _eventos_admin(db_session)]
    assert eventos == ["usuario_desactivado", "usuario_activado"]


async def test_ciclo_de_permiso_otorgar_modificar_revocar(client, db_session):
    sup = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    usuario = await crear_usuario(db_session, username="permisionado")
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}

    resp = await client.post(
        "/api/permisos",
        headers=h,
        json={"user_id": str(usuario.id), "station_type": "captura", "center_id": "OAX-01", "line_id": 1},
    )
    assert resp.status_code == 201
    permiso_id = resp.json()["id"]

    await client.patch(f"/api/permisos/{permiso_id}", headers=h, json={"can_supervise": True})
    # PATCH sin cambios reales no ensucia la bitácora
    await client.patch(f"/api/permisos/{permiso_id}", headers=h, json={"can_supervise": True})
    assert (await client.delete(f"/api/permisos/{permiso_id}", headers=h)).status_code == 204

    eventos = await _eventos_admin(db_session)
    assert [e.evento for e in eventos] == ["permiso_otorgado", "permiso_modificado", "permiso_revocado"]
    assert eventos[1].detalle_json["cambios"] == {"can_supervise": {"antes": False, "despues": True}}
    assert eventos[2].detalle_json["usuario_afectado_id"] == str(usuario.id)


async def test_cambio_de_parametro_guarda_antes_y_despues(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.patch(
        "/api/parametros/obd_modelo_minimo", headers={"X-Session-Id": str(sup.id)}, json={"valor": "2010"}
    )
    assert resp.status_code == 200

    [ev] = await _eventos_admin(db_session, "parametro_modificado")
    assert ev.detalle_json["clave"] == "obd_modelo_minimo"
    assert ev.detalle_json["despues"] == "2010"
    assert ev.detalle_json["antes"] is not None


async def test_parametro_invalido_no_deja_evento(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.patch(
        "/api/parametros/obd_modelo_minimo", headers={"X-Session-Id": str(sup.id)}, json={"valor": "x"}
    )
    assert resp.status_code == 422
    assert await _eventos_admin(db_session) == []


async def test_alta_y_edicion_de_equipo_quedan_registradas(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    prueba = await crear_estacion(db_session, station_type=StationType.PRUEBA, center_id="OAX-01", line_id=1)
    await db_session.commit()
    h = {"X-Session-Id": str(sup.id)}

    resp = await client.post(
        "/api/equipos",
        headers=h,
        json={"workstation_id": str(prueba.id), "tipo": "ANALIZADOR_GASES", "numero_serie": "AUD-001"},
    )
    assert resp.status_code == 201
    await client.patch(f"/api/equipos/{resp.json()['id']}", headers=h, json={"marca": "Nueva"})

    eventos = await _eventos_admin(db_session)
    assert [e.evento for e in eventos] == ["equipo_registrado", "equipo_modificado"]
    assert eventos[1].detalle_json["cambios"]["marca"]["despues"] == "Nueva"


async def test_lote_de_folios_queda_registrado(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()

    resp = await client.post(
        "/api/folios/lotes",
        params={"tipo_certificado": "PARTICULAR", "folio_inicio": "OAX-000501", "folio_fin": "OAX-000505"},
        headers={"X-Session-Id": str(sup.id)},
    )
    assert resp.status_code == 200

    [ev] = await _eventos_admin(db_session, "lote_folios_registrado")
    assert ev.detalle_json["cantidad"] == 5
    assert ev.detalle_json["tipo_certificado"] == "PARTICULAR"


async def test_auditoria_no_muestra_eventos_administrativos_de_otro_centro(client, db_session):
    sup_oax = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    sup_otro = await crear_sesion_supervisor(db_session, center_id="OAX-02")
    await db_session.commit()

    await client.patch(
        "/api/parametros/obd_modelo_minimo", headers={"X-Session-Id": str(sup_otro.id)}, json={"valor": "2011"}
    )

    body = await _auditoria(client, sup_oax, modulo="administracion")
    assert body["total"] == 0
    body = await _auditoria(client, sup_otro, modulo="administracion")
    assert body["total"] == 1


async def test_auditoria_sigue_mostrando_eventos_de_expediente_junto_a_los_admin(client, db_session):
    sup = await crear_sesion_supervisor(db_session, center_id="OAX-01")
    exp = await crear_expediente(db_session, linea_id=1, centro_id="OAX-01", placa="AUD123")
    db_session.add(EventLog(verificacion_id=exp.id, evento="creado", modulo="captura"))
    await db_session.commit()

    await client.patch(
        "/api/parametros/obd_modelo_minimo", headers={"X-Session-Id": str(sup.id)}, json={"valor": "2012"}
    )

    body = await _auditoria(client, sup)
    modulos = {i["modulo"] for i in body["items"]}
    assert {"captura", "administracion"} <= modulos
    # El filtro por placa solo puede traer eventos de expediente
    body = await _auditoria(client, sup, placa="AUD123")
    assert body["total"] >= 1 and all(i["placa"] == "AUD123" for i in body["items"])


async def test_bd_rechaza_evento_operativo_sin_expediente(db_session):
    db_session.add(EventLog(verificacion_id=None, evento="huerfano", modulo="captura"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_eventos_admin_no_se_encolan_y_el_serializador_no_manda_none_como_texto(client, db_session):
    sup = await crear_sesion_supervisor(db_session)
    await db_session.commit()
    antes = len((await db_session.execute(select(SyncOutbox))).scalars().all())

    await client.post(
        "/api/usuarios",
        headers={"X-Session-Id": str(sup.id)},
        json={"username": "sin.sync", "password": "clave-segura-1", "nombre_completo": "X"},
    )

    despues = len((await db_session.execute(select(SyncOutbox))).scalars().all())
    assert despues == antes

    [ev] = await _eventos_admin(db_session, "usuario_creado")
    payload = _serializar_event_log(ev)
    assert payload["verificacion_id"] is None
    assert payload["centro_id"] == ev.centro_id
