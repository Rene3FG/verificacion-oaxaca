"""HU-072 a HU-079: la impresora física no tiene integración definida
todavía. Stub monkeypatcheable en pruebas, mismo patrón que
`app.services.siox_client.consultar_placa` para simular éxito/fallo."""


async def imprimir(pdf_bytes: bytes) -> bool:
    return True
