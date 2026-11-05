#!/usr/bin/env bash
# ==============================================================================
# Desbloquea a un usuario bloqueado por intentos fallidos de login (PENDIENTES X1)
# Sistema de Verificación Vehicular Oaxaca
#
#   scripts/desbloquear_usuario.sh USUARIO [--simular] [--ventana-min N]
#
# Es una herramienta de SOPORTE: toca la base de datos directamente. La API no
# tiene hoy una vía de desbloqueo (falta POST /api/usuarios/{id}/desbloquear);
# cuando exista, este script deja de ser necesario para los operadores.
#
# Qué hace: el backend bloquea a un usuario cuando acumula LOGIN_MAX_INTENTOS
# intentos fallidos recientes (motivo "Credenciales inválidas" en access_events,
# desde su último login correcto). Este script NO borra esos intentos ni inventa
# un login: les agrega al motivo "(desbloqueado por soporte)". Se conservan
# fecha, estación e IP, y el backend deja de contarlos.
#
# Variables (todas opcionales):
#   COMPOSE_ARGS   argumentos de docker compose
#                  (por defecto: -f docker-compose.prod.yml --env-file .env.prod;
#                   en desarrollo: COMPOSE_ARGS="-f docker-compose.yml")
#   VENTANA_MIN    ventana de bloqueo en minutos; debe coincidir con
#                  LOGIN_BLOQUEO_MIN del backend (por defecto 15)
# ==============================================================================
set -euo pipefail

USUARIO=""
SIMULAR=0
VENTANA="${VENTANA_MIN:-15}"

while [ $# -gt 0 ]; do
    case "$1" in
        --simular) SIMULAR=1 ;;
        --ventana-min) shift; VENTANA="${1:?Falta el valor de --ventana-min}" ;;
        -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
        -*) echo "[ERROR] Opción desconocida: $1" >&2; exit 2 ;;
        *) [ -z "$USUARIO" ] && USUARIO="$1" || { echo "[ERROR] Solo se admite un usuario." >&2; exit 2; } ;;
    esac
    shift
done

[ -n "$USUARIO" ] || { echo "Uso: scripts/desbloquear_usuario.sh USUARIO [--simular] [--ventana-min N]" >&2; exit 2; }
# Solo caracteres seguros: el valor viaja como argumento (nunca dentro del SQL),
# pero se limita a ASCII para que no se altere al cruzar la terminal.
[[ "$USUARIO" =~ ^[A-Za-z0-9._@-]{3,60}$ ]] || { echo "[ERROR] Usuario inválido: use de 3 a 60 caracteres entre letras, números y . _ @ -" >&2; exit 2; }
[[ "$VENTANA" =~ ^[0-9]{1,4}$ ]] && [ "$VENTANA" -gt 0 ] || { echo "[ERROR] --ventana-min debe ser un entero positivo." >&2; exit 2; }

read -r -a COMPOSE <<< "docker compose ${COMPOSE_ARGS:--f docker-compose.prod.yml --env-file .env.prod}"

# psql dentro del contenedor. Usuario y ventana viajan como argumentos
# posicionales de sh y como variables de psql (:'usuario', :ventana): nunca se
# concatenan en el texto SQL.
psql_db() {
    "${COMPOSE[@]}" exec -T db sh -c \
        'psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v usuario="$1" -v ventana="$2"' \
        sh "$USUARIO" "$VENTANA"
}

# Intentos fallidos que hoy cuentan para el bloqueo: de este usuario, motivo de
# credenciales inválidas (LIKE con _ para no depender de la tilde), dentro de la
# ventana y posteriores a su último login correcto.
PENDIENTES="e.resultado = 'DENEGADO'
  AND e.motivo LIKE 'Credenciales inv_lidas'
  AND e.created_at > now() - make_interval(mins => :ventana)
  AND e.created_at > COALESCE((SELECT max(o.created_at) FROM access_events o
                               WHERE o.user_id = e.user_id AND o.resultado = 'PERMITIDO'), '-infinity')"

echo "[$(date -Iseconds)] Desbloqueo de usuario: ${USUARIO} (ventana ${VENTANA} min)"

ID=$(echo "SELECT id FROM cat_usuarios WHERE username = :'usuario';" | psql_db)
[ -n "$ID" ] || { echo "[ERROR] No existe el usuario '${USUARIO}'." >&2; exit 1; }

CUENTA=$(echo "SELECT count(*) FROM access_events e JOIN cat_usuarios u ON u.id = e.user_id
               WHERE u.username = :'usuario' AND ${PENDIENTES};" | psql_db)
if [ "$CUENTA" -eq 0 ]; then
    echo "[OK] El usuario no tiene intentos fallidos que cuenten para el bloqueo: no está bloqueado por intentos."
    exit 0
fi

echo "Intentos fallidos vigentes que se liberarían (${CUENTA}):"
echo "SELECT '  ' || e.created_at::text || '  IP ' || COALESCE(e.ip_address, '-')
        FROM access_events e JOIN cat_usuarios u ON u.id = e.user_id
        WHERE u.username = :'usuario' AND ${PENDIENTES} ORDER BY e.created_at;" | psql_db

if [ "$SIMULAR" -eq 1 ]; then
    echo "[SIMULACIÓN] No se modificó nada."
    exit 0
fi

read -r -p "Se anotará 'desbloqueado por soporte' en esos ${CUENTA} intentos. Escribe SI para continuar: " R
[ "$R" = "SI" ] || { echo "Cancelado."; exit 1; }

LIBERADOS=$(echo "WITH liberados AS (
        UPDATE access_events e
           SET motivo = 'Credenciales invalidas (desbloqueado por soporte)', updated_at = now()
          FROM cat_usuarios u
         WHERE u.id = e.user_id AND u.username = :'usuario' AND ${PENDIENTES}
        RETURNING e.id)
    SELECT count(*) FROM liberados;" | psql_db)
echo "  Intentos liberados: ${LIBERADOS}"

RESTAN=$(echo "SELECT count(*) FROM access_events e JOIN cat_usuarios u ON u.id = e.user_id
               WHERE u.username = :'usuario' AND ${PENDIENTES};" | psql_db)
if [ "$RESTAN" -ne 0 ]; then
    echo "[ERROR] Quedan ${RESTAN} intentos que cuentan: revise que --ventana-min coincida con LOGIN_BLOQUEO_MIN." >&2
    exit 1
fi
echo "[$(date -Iseconds)] [OK] ${USUARIO} desbloqueado: ya puede iniciar sesión."
