#!/usr/bin/env bash
# ==============================================================================
# Script de Restauración de Base de Datos PostgreSQL (D4)
# Sistema de Verificación Vehicular Oaxaca
# ==============================================================================
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-verificacion-oaxaca-db-1}"
POSTGRES_USER="${POSTGRES_USER:-verificacion}"
POSTGRES_DB="${POSTGRES_DB:-verificacion}"

if [ $# -lt 1 ]; then
    echo "Uso: $0 <ruta_al_archivo_dump>" >&2
    echo "Ejemplo: $0 /var/backups/verificacion/verificacion_verificacion_20261022_120000.dump" >&2
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "[ERROR] El archivo de respaldo '${BACKUP_FILE}' no existe." >&2
    exit 1
fi

if [ ! -s "${BACKUP_FILE}" ]; then
    echo "[ERROR] El archivo de respaldo '${BACKUP_FILE}' está vacío." >&2
    exit 1
fi

echo "[$(date -Iseconds)] Iniciando restauración de PostgreSQL..."
echo "  Archivo: ${BACKUP_FILE}"
echo "  Contenedor: ${CONTAINER_NAME}"
echo "  Base de datos destino: ${POSTGRES_DB}"

# Verificar si el contenedor está en ejecución
if ! docker ps --format '{{.Names}}' | grep -Eq "^${CONTAINER_NAME}\$"; then
    echo "[ERROR] El contenedor '${CONTAINER_NAME}' no está en ejecución." >&2
    exit 1
fi

# Restauración con pg_restore (limpia objetos existentes antes de restaurar)
docker exec -i "${CONTAINER_NAME}" pg_restore \
    -U "${POSTGRES_USER}" \
    -d "${POSTGRES_DB}" \
    --clean \
    --if-exists < "${BACKUP_FILE}"

echo "[OK] Restauración completada exitosamente desde ${BACKUP_FILE}."
