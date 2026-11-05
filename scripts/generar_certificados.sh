#!/usr/bin/env bash
# ==============================================================================
# Genera la CA local y el certificado TLS del servidor del verificentro (PENDIENTES X3)
# Sistema de Verificación Vehicular Oaxaca
#
#   scripts/generar_certificados.sh [--host NOMBRE]... [--ip DIRECCION]... [--hosts LISTA]
#                                   [--salida DIR] [--dias N] [--forzar-ca]
#
# Para la red local del verificentro (sin internet ni dominio público): crea una
# autoridad certificadora propia (CA) y un certificado de servidor firmado por
# ella. Las estaciones confían UNA vez en la CA (ver el manual) y desde entonces
# aceptan los certificados que ella firme, también al renovarlos.
#
# Resultado (por defecto en ./certs, que Git ignora):
#   certs/ca/ca.crt          CA pública: se instala en cada estación
#   certs/ca/ca.key          CA PRIVADA: guardarla fuera del servidor
#   certs/server/server.crt  certificado del servidor  } lo único que monta nginx
#   certs/server/server.key  llave del servidor        }
#
# Opciones:
#   --host NOMBRE    nombre DNS con el que las estaciones abren el sistema
#                    (repetible). "localhost" y 127.0.0.1 siempre se incluyen.
#   --ip DIRECCION   dirección IPv4 del servidor en la red (repetible).
#   --hosts LISTA    atajo: lista separada por comas con nombres e IPs mezclados, p. ej.
#                    "verificentro.local,192.168.1.100". Equivale a repetir --host y --ip.
#   --salida DIR     carpeta de salida (por defecto: certs).
#   --dias N         vigencia del certificado del servidor (por defecto 825).
#   --forzar-ca      crea una CA nueva aunque ya exista una (obliga a reinstalarla
#                    en todas las estaciones).
#
# Renovar el certificado del servidor: volver a ejecutar el script con las mismas
# opciones. Si la CA ya existe se reutiliza y las estaciones no cambian nada.
# Requiere openssl.
# ==============================================================================
set -euo pipefail

HOSTS=("localhost")
IPS=("127.0.0.1")
SALIDA="certs"
DIAS=825
FORZAR_CA=0

error() { echo "[ERROR] $*" >&2; exit 2; }

# Validan y agregan sin repetir ("localhost" y 127.0.0.1 ya están incluidos).
agregar_host() {
    local h="$1" x
    [[ "$h" =~ ^[0-9.]+$ ]] && error "'$h' parece una dirección IP: use --ip"
    [[ "$h" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$ ]] || error "Nombre DNS inválido: $h"
    for x in "${HOSTS[@]}"; do [ "$x" = "$h" ] && return 0; done
    HOSTS+=("$h")
}
agregar_ip() {
    local i="$1" x a b c d o
    [[ "$i" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || error "Dirección IPv4 inválida: $i"
    IFS=. read -r a b c d <<< "$i"
    for o in "$a" "$b" "$c" "$d"; do [ "$o" -le 255 ] || error "Dirección IPv4 inválida: $i"; done
    for x in "${IPS[@]}"; do [ "$x" = "$i" ] && return 0; done
    IPS+=("$i")
}

while [ $# -gt 0 ]; do
    case "$1" in
        --host) shift; agregar_host "${1:?Falta el valor de --host}" ;;
        --ip) shift; agregar_ip "${1:?Falta el valor de --ip}" ;;
        --hosts) shift; LISTA="${1:?Falta el valor de --hosts}"
                 IFS=',' read -r -a ITEMS <<< "$LISTA"
                 for X in "${ITEMS[@]}"; do
                     X="${X#"${X%%[![:space:]]*}"}"; X="${X%"${X##*[![:space:]]}"}"   # solo los extremos
                     [ -n "$X" ] || continue
                     if [[ "$X" =~ ^[0-9.]+$ ]]; then agregar_ip "$X"; else agregar_host "$X"; fi
                 done ;;
        --salida) shift; SALIDA="${1:?Falta el valor de --salida}" ;;
        --dias) shift; DIAS="${1:?Falta el valor de --dias}"
                [[ "$DIAS" =~ ^[0-9]{1,4}$ ]] && [ "$DIAS" -ge 1 ] && [ "$DIAS" -le 3650 ] || error "--dias debe estar entre 1 y 3650." ;;
        --forzar-ca) FORZAR_CA=1 ;;
        -h|--help) sed -n '2,34p' "$0"; exit 0 ;;
        *) error "Opción desconocida: $1" ;;
    esac
    shift
done
# Nombre que se muestra en el certificado: el primer nombre propio, si lo hay.
CN_SRV="${HOSTS[1]:-${HOSTS[0]}}"

command -v openssl >/dev/null 2>&1 || { echo "[ERROR] No se encontró openssl." >&2; exit 1; }

CA_DIR="${SALIDA}/ca"
SRV_DIR="${SALIDA}/server"
mkdir -p "$CA_DIR" "$SRV_DIR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- Autoridad certificadora local (se reutiliza si ya existe y sigue vigente) ---
if [ "$FORZAR_CA" -eq 0 ] && [ -f "$CA_DIR/ca.crt" ] && [ -f "$CA_DIR/ca.key" ] \
   && openssl x509 -in "$CA_DIR/ca.crt" -noout -checkend $((60*60*24*30)) >/dev/null; then
    echo "CA existente reutilizada: $CA_DIR/ca.crt (las estaciones no necesitan cambios)"
else
    [ -f "$CA_DIR/ca.crt" ] && echo "[AVISO] Se crea una CA NUEVA: habrá que reinstalarla en todas las estaciones."
    cat > "$TMP/ca.cnf" <<'EOF'
[req]
distinguished_name = dn
prompt = no
[dn]
O = Verificacion Vehicular Oaxaca
CN = Verificacion Oaxaca CA local
[v3_ca]
basicConstraints = critical,CA:TRUE,pathlen:0
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
EOF
    openssl ecparam -name prime256v1 -genkey -noout -out "$CA_DIR/ca.key"
    openssl req -new -x509 -sha256 -days 3650 -key "$CA_DIR/ca.key" \
        -config "$TMP/ca.cnf" -extensions v3_ca -out "$CA_DIR/ca.crt"
    echo "CA nueva creada: $CA_DIR/ca.crt (vigencia 10 años)"
fi

# --- Certificado del servidor ---
SAN=""
for h in "${HOSTS[@]}"; do SAN="${SAN:+$SAN,}DNS:$h"; done
for i in "${IPS[@]}";   do SAN="${SAN},IP:$i"; done
cat > "$TMP/srv.ext" <<EOF
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
subjectAltName = ${SAN}
EOF
openssl ecparam -name prime256v1 -genkey -noout -out "$SRV_DIR/server.key"
cat > "$TMP/srv.cnf" <<EOF
[req]
distinguished_name = dn
prompt = no
[dn]
O = Verificacion Vehicular Oaxaca
CN = ${CN_SRV}
EOF
openssl req -new -key "$SRV_DIR/server.key" -config "$TMP/srv.cnf" -out "$TMP/server.csr"
if ! SALIDA_FIRMA="$(openssl x509 -req -sha256 -days "$DIAS" -in "$TMP/server.csr" \
        -CA "$CA_DIR/ca.crt" -CAkey "$CA_DIR/ca.key" -CAcreateserial \
        -extfile "$TMP/srv.ext" -out "$SRV_DIR/server.crt" 2>&1)"; then
    echo "[ERROR] No se pudo firmar el certificado del servidor:" >&2
    echo "$SALIDA_FIRMA" >&2
    exit 1
fi
# nginx lee los certificados como root al arrancar, antes de bajar privilegios: basta con 600.
chmod 600 "$CA_DIR/ca.key" "$SRV_DIR/server.key" 2>/dev/null || true

# --- Comprobaciones ---
openssl verify -CAfile "$CA_DIR/ca.crt" "$SRV_DIR/server.crt" >/dev/null \
    || { echo "[ERROR] El certificado del servidor no valida contra la CA." >&2; exit 1; }
pub_crt="$(openssl x509 -in "$SRV_DIR/server.crt" -pubkey -noout | openssl md5)"
pub_key="$(openssl pkey -in "$SRV_DIR/server.key" -pubout | openssl md5)"
[ "$pub_crt" = "$pub_key" ] || { echo "[ERROR] La llave no corresponde al certificado." >&2; exit 1; }

echo
echo "[OK] Certificado del servidor generado y verificado:"
echo "  Nombres: ${SAN//,/  }"
echo "  Vence:   $(openssl x509 -in "$SRV_DIR/server.crt" -noout -enddate | cut -d= -f2)"
echo "  Huella SHA-256 de la CA (compárela al instalarla en una estación):"
echo "    $(openssl x509 -in "$CA_DIR/ca.crt" -noout -fingerprint -sha256 | cut -d= -f2)"
echo
echo "Siguientes pasos:"
echo "  1. Guarde $CA_DIR/ca.key FUERA del servidor (USB cifrada o gestor de secretos)."
echo "     Solo $SRV_DIR/ se monta en nginx."
echo "  2. Instale $CA_DIR/ca.crt en cada estación (ver el manual, sección TLS)."
echo "  3. Anote la fecha de vencimiento y renueve antes con este mismo script."
