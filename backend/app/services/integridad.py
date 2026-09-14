"""Hash de integridad de resultados de prueba (HU-102, subtarea 3, Etapa 12).

El expediente puede capturarse y probarse sin internet (ver
`app/services/sync.py`); el resultado de prueba viaja hacia el central
como un registro más de `sync_outbox`, potencialmente horas o días después
de haberse generado localmente. Este módulo calcula, una sola vez y al
momento de crear el `ResultadoPrueba`, un hash SHA-256 sobre los campos
técnicos que nunca deben cambiar después de guardados (valores medidos,
límites aplicados, resultado, equipo y quién/cuándo lo capturó). El central
puede recalcularlo con la misma función sobre el payload recibido y
comparar contra `hash_integridad` para detectar alteración en tránsito o
manipulación del registro local antes de sincronizar — no protege contra
un servidor local comprometido que recalcule el hash también, solo contra
corrupción/alteración accidental o en el transporte.

No incluye `created_at`/`updated_at` (los pone el propio ORM al insertar,
no son parte del resultado técnico) ni `id` como campo de negocio, aunque
sí se ata a un `id` concreto vía el propio nombre del campo — ver
`calcular_hash_resultado_prueba`.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any


def calcular_hash_resultado_prueba(
    *,
    resultado_id: uuid.UUID,
    verificacion_id: uuid.UUID,
    tipo_prueba: str,
    combustible: str,
    resultado: str | None,
    valores_medidos_json: dict[str, Any] | None,
    limites_aplicados_json: dict[str, Any] | None,
    equipo_id: uuid.UUID | None,
    linea_id: int,
    operador_id: uuid.UUID | None,
    started_at: str | None,
    finished_at: str | None,
) -> str:
    """Serialización canónica (claves ordenadas, sin espacios variables) +
    SHA-256. Los `datetime`/`UUID` deben llegar ya convertidos a `str`
    (`.isoformat()`/`str(...)`) por el llamador, igual que en
    `app.services.sync._serializar_verificacion`, para que el hash no
    dependa de cómo cada capa serializa esos tipos."""

    campos = {
        "resultado_id": str(resultado_id),
        "verificacion_id": str(verificacion_id),
        "tipo_prueba": tipo_prueba,
        "combustible": combustible,
        "resultado": resultado,
        "valores_medidos_json": valores_medidos_json,
        "limites_aplicados_json": limites_aplicados_json,
        "equipo_id": str(equipo_id) if equipo_id else None,
        "linea_id": linea_id,
        "operador_id": str(operador_id) if operador_id else None,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    canonico = json.dumps(campos, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()
