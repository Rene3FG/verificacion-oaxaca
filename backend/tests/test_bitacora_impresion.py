"""HU-093: la bitácora del expediente registra solicitud de folio, error de
folio, asignación, vista previa, impresión fallida, reintento, impresión y
cierre — con usuario y estados de cada paso (HU-027)."""

from sqlalchemy import select

from app.models.enums import EstadoVerificacion, ResultadoFinal, StationType
from app.models.event_log import EventLog
from tests.conftest import crear_expediente, crear_sesion_supervisor
from tests.test_impresion import _sesion_impresion


async def test_bitacora_de_impresion_registra_todo_el_ciclo(client, db_session, monkeypatch):
    sesion = await _sesion_impresion(db_session)
    supervisor = await crear_sesion_supervisor(db_session, station_type=StationType.IMPRESION)
    expediente = await crear_expediente(db_session, linea_id=1, estado=EstadoVerificacion.PENDIENTE_IMPRESION)
    expediente.resultado_final = ResultadoFinal.APROBADO
    await db_session.commit()
    h = {"X-Session-Id": str(sesion.id)}
    url = lambda accion: f"/api/impresion/{accion}/{expediente.id}"  # noqa: E731

    resp = await client.post(
        url("tipo-certificado"),
        params={"tipo_certificado": "PARTICULAR", "tipo_verificacion": "ORDINARIA"},
        headers=h,
    )
    assert resp.status_code == 200, resp.text

    # Sin inventario: folio_error, reintentable.
    solicitar = f"/api/folios/solicitar/{expediente.id}?tipo_certificado=PARTICULAR"
    assert (await client.post(solicitar, headers=h)).status_code == 409
    lote = await client.post(
        "/api/folios/lotes",
        params={"tipo_certificado": "PARTICULAR", "folio_inicio": "B93-000001", "folio_fin": "B93-000002"},
        headers={"X-Session-Id": str(supervisor.id)},
    )
    assert lote.status_code == 200
    assert (await client.post(solicitar, headers=h)).status_code == 200

    assert (await client.get(url("vista-previa"), headers=h)).status_code == 200

    resultados = iter([False, True])

    async def _impresora(pdf_bytes: bytes) -> bool:
        return next(resultados)

    monkeypatch.setattr("app.api.routers.impresion.imprimir_en_impresora", _impresora)
    assert (await client.post(url("imprimir"), headers=h)).json()["estado_expediente"] == "IMPRESION_FALLIDA"
    resp = await client.post(url("imprimir"), headers={"X-Session-Id": str(supervisor.id)})
    assert resp.json()["estado_expediente"] == "IMPRESO"
    assert (await client.post(url("cerrar"), headers=h)).status_code == 200

    eventos = (
        await db_session.execute(select(EventLog).where(EventLog.verificacion_id == expediente.id))
    ).scalars().all()
    nombres = {e.evento for e in eventos}
    for esperado in (
        "folio_solicitado",
        "folio_error",
        "folio_asignado",
        "vista_previa_generada",
        "impresion_fallida",
        "reintento_impresion_sin_nuevo_folio",
        "certificado_impreso",
        "expediente_cerrado",
    ):
        assert esperado in nombres, esperado

    # HU-027: cada transición guarda estados y usuario.
    cierre = next(e for e in eventos if e.evento == "expediente_cerrado")
    assert cierre.estado_anterior == EstadoVerificacion.IMPRESO
    assert cierre.estado_nuevo == EstadoVerificacion.CERRADO_APROBADO
    assert cierre.usuario_id == sesion.user_id
    reintento = next(e for e in eventos if e.evento == "reintento_impresion_sin_nuevo_folio")
    assert reintento.usuario_id == supervisor.user_id
