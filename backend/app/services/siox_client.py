"""Cliente SIOX (consulta pública de placa en pagoTenencia).

PENDIENTE (ver prioridades del proyecto): falta capturar el request real
con DevTools (Network -> XHR) contra
https://siox.finanzasoaxaca.gob.mx/pagoTenencia
para saber si expone JSON (cliente httpx) o requiere render JS / captcha
(Playwright). Hasta entonces esta función devuelve SIN_DATOS para que el
resto del flujo (captura manual asistida) sea probable end-to-end sin
bloquear el desarrollo de Captura/Prueba/Impresión.
"""


class SioxConsultaResultado:
    def __init__(self, status: str, raw: dict | None, normalized: dict | None):
        self.status = status  # "EXITOSA" | "SIN_DATOS" | "ERROR"
        self.raw = raw
        self.normalized = normalized


async def consultar_placa(placa: str) -> SioxConsultaResultado:
    return SioxConsultaResultado(status="SIN_DATOS", raw=None, normalized=None)
