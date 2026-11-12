#!/usr/bin/env bash
# Instala (o quita) la CA local del sistema en una estación Linux (X3).
#
# Cada estación debe confiar en la CA que firmó el certificado del servidor
# (scripts/generar_certificados.sh) para abrir https:// sin advertencias.
#
#   sudo scripts/instalar_ca.sh [--ca RUTA] [--huella SHA256] [--desinstalar] [--simular]
#   scripts/instalar_ca.sh --nss [--ca RUTA] [--huella SHA256]     (Chrome/Chromium, sin sudo)
#
# Opciones:
#   --ca RUTA        Certificado de la CA (por defecto certs/ca/ca.crt del repositorio).
#   --huella SHA256  Huella SHA-256 anotada en el servidor (con o sin ':'). Muy
#                    recomendable: si no coincide, no se instala nada.
#   --desinstalar    Quita la CA en lugar de instalarla.
#   --simular        Muestra qué haría, sin modificar nada.
#   --nss            En lugar del almacén del sistema, instala en la base NSS del
#                    usuario actual (~/.pki/nssdb), que es la que usan Chrome y
#                    Chromium en Linux. Requiere `certutil` (paquete libnss3-tools).
#   --destino DIR    Carpeta de anclas del sistema (solo para pruebas o distros raras).
#
# Almacén del sistema: Debian/Ubuntu (update-ca-certificates) y Fedora/RHEL
# (update-ca-trust). Firefox usa su propio almacén: ver el manual, sección 3.3.
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CA="$AQUI/../certs/ca/ca.crt"
HUELLA_ESPERADA=""
DESINSTALAR=0
SIMULAR=0
NSS=0
DESTINO=""
NOMBRE="verificacion-oaxaca-ca"

uso() { sed -n '2,23p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }
fallar() { echo "[ERROR] $1" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --ca) CA="${2:?Falta el valor de --ca}"; shift 2 ;;
        --huella) HUELLA_ESPERADA="${2:?Falta el valor de --huella}"; shift 2 ;;
        --desinstalar) DESINSTALAR=1; shift ;;
        --simular) SIMULAR=1; shift ;;
        --nss) NSS=1; shift ;;
        --destino) DESTINO="${2:?Falta el valor de --destino}"; shift 2 ;;
        -h|--help) uso; exit 0 ;;
        *) echo "Opción desconocida: $1" >&2; uso >&2; exit 2 ;;
    esac
done

command -v openssl >/dev/null 2>&1 || fallar "Se necesita openssl."

# --- 1. Validar el archivo ---------------------------------------------------
[ -f "$CA" ] || fallar "No existe el archivo: $CA (copia ca.crt desde el servidor, carpeta certs/ca)."
openssl x509 -in "$CA" -noout >/dev/null 2>&1 || fallar "El archivo no es un certificado PEM válido: $CA"
openssl x509 -in "$CA" -noout -text | grep -q "CA:TRUE" \
    || fallar "El certificado no es una autoridad certificadora (CA). ¿Elegiste server.crt por error? Hay que instalar certs/ca/ca.crt."
openssl x509 -in "$CA" -noout -checkend 0 >/dev/null \
    || fallar "La CA está vencida. Hay que generar una nueva (generar_certificados.sh --forzar-ca)."

HUELLA="$(openssl x509 -in "$CA" -noout -fingerprint -sha256 | cut -d= -f2)"
echo "CA:       $(openssl x509 -in "$CA" -noout -subject | sed 's/^subject= *//')"
echo "Vence:    $(openssl x509 -in "$CA" -noout -enddate | cut -d= -f2)"
echo "SHA-256:  $HUELLA"

if [ -n "$HUELLA_ESPERADA" ]; then
    A="$(printf '%s' "$HUELLA_ESPERADA" | tr -d ': ' | tr 'a-f' 'A-F')"
    B="$(printf '%s' "$HUELLA" | tr -d ':')"
    [ "$A" = "$B" ] || fallar "La huella NO coincide con la esperada. No se hizo ningún cambio. Verifica que el archivo sea el ca.crt original del servidor."
    echo "La huella coincide con la esperada."
else
    echo "[AVISO] No se indicó --huella: compara la huella de arriba con la anotada en el servidor antes de continuar."
fi

ejecutar() {
    if [ "$SIMULAR" -eq 1 ]; then echo "[SIMULACIÓN] $*"; else "$@"; fi
}

# --- 2a. Base NSS del usuario (Chrome / Chromium) ----------------------------
if [ "$NSS" -eq 1 ]; then
    command -v certutil >/dev/null 2>&1 || fallar "Falta certutil (instala libnss3-tools)."
    [ "$(id -u)" -ne 0 ] || fallar "Con --nss ejecuta el script como el usuario de la estación, sin sudo (la base NSS es por usuario)."
    BD="sql:$HOME/.pki/nssdb"
    if [ "$DESINSTALAR" -eq 1 ]; then
        ejecutar certutil -d "$BD" -D -n "Verificacion Oaxaca CA"
        [ "$SIMULAR" -eq 1 ] || echo "CA quitada de $HOME/.pki/nssdb."
        exit 0
    fi
    if [ "$SIMULAR" -eq 0 ] && certutil -d "$BD" -L -n "Verificacion Oaxaca CA" >/dev/null 2>&1; then
        echo "La CA ya está en $HOME/.pki/nssdb. No se hizo ningún cambio."; exit 0
    fi
    [ "$SIMULAR" -eq 1 ] || mkdir -p "$HOME/.pki/nssdb"
    [ "$SIMULAR" -eq 1 ] || [ -f "$HOME/.pki/nssdb/cert9.db" ] || certutil -d "$BD" -N --empty-password
    ejecutar certutil -d "$BD" -A -t "C,," -n "Verificacion Oaxaca CA" -i "$CA"
    [ "$SIMULAR" -eq 1 ] || { certutil -d "$BD" -L -n "Verificacion Oaxaca CA" >/dev/null 2>&1 || fallar "La CA no aparece en la base NSS tras instalarla."; \
        echo "CA instalada para Chrome y Chromium del usuario $USER. Reinicia el navegador."; }
    exit 0
fi

# --- 2b. Almacén del sistema -------------------------------------------------
if command -v update-ca-certificates >/dev/null 2>&1; then
    CARPETA="${DESTINO:-/usr/local/share/ca-certificates}"; ACTUALIZAR=(update-ca-certificates)
elif command -v update-ca-trust >/dev/null 2>&1; then
    CARPETA="${DESTINO:-/etc/pki/ca-trust/source/anchors}"; ACTUALIZAR=(update-ca-trust extract)
else
    fallar "No se encontró update-ca-certificates (Debian/Ubuntu) ni update-ca-trust (Fedora/RHEL)."
fi
ARCHIVO="$CARPETA/$NOMBRE.crt"

if [ "$SIMULAR" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
    fallar "Ejecuta con sudo (o usa --nss para Chrome/Chromium sin privilegios)."
fi

if [ "$DESINSTALAR" -eq 1 ]; then
    [ -f "$ARCHIVO" ] || [ "$SIMULAR" -eq 1 ] || { echo "La CA no está instalada en $ARCHIVO. No hay nada que quitar."; exit 0; }
    ejecutar rm -f "$ARCHIVO"
    ejecutar "${ACTUALIZAR[@]}"
    [ "$SIMULAR" -eq 1 ] || echo "CA quitada del almacén del sistema."
    exit 0
fi

if [ "$SIMULAR" -eq 0 ] && [ -f "$ARCHIVO" ] && cmp -s "$CA" "$ARCHIVO"; then
    echo "La CA ya está instalada en $ARCHIVO. No se hizo ningún cambio."; exit 0
fi

ejecutar install -D -m 0644 "$CA" "$ARCHIVO"
ejecutar "${ACTUALIZAR[@]}"
if [ "$SIMULAR" -eq 0 ]; then
    [ -f "$ARCHIVO" ] || fallar "No se pudo copiar la CA a $ARCHIVO."
    echo "CA instalada en el almacén del sistema ($ARCHIVO)."
    echo "Chrome y Chromium en Linux usan su propia base NSS: ejecuta también, como el usuario de la estación, scripts/instalar_ca.sh --nss."
fi
