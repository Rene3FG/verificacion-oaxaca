#!/usr/bin/env bash
# Restaura un respaldo hecho con respaldo.sh. DESTRUYE los datos actuales.
#   scripts/restaurar.sh respaldos/verificacion_AAAAMMDD_HHMMSS.sql.gz
set -euo pipefail

ARCHIVO="${1:?Uso: scripts/restaurar.sh archivo.sql.gz}"
[ -f "$ARCHIVO" ] || { echo "No existe: $ARCHIVO" >&2; exit 1; }
COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env.prod)

read -r -p "Esto BORRA la base actual y la reemplaza por $ARCHIVO. Escribe SI para continuar: " R
[ "$R" = "SI" ] || { echo "Cancelado."; exit 1; }

"${COMPOSE[@]}" stop backend
"${COMPOSE[@]}" exec -T db sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE)" -c "CREATE DATABASE \"$POSTGRES_DB\""'
gzip -dc "$ARCHIVO" | "${COMPOSE[@]}" exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
"${COMPOSE[@]}" start backend
echo "Restauración completa."
