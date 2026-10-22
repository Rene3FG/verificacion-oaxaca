#!/usr/bin/env bash
# ==============================================================================
# Script de Respaldo Automatizado de Base de Datos PostgreSQL (D4)
# Sistema de Verificación Vehicular Oaxaca
# ==============================================================================
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-verificacion-oaxaca-db-1}"
POSTGRES_USER="${POSTGRES_USER:-verificacion}"
POSTGRES_DB="${POSTGRES_DB:-verificacion}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/verificacion}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/verificacion_${POSTGRES_DB}_${TIMESTAMP}.dump"

echo "[$(date -Iseconds)] Iniciando respaldo de PostgreSQL..."
echo "  Contenedor: ${CONTAINER_NAME}"
echo "  Base de datos: ${POSTGRES_DB}"
echo "  Directorio de destino: ${BACKUP_DIR}"

# Crear directorio si no existe
mkdir -p "${BACKUP_DIR}"

# Verificar si el contenedor está en ejecución
if ! docker ps --format '{{.Names}}' | grep -Eq "^${CONTAINER_NAME}\$"; then
    echo "[ERROR] El contenedor '${CONTAINER_NAME}' no está en ejecución." >&2
    exit 1
fi

# Ejecutar pg_dump en formato custom (comprimido, apto para pg_restore)
docker exec "${CONTAINER_NAME}" pg_dump -U "${POSTGRES_USER}" -F c "${POSTGRES_DB}" > "${BACKUP_FILE}"

# Verificar integridad y tamaño del archivo generado
if [ -s "${BACKUP_FILE}" ]; then
    FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "[OK] Respaldo generado exitosamente: ${BACKUP_FILE} (${FILE_SIZE})"
else
    echo "[ERROR] El archivo de respaldo se encuentra vacío o no se generó correctamente." >&2
    rm -f "${BACKUP_FILE}"
    exit 1
fi

# Rotación de respaldos antiguos
echo "  Purgando respaldos con más de ${RETENTION_DAYS} días de antigüedad..."
find "${BACKUP_DIR}" -type f -name "verificacion_${POSTGRES_DB}_*.dump" -mtime +"${RETENTION_DAYS}" -exec rm -v {} \;

echo "[$(date -Iseconds)] Proceso de respaldo completado satisfactoriamente."
