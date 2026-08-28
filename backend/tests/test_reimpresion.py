"""Sección 3 del handoff (revisión Figma 2026-08-24): modelo completo de
reimpresión y cierre — folio dañado antes de imprimir, corrección de tipo
antes/después de imprimir, reimpresión por daño físico después de
imprimir. Ver CLAUDE.md, "Split de CERRADO..." y el PDF de la revisión
para el texto íntegro de las reglas."""

from sqlalchemy import select

from app.models.enums import EstadoFolio, EstadoVerificacion, ResultadoFinal, StationType
from app.models.folio import Folio
from app.models.print_attempt import PrintAttempt
from app.models.print_job import PrintJob
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
    client, sesion_supervisor, *, tipo_certificado, folio_inicio, folio_fin
):
    resp = await client.post(
        "/api/folios/lotes",
        params={
            "tipo_certificado": tipo_certificado,
            "folio_inicio": folio_inicio,
            "folio_fin": folio_fin,
        },
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 200
    return resp


async def _expediente_con_folio_asignado(
    client, db_session, sesion, sesion_supervisor, *, tipo_certificado="PARTICULAR", folio="OAX-000001"
):
    await _registrar_lote(
        client, sesion_supervisor, tipo_certificado=tipo_certificado, folio_inicio=folio, folio_fin=folio
    )
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    expediente.resultado_final = ResultadoFinal.APROBADO
    db_session.add(expediente)
    await db_session.commit()

    await client.post(
        f"/api/impresion/tipo-certificado/{expediente.id}",
        params={"tipo_certificado": tipo_certificado},
        headers={"X-Session-Id": str(sesion.id)},
    )
    await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": tipo_certificado},
        headers={"X-Session-Id": str(sesion.id)},
    )
    await db_session.refresh(expediente)
    return expediente


async def _imprimir(client, sesion, expediente):
    resp = await client.post(
        f"/api/impresion/imprimir/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )
    assert resp.status_code == 200
    assert resp.json()["estado_expediente"] == EstadoVerificacion.IMPRESO.value
    return resp


# --- Folio.estatus pasa a IMPRESO tras imprimir con éxito ------------------


async def test_imprimir_exitoso_marca_el_folio_como_impreso(client, db_session):
    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    expediente = await _expediente_con_folio_asignado(client, db_session, sesion, sesion_supervisor)

    await _imprimir(client, sesion, expediente)

    folio = (
        await db_session.execute(select(Folio).where(Folio.folio == "OAX-000001"))
    ).scalar_one()
    assert folio.estatus == EstadoFolio.IMPRESO


# --- Folio dañado antes de imprimir ----------------------------------------


async def test_marcar_folio_danado_asigna_siguiente_folio_disponible(client, db_session):
    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    expediente = await _expediente_con_folio_asignado(client, db_session, sesion, sesion_supervisor)
    assert expediente.folio_externo == "OAX-000001"
    # Se registra DESPUÉS del folio original — `orden` (Postgres IDENTITY)
    # es por inserción, así que si se registrara antes sería el primero en
    # asignarse y el escenario dejaría de probar el reemplazo.
    await _registrar_lote(
        client, sesion_supervisor, tipo_certificado="PARTICULAR",
        folio_inicio="OAX-000002", folio_fin="OAX-000002",
    )

    resp = await client.post(
        f"/api/impresion/folio/marcar-danado/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["folio_danado"] == "OAX-000001"
    assert resp.json()["folio_externo"] == "OAX-000002"

    await db_session.refresh(expediente)
    assert expediente.folio_externo == "OAX-000002"
    assert expediente.estado == EstadoVerificacion.FOLIO_ASIGNADO

    folio_viejo = (
        await db_session.execute(select(Folio).where(Folio.folio == "OAX-000001"))
    ).scalar_one()
    assert folio_viejo.estatus == EstadoFolio.DANADO
    assert folio_viejo.danado_at is not None
    assert folio_viejo.motivo_danado is None

    folio_nuevo = (
        await db_session.execute(select(Folio).where(Folio.folio == "OAX-000002"))
    ).scalar_one()
    assert folio_nuevo.estatus == EstadoFolio.ASIGNADO
    assert folio_viejo.reemplazado_por_folio_id == folio_nuevo.id


async def test_marcar_folio_danado_sin_reemplazo_deja_expediente_en_folio_error(client, db_session):
    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    expediente = await _expediente_con_folio_asignado(client, db_session, sesion, sesion_supervisor)

    resp = await client.post(
        f"/api/impresion/folio/marcar-danado/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409
    assert "Sin folio disponible" in resp.json()["detail"]

    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.FOLIO_ERROR

    folio_viejo = (
        await db_session.execute(select(Folio).where(Folio.folio == "OAX-000001"))
    ).scalar_one()
    assert folio_viejo.estatus == EstadoFolio.DANADO


async def test_marcar_folio_danado_fuera_de_folio_asignado_responde_409(client, db_session):
    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/impresion/folio/marcar-danado/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409


# --- Corrección de tipo ANTES de imprimir -----------------------------------


async def test_corregir_tipo_antes_de_imprimir_libera_folio_viejo_y_asigna_nuevo(client, db_session):
    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    await _registrar_lote(
        client, sesion_supervisor, tipo_certificado="INTENSIVO",
        folio_inicio="INT-000001", folio_fin="INT-000001",
    )
    expediente = await _expediente_con_folio_asignado(client, db_session, sesion, sesion_supervisor)
    assert expediente.folio_externo == "OAX-000001"

    resp = await client.post(
        f"/api/impresion/tipo-certificado/{expediente.id}",
        params={"tipo_certificado": "INTENSIVO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["certificado_tipo"] == "INTENSIVO"
    assert resp.json()["folio_externo"] == "INT-000001"

    await db_session.refresh(expediente)
    assert expediente.certificado_tipo == "INTENSIVO"
    assert expediente.folio_externo == "INT-000001"
    assert expediente.estado == EstadoVerificacion.FOLIO_ASIGNADO

    folio_liberado = (
        await db_session.execute(select(Folio).where(Folio.folio == "OAX-000001"))
    ).scalar_one()
    assert folio_liberado.estatus == EstadoFolio.DISPONIBLE
    assert folio_liberado.verificacion_id is None
    assert folio_liberado.danado_at is None


async def test_corregir_tipo_antes_de_imprimir_sin_folio_nuevo_no_pierde_el_viejo(client, db_session):
    """Si no hay folio disponible del tipo nuevo, la operación completa se
    aborta — el expediente conserva su tipo y folio originales."""

    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    expediente = await _expediente_con_folio_asignado(client, db_session, sesion, sesion_supervisor)

    resp = await client.post(
        f"/api/impresion/tipo-certificado/{expediente.id}",
        params={"tipo_certificado": "DOBLE_CERO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409

    await db_session.refresh(expediente)
    assert expediente.certificado_tipo == "PARTICULAR"
    assert expediente.folio_externo == "OAX-000001"

    folio_original = (
        await db_session.execute(select(Folio).where(Folio.folio == "OAX-000001"))
    ).scalar_one()
    assert folio_original.estatus == EstadoFolio.ASIGNADO


async def test_corregir_tipo_una_vez_impreso_responde_409_en_endpoint_de_antes(client, db_session):
    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    expediente = await _expediente_con_folio_asignado(client, db_session, sesion, sesion_supervisor)
    await _imprimir(client, sesion, expediente)

    resp = await client.post(
        f"/api/impresion/tipo-certificado/{expediente.id}",
        params={"tipo_certificado": "INTENSIVO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409


# --- Reimpresión por daño físico (después de imprimir) ----------------------


async def test_reimprimir_por_dano_requiere_supervisor(client, db_session):
    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    expediente = await _expediente_con_folio_asignado(client, db_session, sesion, sesion_supervisor)
    await _imprimir(client, sesion, expediente)

    resp = await client.post(
        f"/api/impresion/folio/reimprimir-por-dano/{expediente.id}",
        json={"motivo": "Certificado manchado al salir de la impresora"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_reimprimir_por_dano_sin_motivo_responde_422(client, db_session):
    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    expediente = await _expediente_con_folio_asignado(client, db_session, sesion, sesion_supervisor)
    await _imprimir(client, sesion, expediente)

    resp = await client.post(
        f"/api/impresion/folio/reimprimir-por-dano/{expediente.id}",
        json={"motivo": ""},
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 422


async def test_reimprimir_por_dano_en_estado_no_impreso_responde_409(client, db_session):
    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    expediente = await _expediente_con_folio_asignado(client, db_session, sesion, sesion_supervisor)

    resp = await client.post(
        f"/api/impresion/folio/reimprimir-por-dano/{expediente.id}",
        json={"motivo": "Dañado"},
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 409


async def test_reimprimir_por_dano_exitoso_invalida_folio_viejo_y_conserva_hora_salida(
    client, db_session
):
    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    expediente = await _expediente_con_folio_asignado(client, db_session, sesion, sesion_supervisor)
    await _registrar_lote(
        client, sesion_supervisor, tipo_certificado="PARTICULAR",
        folio_inicio="OAX-000002", folio_fin="OAX-000002",
    )
    await _imprimir(client, sesion, expediente)

    print_job_antes = (
        await db_session.execute(select(PrintJob).where(PrintJob.verificacion_id == expediente.id))
    ).scalar_one()
    hora_salida = print_job_antes.created_at

    resp = await client.post(
        f"/api/impresion/folio/reimprimir-por-dano/{expediente.id}",
        json={"motivo": "Certificado manchado al salir de la impresora"},
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["impreso"] is True
    assert resp.json()["folio"] == "OAX-000002"
    # El estado del expediente no cambia: la reimpresión no es una
    # transición de la máquina de estados.
    assert resp.json()["estado_expediente"] == EstadoVerificacion.IMPRESO.value

    await db_session.refresh(expediente)
    assert expediente.folio_externo == "OAX-000002"
    assert expediente.estado == EstadoVerificacion.IMPRESO

    folio_danado = (
        await db_session.execute(select(Folio).where(Folio.folio == "OAX-000001"))
    ).scalar_one()
    assert folio_danado.estatus == EstadoFolio.DANADO
    assert folio_danado.motivo_danado == "Certificado manchado al salir de la impresora"

    folio_nuevo = (
        await db_session.execute(select(Folio).where(Folio.folio == "OAX-000002"))
    ).scalar_one()
    assert folio_nuevo.estatus == EstadoFolio.IMPRESO
    assert folio_danado.reemplazado_por_folio_id == folio_nuevo.id

    print_job_despues = (
        await db_session.execute(select(PrintJob).where(PrintJob.verificacion_id == expediente.id))
    ).scalar_one()
    assert print_job_despues.id == print_job_antes.id
    assert print_job_despues.created_at == hora_salida
    assert print_job_despues.intentos == 2

    intentos = (
        await db_session.execute(
            select(PrintAttempt).where(PrintAttempt.print_job_id == print_job_antes.id)
        )
    ).scalars().all()
    assert len(intentos) == 2


async def test_reimprimir_por_dano_funciona_con_expediente_ya_cerrado(client, db_session):
    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    expediente = await _expediente_con_folio_asignado(client, db_session, sesion, sesion_supervisor)
    await _registrar_lote(
        client, sesion_supervisor, tipo_certificado="PARTICULAR",
        folio_inicio="OAX-000002", folio_fin="OAX-000002",
    )
    await _imprimir(client, sesion, expediente)

    resp_cerrar = await client.post(
        f"/api/impresion/cerrar/{expediente.id}", headers={"X-Session-Id": str(sesion.id)}
    )
    assert resp_cerrar.json()["estado_expediente"] == EstadoVerificacion.CERRADO_APROBADO.value

    resp = await client.post(
        f"/api/impresion/folio/reimprimir-por-dano/{expediente.id}",
        json={"motivo": "Se rompió al entregarlo"},
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["estado_expediente"] == EstadoVerificacion.CERRADO_APROBADO.value

    await db_session.refresh(expediente)
    assert expediente.estado == EstadoVerificacion.CERRADO_APROBADO
    assert expediente.folio_externo == "OAX-000002"


# --- Corrección de tipo DESPUÉS de imprimir ---------------------------------


async def test_corregir_tipo_post_impresion_requiere_supervisor(client, db_session):
    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    expediente = await _expediente_con_folio_asignado(client, db_session, sesion, sesion_supervisor)
    await _imprimir(client, sesion, expediente)

    resp = await client.post(
        f"/api/impresion/tipo-certificado-post-impresion/{expediente.id}",
        params={"nuevo_tipo": "INTENSIVO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 403


async def test_corregir_tipo_post_impresion_invalida_folio_viejo_y_reimprime(client, db_session):
    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    await _registrar_lote(
        client, sesion_supervisor, tipo_certificado="INTENSIVO",
        folio_inicio="INT-000001", folio_fin="INT-000001",
    )
    expediente = await _expediente_con_folio_asignado(client, db_session, sesion, sesion_supervisor)
    await _imprimir(client, sesion, expediente)

    print_job_antes = (
        await db_session.execute(select(PrintJob).where(PrintJob.verificacion_id == expediente.id))
    ).scalar_one()
    hora_salida = print_job_antes.created_at

    resp = await client.post(
        f"/api/impresion/tipo-certificado-post-impresion/{expediente.id}",
        params={"nuevo_tipo": "INTENSIVO"},
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["certificado_tipo"] == "INTENSIVO"
    assert resp.json()["folio"] == "INT-000001"
    assert resp.json()["impreso"] is True

    await db_session.refresh(expediente)
    assert expediente.certificado_tipo == "INTENSIVO"
    assert expediente.folio_externo == "INT-000001"

    folio_invalidado = (
        await db_session.execute(select(Folio).where(Folio.folio == "OAX-000001"))
    ).scalar_one()
    assert folio_invalidado.estatus == EstadoFolio.INVALIDADO
    assert folio_invalidado.invalidado_at is not None

    folio_nuevo = (
        await db_session.execute(select(Folio).where(Folio.folio == "INT-000001"))
    ).scalar_one()
    assert folio_nuevo.estatus == EstadoFolio.IMPRESO

    print_job_despues = (
        await db_session.execute(select(PrintJob).where(PrintJob.verificacion_id == expediente.id))
    ).scalar_one()
    assert print_job_despues.created_at == hora_salida


async def test_corregir_tipo_post_impresion_rechazo_no_admite_correccion(client, db_session):
    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    await _registrar_lote(
        client, sesion_supervisor, tipo_certificado="RECHAZO",
        folio_inicio="RCH-000001", folio_fin="RCH-000001",
    )
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO
    )
    expediente.resultado_final = ResultadoFinal.RECHAZADO
    db_session.add(expediente)
    await db_session.commit()

    await client.post(
        f"/api/impresion/tipo-certificado/{expediente.id}",
        headers={"X-Session-Id": str(sesion.id)},
    )
    await client.post(
        f"/api/folios/solicitar/{expediente.id}",
        params={"tipo_certificado": "RECHAZO"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    await _imprimir(client, sesion, expediente)

    resp = await client.post(
        f"/api/impresion/tipo-certificado-post-impresion/{expediente.id}",
        params={"nuevo_tipo": "PARTICULAR"},
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 409


# --- Regresión: FOLIO_ERROR desaparecía de la cola de Impresión -----------


async def test_cola_impresion_incluye_folio_error(client, db_session):
    """Reportado por Sebastian durante la QA visual de ImpresionView.vue:
    `cola_impresion` no listaba FOLIO_ERROR, así que un expediente que cae
    ahí (sistema de folios agotado/con error) desaparecía de la cola para
    siempre — sin forma de reabrirlo desde la UI para reintentar, aunque
    `/folios/solicitar` (ESTADOS_SOLICITABLES) ya sabe reintentar desde ese
    estado y el frontend ya tiene el botón "Reintentar" listo."""

    sesion = await _sesion_impresion(db_session)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=EstadoVerificacion.FOLIO_ERROR
    )
    await db_session.commit()

    resp = await client.get(
        "/api/impresion/cola", headers={"X-Session-Id": str(sesion.id)}
    )
    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    assert str(expediente.id) in ids


async def test_corregir_tipo_post_impresion_mismo_tipo_responde_409(client, db_session):
    sesion = await _sesion_impresion(db_session)
    sesion_supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    expediente = await _expediente_con_folio_asignado(client, db_session, sesion, sesion_supervisor)
    await _imprimir(client, sesion, expediente)

    resp = await client.post(
        f"/api/impresion/tipo-certificado-post-impresion/{expediente.id}",
        params={"nuevo_tipo": "PARTICULAR"},
        headers={"X-Session-Id": str(sesion_supervisor.id)},
    )
    assert resp.status_code == 409
