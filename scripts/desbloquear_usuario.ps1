<#
.SYNOPSIS
    Desbloquea a un usuario bloqueado por intentos fallidos de login (PENDIENTES X1).
.DESCRIPTION
    Herramienta de SOPORTE: toca la base de datos directamente. Lo normal es que otro
    supervisor use el botón Desbloquear (POST /api/usuarios/{id}/desbloquear, desde
    2026-11-09); este script queda para cuando el bloqueado es el único supervisor.

    El backend bloquea a un usuario cuando acumula LOGIN_MAX_INTENTOS intentos fallidos
    recientes (motivo "Credenciales inválidas" en access_events, desde su último login
    correcto). Este script NO borra esos intentos ni inventa un login: les agrega al motivo
    "(desbloqueado por soporte)". Se conservan fecha, estación e IP, y el backend deja de
    contarlos.
.PARAMETER Usuario
    Nombre de usuario a desbloquear (3 a 60 caracteres: letras, números y . _ @ -).
.PARAMETER VentanaMin
    Ventana de bloqueo en minutos; debe coincidir con LOGIN_BLOQUEO_MIN del backend (15).
.PARAMETER Simular
    Solo muestra qué se liberaría, sin modificar nada.
.PARAMETER ComposeFile
    Archivo de Compose (por defecto 'docker-compose.prod.yml'; en desarrollo 'docker-compose.yml').
.PARAMETER EnvFile
    Archivo de variables (por defecto '.env.prod'). Si no existe, se omite.
.EXAMPLE
    .\scripts\desbloquear_usuario.ps1 supervisor1 -Simular
.EXAMPLE
    .\scripts\desbloquear_usuario.ps1 operador1 -ComposeFile docker-compose.yml
#>
[CmdletBinding()]
param (
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Usuario,
    [int]$VentanaMin = 15,
    [switch]$Simular,
    [string]$ComposeFile = "docker-compose.prod.yml",
    [string]$EnvFile = ".env.prod"
)

$ErrorActionPreference = "Stop"

# Solo caracteres ASCII seguros: el valor viaja como argumento (nunca dentro del SQL).
if ($Usuario -notmatch '^[A-Za-z0-9._@-]{3,60}$') {
    Write-Host "[ERROR] Usuario inválido: use de 3 a 60 caracteres entre letras, números y . _ @ -" -ForegroundColor Red
    exit 2
}
if ($VentanaMin -le 0 -or $VentanaMin -gt 9999) {
    Write-Host "[ERROR] -VentanaMin debe ser un entero entre 1 y 9999." -ForegroundColor Red
    exit 2
}

$composeArgs = @("compose", "-f", $ComposeFile)
if (Test-Path $EnvFile) { $composeArgs += @("--env-file", $EnvFile) }

# psql dentro del contenedor. Usuario y ventana viajan como argumentos posicionales de sh y
# como variables de psql (:'usuario', :ventana): nunca se concatenan en el texto SQL. El
# argumento de sh -c no lleva comillas dobles porque PowerShell 5.1 las deforma al llamar a un
# ejecutable nativo; es seguro porque ambos valores se validaron arriba.
function Invoke-PsqlDb {
    param([Parameter(Mandatory = $true)][string]$Sql)
    $salida = $Sql | docker @composeArgs exec -T db sh -c `
        'psql -v ON_ERROR_STOP=1 -At -U $POSTGRES_USER -d $POSTGRES_DB -v usuario=$1 -v ventana=$2' `
        sh $Usuario $VentanaMin
    if ($LASTEXITCODE -ne 0) { throw "psql terminó con código $LASTEXITCODE (¿está arriba el contenedor 'db'?)." }
    return ($salida -join "`n").Trim()
}

# Intentos fallidos que hoy cuentan para el bloqueo: de este usuario, motivo de credenciales
# inválidas (LIKE con _ para no depender de la tilde), dentro de la ventana y posteriores a
# su último login correcto.
$pendientes = @"
e.resultado = 'DENEGADO'
  AND e.motivo LIKE 'Credenciales inv_lidas'
  AND e.created_at > now() - make_interval(mins => :ventana)
  AND e.created_at > COALESCE((SELECT max(o.created_at) FROM access_events o
                               WHERE o.user_id = e.user_id AND o.resultado = 'PERMITIDO'), '-infinity')
"@

Write-Host "[$((Get-Date).ToString('s'))] Desbloqueo de usuario: $Usuario (ventana $VentanaMin min)" -ForegroundColor Cyan

try {
    $id = Invoke-PsqlDb "SELECT id FROM cat_usuarios WHERE username = :'usuario';"
    if (-not $id) {
        Write-Host "[ERROR] No existe el usuario '$Usuario'." -ForegroundColor Red
        exit 1
    }

    $consultaCuenta = "SELECT count(*) FROM access_events e JOIN cat_usuarios u ON u.id = e.user_id WHERE u.username = :'usuario' AND $pendientes;"
    $cuenta = [int](Invoke-PsqlDb $consultaCuenta)
    if ($cuenta -eq 0) {
        Write-Host "[OK] El usuario no tiene intentos fallidos que cuenten para el bloqueo: no está bloqueado por intentos." -ForegroundColor Green
        exit 0
    }

    Write-Host "Intentos fallidos vigentes que se liberarían ($cuenta):"
    Invoke-PsqlDb ("SELECT '  ' || e.created_at::text || '  IP ' || COALESCE(e.ip_address, '-') FROM access_events e JOIN cat_usuarios u ON u.id = e.user_id WHERE u.username = :'usuario' AND $pendientes ORDER BY e.created_at;")

    if ($Simular) {
        Write-Host "[SIMULACIÓN] No se modificó nada." -ForegroundColor Yellow
        exit 0
    }

    $respuesta = Read-Host "Se anotará 'desbloqueado por soporte' en esos $cuenta intentos. Escribe SI para continuar"
    # -cne: la confirmacion distingue mayusculas, igual que la version de Linux ("si" no cuenta).
    if ($respuesta -cne "SI") {
        Write-Host "Cancelado."
        exit 1
    }

    $actualiza = @"
WITH liberados AS (
  UPDATE access_events e
     SET motivo = 'Credenciales invalidas (desbloqueado por soporte)', updated_at = now()
    FROM cat_usuarios u
   WHERE u.id = e.user_id AND u.username = :'usuario' AND $pendientes
  RETURNING e.id)
SELECT count(*) FROM liberados;
"@
    $liberados = Invoke-PsqlDb $actualiza
    Write-Host "  Intentos liberados: $liberados"

    $restan = [int](Invoke-PsqlDb $consultaCuenta)
    if ($restan -ne 0) {
        Write-Host "[ERROR] Quedan $restan intentos que cuentan: revise que -VentanaMin coincida con LOGIN_BLOQUEO_MIN." -ForegroundColor Red
        exit 1
    }
    Write-Host "[$((Get-Date).ToString('s'))] [OK] $Usuario desbloqueado: ya puede iniciar sesión." -ForegroundColor Green
}
catch {
    Write-Host "[ERROR] $_" -ForegroundColor Red
    exit 1
}
