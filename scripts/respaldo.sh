#!/usr/bin/env bash
# Respaldo de PostgreSQL del stack de producción (D4).
#   scripts/respaldo.sh [directorio]      (default: ./respaldos)
# Deja un dump comprimido con fecha y conserva los últimos RETENCION (default 14).
# Programar con cron, p. ej. diario 02:00:
#   0 2 * * * cd /ruta/verificacion-oaxaca && scripts/respaldo.sh /var/respaldos/verificacion
set -euo pipefail

DESTINO="${1:-./respaldos}"
RETENCION="${RETENCION:-14}"
COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env.prod)

mkdir -p "$DESTINO"
ARCHIVO="$DESTINO/verificacion_$(date +%Y%m%d_%H%M%S).sql.gz"

"${COMPOSE[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' | gzip > "$ARCHIVO"

# Un dump vacío o truncado no es un respaldo.
gzip -t "$ARCHIVO"
[ "$(gzip -dc "$ARCHIVO" | wc -c)" -gt 1000 ] || { echo "Respaldo sospechosamente pequeño: $ARCHIVO" >&2; rm -f "$ARCHIVO"; exit 1; }

ls -1t "$DESTINO"/verificacion_*.sql.gz | tail -n +"$((RETENCION + 1))" | xargs -r rm -f
echo "Respaldo listo: $ARCHIVO"
