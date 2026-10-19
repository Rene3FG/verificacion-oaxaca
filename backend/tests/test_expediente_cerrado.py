"""HU-096: un expediente cerrado (o cancelado) no admite cambios en datos,
inspección visual, OBD/SBD, prueba ni folio. Cada endpoint valida su propio
estado de origen; esta prueba los recorre todos con un expediente cerrado
para que una guardia faltante no pase desapercibida."""

import pytest

from app.models.enums import EstadoVerificacion, StationType
from tests.conftest import (
    crear_estacion,
    crear_expediente,
    crear_sesion_activa,
    crear_sesion_supervisor,
)

ESTADOS_CERRADOS = [
    EstadoVerificacion.CERRADO_APROBADO,
    EstadoVerificacion.CERRADO_RECHAZADO,
    EstadoVerificacion.CANCELADO,
]

# (estación, método, ruta, cuerpo)
OPERACIONES = [
    (StationType.CAPTURA, "patch", "/api/expedientes/{id}/vehiculo", {"marca": "OTRA"}),
    (StationType.PRUEBA, "patch", "/api/expedientes/{id}/vehiculo", {"marca": "OTRA"}),
    (StationType.CAPTURA, "patch", "/api/expedientes/{id}/datos-certificado", {"folio_multa": "M-1"}),
    (StationType.CAPTURA, "post", "/api/expedientes/{id}/normalizar", None),
    (StationType.CAPTURA, "post", "/api/siox/consultar/{id}", None),
    (StationType.CAPTURA, "post", "/api/siox/captura-manual/{id}", {}),
    (StationType.PRUEBA, "post", "/api/inspeccion/{id}", {"checklist": {}}),
    (StationType.PRUEBA, "post", "/api/obd/evaluar/{id}", None),
    (StationType.PRUEBA, "post", "/api/obd/solicitar/{id}", None),
    (StationType.PRUEBA, "post", "/api/obd/resultado/{id}", {"resultado": "APROBADO"}),
    (StationType.PRUEBA, "post", "/api/pruebas/configurar/{id}?tipo_prueba=DINAMICA", None),
    (StationType.PRUEBA, "post", "/api/pruebas/iniciar/{id}", None),
    (StationType.PRUEBA, "post", "/api/pruebas/interrumpir/{id}", {"causa": "CANCELADA", "motivo": "x"}),
    (StationType.PRUEBA, "post", "/api/pruebas/resultado/{id}", {"normalized_payload": {}}),
    (StationType.IMPRESION, "post", "/api/impresion/tipo-certificado/{id}?tipo_certificado=PARTICULAR", None),
    (StationType.IMPRESION, "post", "/api/impresion/imprimir/{id}", None),
    (StationType.IMPRESION, "post", "/api/impresion/folio/marcar-danado/{id}", None),
    (StationType.IMPRESION, "post", "/api/impresion/cerrar/{id}", None),
    (StationType.IMPRESION, "post", "/api/folios/solicitar/{id}?tipo_certificado=DOBLE_CERO", None),
]


@pytest.mark.parametrize("estado", ESTADOS_CERRADOS)
@pytest.mark.parametrize("station_type,metodo,ruta,cuerpo", OPERACIONES)
async def test_expediente_cerrado_no_admite_cambios(
    client, db_session, estado, station_type, metodo, ruta, cuerpo
):
    estacion = await crear_estacion(db_session, station_type=station_type, line_id=1)
    sesion = await crear_sesion_activa(db_session, estacion=estacion)
    expediente = await crear_expediente(
        db_session, linea_id=1, estado=estado, combustible_validado="GASOLINA"
    )
    expediente.certificado_tipo = "PARTICULAR"
    await db_session.commit()

    kwargs = {"headers": {"X-Session-Id": str(sesion.id)}}
    if cuerpo is not None:
        kwargs["json"] = cuerpo
    resp = await getattr(client, metodo)(ruta.format(id=expediente.id), **kwargs)

    assert resp.status_code == 409, (ruta, resp.status_code, resp.text)
    await db_session.refresh(expediente)
    assert expediente.estado == estado


@pytest.mark.parametrize("estado", ESTADOS_CERRADOS)
async def test_expediente_cerrado_no_se_reasigna_de_linea(client, db_session, estado):
    sesion = await crear_sesion_supervisor(db_session)
    expediente = await crear_expediente(db_session, linea_id=1, estado=estado)
    await db_session.commit()

    resp = await client.post(
        f"/api/expedientes/{expediente.id}/reasignar-linea",
        json={"nueva_linea_id": 2, "motivo": "prueba"},
        headers={"X-Session-Id": str(sesion.id)},
    )
    assert resp.status_code == 409
