"""Lectura de parámetros de negocio configurables desde `cat_parametros_sistema`.

Regla de negocio #4 y convención de código: valores como obd_modelo_minimo
NUNCA deben quedar como constantes en el código; siempre se leen de BD."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalogos import CatParametroSistema

DEFAULTS = {
    "obd_modelo_minimo": "2006",
    "gasolina_prueba_default": "dinamica",
    "gasolina_permite_cambio_estatica": "true",
    # Valor corregido (2026-09-27): el default original ("sistema_externo")
    # quedó de antes de la revisión del Figma del 2026-08-24, que confirmó
    # que los folios son inventario LOCAL (bloqueador E del plan del
    # 2026-09-14) — folios_client.py/Folio ya implementan eso desde el
    # 2026-08-25. Esta clave no se lee en ningún flujo real (ver folios.py),
    # es solo informativa para el panel de Administración; se corrige aquí
    # para no mostrar un valor que contradice la arquitectura real.
    "folios_origen": "inventario_local",
    # Plantillas de sobreimpresión del cliente (2026-10-05): datos fijos que
    # las plantillas Word traían escritos a mano, más calibración de márgenes
    # contra el papel preimpreso. Ver app.services.certificado.
    "certificado_clave_centro": "CVV-06",
    "certificado_marca_equipo": "OBERTECH",
    "certificado_numero_equipo": "001",
    "certificado_imprime_folio": "false",
    "certificado_offset_x_mm": "0",
    "certificado_offset_y_mm": "0",
}

DESCRIPCIONES = {
    "obd_modelo_minimo": "Año-modelo mínimo (gasolina) a partir del cual aplica OBD/SBD.",
    "gasolina_prueba_default": "Tipo de prueba con el que arranca un vehículo a gasolina (dinamica/estatica).",
    "gasolina_permite_cambio_estatica": "Si el operador puede cambiar de dinámica a estática con motivo (true/false).",
    "folios_origen": "Origen del inventario de folios (informativo; no se lee en el flujo real de folios.py).",
    "certificado_clave_centro": "Clave del centro que se imprime en el certificado (p. ej. CVV-06).",
    "certificado_marca_equipo": "Marca del equipo de medición que se imprime en el certificado.",
    "certificado_numero_equipo": "Número de equipo que se imprime en el certificado.",
    "certificado_imprime_folio": "Si el sistema sobreimprime el folio (false: el papel ya lo trae preimpreso).",
    "certificado_offset_x_mm": "Calibración horizontal de la sobreimpresión en mm (+ derecha, − izquierda).",
    "certificado_offset_y_mm": "Calibración vertical de la sobreimpresión en mm (+ abajo, − arriba).",
}


async def get_parametro(db: AsyncSession, clave: str) -> str:
    result = await db.execute(
        select(CatParametroSistema).where(CatParametroSistema.clave == clave)
    )
    parametro = result.scalar_one_or_none()
    if parametro is not None:
        return parametro.valor
    if clave in DEFAULTS:
        return DEFAULTS[clave]
    raise KeyError(f"Parámetro de sistema no encontrado: {clave}")


def validar_valor(clave: str, valor: str) -> str | None:
    """Devuelve un mensaje de error si `valor` no es válido para `clave`,
    o None si es válido. Solo valida las claves conocidas (ver DEFAULTS)."""

    if clave == "obd_modelo_minimo":
        try:
            numero = int(valor)
        except ValueError:
            return "obd_modelo_minimo debe ser un año numérico (ej. 2006)."
        if numero < 1980 or numero > 2100:
            return "obd_modelo_minimo debe ser un año-modelo razonable."
    elif clave == "gasolina_prueba_default":
        if valor not in ("dinamica", "estatica"):
            return "gasolina_prueba_default debe ser 'dinamica' o 'estatica'."
    elif clave in ("certificado_offset_x_mm", "certificado_offset_y_mm"):
        try:
            numero = float(valor)
        except ValueError:
            return f"{clave} debe ser un número en milímetros (ej. -1.5)."
        if abs(numero) > 20:
            return f"{clave} debe estar entre -20 y 20 mm."
    elif clave in ("certificado_clave_centro", "certificado_marca_equipo", "certificado_numero_equipo"):
        if not valor.strip() or len(valor) > 30:
            return f"{clave} no puede quedar vacío ni pasar de 30 caracteres."
    elif clave in ("gasolina_permite_cambio_estatica", "certificado_imprime_folio"):
        if valor not in ("true", "false"):
            return f"{clave} debe ser 'true' o 'false'."
    return None


async def obd_aplica(
    db: AsyncSession,
    *,
    inspeccion_aprobada: bool,
    tipo_vehiculo: str,
    combustible: str,
    modelo: int,
) -> bool:
    """Regla de negocio #4: OBD/SBD aplica solo si la inspección visual fue
    aprobada, el tipo de unidad es 'vehiculo', el combustible es gasolina y
    el modelo es >= obd_modelo_minimo (parámetro configurable)."""

    if not inspeccion_aprobada:
        return False
    if tipo_vehiculo.lower() != "vehiculo":
        return False
    if combustible.lower() != "gasolina":
        return False

    modelo_minimo = int(await get_parametro(db, "obd_modelo_minimo"))
    return modelo >= modelo_minimo
