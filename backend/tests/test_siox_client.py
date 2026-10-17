import httpx

from app.services import siox_client
from app.services.siox_client import _normalizar, _parse_respuesta, consultar_placa

# Fragmentos reconstruidos a partir del HTML real devuelto por
# https://siox.finanzasoaxaca.gob.mx/pagoTenencia/busquedaVehiculo.htm
# (capturado por ingeniería inversa el 2026-08-03). Reproduce el bug de
# ids duplicados/mal etiquetados del sitio: id="labelVersion" se repite en
# LINEA, VERSIÓN y MOTOR, y id="labelLinea" en realidad guarda MARCA.
ENCONTRADO_HTML = """
<div id="formFinalizarTramite">
  <div class="form-group">
    <label class="col-md-12 control-label"><h5>DATOS DEL VEHÍCULO</h5></label>
  </div>
  <div class="col-md-12 form-group">
    <div class="col-md-6">
      <label class="col-md-4 control-label">NÚMERO DE SERIE:</label>
      <label class="col-md-8 control-label" id="labelNumeroSerie">3N1CN8AE1PL835483</label>
    </div>
    <div class="col-md-6">
      <label class="col-md-4 control-label">ESTATUS:</label>
      <label class="col-md-8 control-label" id="labelEstatus">ACTIVO</label>
    </div>
  </div>
  <div class="col-md-12 form-group">
    <div class="col-md-6">
      <label class="col-md-4 control-label">PLACAS:</label>
      <label class="col-md-8 control-label" id="labelPlacas">THJ389B</label>
    </div>
    <div class="col-md-6">
      <label class="col-md-4 control-label">MODELO:</label>
      <label class="col-md-8 control-label" id="labelModelo">2023</label>
    </div>
  </div>
  <div class="col-md-12 form-group">
    <div class="col-md-6">
      <label class="col-md-4 control-label">CLASIFICACIÓN:</label>
      <label class="col-md-8 control-label" id="labelClasificacion">AUTOMOVIL</label>
    </div>
    <div class="col-md-6">
      <label class="col-md-4 control-label">MARCA</label>
      <label class="col-md-8 control-label" id="labelLinea">"NISSAN MEXICANA, S.A. DE C.V."</label>
    </div>
  </div>
  <div class="col-md-12 form-group">
    <div class="col-md-6">
      <label class="col-md-4 control-label">LINEA</label>
      <label class="col-md-8 control-label" id="labelVersion">VERSA</label>
    </div>
    <div class="col-md-6">
      <label class="col-md-4 control-label">VERSIÓN:</label>
      <label class="col-md-8 control-label" id="labelVersion">SR CVT 1.6 LTS</label>
    </div>
  </div>
  <div class="col-md-12 form-group">
    <div class="col-md-6">
      <label class="col-md-4 control-label">MOTOR:</label>
      <label class="col-md-8 control-label" id="labelVersion">HR16729018V</label>
    </div>
  </div>
</div>
"""

NO_ENCONTRADO_HTML = """
<div id="formFinalizarTramite">
  <div class="form-group">
    <div class="col-md-12">
      <label class="control-label col-md-12 text-center">
        <h3>No existe un vehiculo con serie o placa ingresada</h3>
      </label>
    </div>
  </div>
</div>
"""


def test_parse_respuesta_extrae_campos_pese_a_ids_duplicados():
    datos = _parse_respuesta(ENCONTRADO_HTML)

    assert datos == {
        "niv": "3N1CN8AE1PL835483",
        "estatus": "ACTIVO",
        "placa": "THJ389B",
        "modelo": "2023",
        "tipo_vehiculo": "AUTOMOVIL",
        "marca": '"NISSAN MEXICANA, S.A. DE C.V."',
        "linea": "VERSA",
        "version": "SR CVT 1.6 LTS",
        "motor": "HR16729018V",
    }


def test_parse_respuesta_sin_datos_devuelve_none():
    assert _parse_respuesta(NO_ENCONTRADO_HTML) is None


def test_normalizar_convierte_modelo_a_entero():
    datos = _parse_respuesta(ENCONTRADO_HTML)

    normalizado = _normalizar(datos, placa_consultada="THJ389B")

    assert normalizado["modelo"] == 2023
    assert normalizado["placa"] == "THJ389B"
    assert normalizado["marca"] == '"NISSAN MEXICANA, S.A. DE C.V."'
    assert normalizado["linea"] == "VERSA"
    assert normalizado["version"] == "SR CVT 1.6 LTS"
    assert normalizado["motor"] == "HR16729018V"


def test_normalizar_con_modelo_ausente_no_falla():
    normalizado = _normalizar({}, placa_consultada="THJ389B")

    assert normalizado["modelo"] is None
    assert normalizado["placa"] == "THJ389B"


def _simular_siox(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(
        siox_client.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )


async def test_consultar_placa_pagina_inesperada_es_error_no_sin_datos(monkeypatch):
    """Un 200 que no es ni el bloque de datos ni el aviso de 'no existe'
    (mantenimiento, captcha, cambio de formato) no prueba que el vehículo no
    exista: se clasifica ERROR y se guarda el HTML como evidencia."""

    _simular_siox(
        monkeypatch,
        lambda req: httpx.Response(200, text="<html><body>Sitio en mantenimiento</body></html>"),
    )

    resultado = await consultar_placa("THJ389B")

    assert resultado.status == "ERROR"
    assert resultado.normalized is None
    assert "mantenimiento" in resultado.raw["html"]


async def test_consultar_placa_vehiculo_inexistente_sigue_siendo_sin_datos(monkeypatch):
    _simular_siox(monkeypatch, lambda req: httpx.Response(200, text=NO_ENCONTRADO_HTML))

    resultado = await consultar_placa("XXX000")

    assert resultado.status == "SIN_DATOS"
    assert resultado.normalized is None


async def test_consultar_placa_encontrado_es_exitosa(monkeypatch):
    _simular_siox(monkeypatch, lambda req: httpx.Response(200, text=ENCONTRADO_HTML))

    resultado = await consultar_placa("THJ389B")

    assert resultado.status == "EXITOSA"
    assert resultado.normalized["niv"] == "3N1CN8AE1PL835483"


async def test_consultar_placa_error_de_red_es_error(monkeypatch):
    def _handler(req):
        raise httpx.ConnectError("sin internet", request=req)

    _simular_siox(monkeypatch, _handler)

    resultado = await consultar_placa("THJ389B")

    assert resultado.status == "ERROR"
    assert resultado.raw is None
