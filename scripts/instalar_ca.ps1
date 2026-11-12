<#
.SYNOPSIS
    Instala (o quita) la CA local del sistema en el almacén de confianza de Windows (X3).
.DESCRIPTION
    Cada estación debe confiar en la CA que firmó el certificado del servidor
    (scripts/generar_certificados.sh) para que Chrome y Edge abran https:// sin
    advertencias. Este script usa certutil, valida el archivo antes de instalar y
    es repetible: si la CA ya está instalada, no hace nada.

    Antes de instalar, comprueba que:
      - el archivo existe y es una CA (no el certificado del servidor);
      - no está vencida;
      - si se indica -HuellaEsperada, que su huella SHA-256 coincide con la anotada
        al generar los certificados (protege contra instalar una CA equivocada).

    Requiere PowerShell como administrador (alcance Equipo). Con alcance Usuario no
    hace falta, pero Windows muestra un cuadro de confirmación.

    Firefox usa su propio almacén: ver el manual (sección 3.3) para importarla ahí o
    activar security.enterprise_roots.enabled.
.PARAMETER CaCert
    Ruta del certificado de la CA (por defecto certs\ca\ca.crt del repositorio).
.PARAMETER HuellaEsperada
    Huella SHA-256 de la CA anotada en el servidor (con o sin ':'). Muy recomendable.
.PARAMETER Alcance
    Equipo (por defecto, todos los usuarios; requiere administrador) o Usuario.
.PARAMETER Almacen
    Almacén de certificados (por defecto Root, "Entidades de certificación raíz de
    confianza"). Solo se cambia para pruebas.
.PARAMETER Desinstalar
    Quita la CA en lugar de instalarla.
.PARAMETER Simular
    Muestra qué haría, sin modificar nada.
.EXAMPLE
    .\scripts\instalar_ca.ps1 -CaCert D:\ca.crt -HuellaEsperada "AB:CD:..."
#>
[CmdletBinding()]
param (
    [string]$CaCert = "",
    [string]$HuellaEsperada = "",
    [ValidateSet("Equipo", "Usuario")]
    [string]$Alcance = "Equipo",
    [string]$Almacen = "Root",
    [switch]$Desinstalar,
    [switch]$Simular
)

$ErrorActionPreference = "Stop"

if (-not $CaCert) {
    $raiz = if ($PSScriptRoot) { Split-Path $PSScriptRoot -Parent } else { (Get-Location).Path }
    $CaCert = Join-Path $raiz "certs\ca\ca.crt"
}

function Fallar([string]$mensaje) {
    Write-Host "[ERROR] $mensaje" -ForegroundColor Red
    exit 1
}

# --- 1. Validar el archivo ---------------------------------------------------
if (-not (Test-Path -LiteralPath $CaCert -PathType Leaf)) {
    Fallar "No existe el archivo: $CaCert (copia ca.crt desde el servidor, carpeta certs\ca)."
}
try {
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 -ArgumentList (Resolve-Path -LiteralPath $CaCert).Path
} catch {
    Fallar "El archivo no es un certificado válido: $CaCert"
}

$basica = $cert.Extensions | Where-Object { $_ -is [System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension] } | Select-Object -First 1
if ($null -eq $basica -or -not $basica.CertificateAuthority) {
    Fallar "El certificado no es una autoridad certificadora (CA). ¿Seleccionaste server.crt por error? Hay que instalar certs\ca\ca.crt."
}
if ($cert.NotAfter -lt (Get-Date)) {
    Fallar "La CA está vencida desde $($cert.NotAfter.ToString('yyyy-MM-dd')). Hay que generar una nueva (generar_certificados.sh --forzar-ca)."
}

$sha = [System.Security.Cryptography.SHA256]::Create()
$huella = ($sha.ComputeHash($cert.RawData) | ForEach-Object { $_.ToString("X2") }) -join ":"

Write-Host "CA:       $($cert.Subject)"
Write-Host "Vence:    $($cert.NotAfter.ToString('yyyy-MM-dd'))"
Write-Host "SHA-256:  $huella"

if ($HuellaEsperada -ne "") {
    $esperada = ($HuellaEsperada -replace "[:\s]", "").ToUpper()
    if (($huella -replace ":", "") -ne $esperada) {
        Fallar "La huella NO coincide con la esperada. No se hizo ningún cambio. Verifica que el archivo sea el ca.crt original del servidor."
    }
    Write-Host "La huella coincide con la esperada." -ForegroundColor Green
} else {
    Write-Host "[AVISO] No se indicó -HuellaEsperada: compara la huella de arriba con la anotada en el servidor antes de continuar." -ForegroundColor Yellow
}

# --- 2. Preparar la operación ------------------------------------------------
$ubicacion = if ($Alcance -eq "Equipo") { "LocalMachine" } else { "CurrentUser" }
$rutaAlmacen = "Cert:\$ubicacion\$Almacen\$($cert.Thumbprint)"
[string[]]$flagUsuario = @(if ($Alcance -eq "Usuario") { "-user" })
$instalada = Test-Path -LiteralPath $rutaAlmacen

if ($Alcance -eq "Equipo" -and -not $Simular) {
    $actual = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $actual.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Fallar "Se necesita PowerShell como administrador (o usa -Alcance Usuario)."
    }
}

if ($Desinstalar) {
    if (-not $instalada) { Write-Host "La CA no está instalada en $ubicacion\$Almacen. No hay nada que quitar."; exit 0 }
    $argumentos = $flagUsuario + @("-delstore", $Almacen, $cert.Thumbprint)
    if ($Simular) { Write-Host "[SIMULACIÓN] certutil $($argumentos -join ' ')"; exit 0 }
    $salida = (& certutil @argumentos 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { Fallar "certutil falló al quitar la CA (código $LASTEXITCODE).`n$salida" }
    if (Test-Path -LiteralPath $rutaAlmacen) { Fallar "La CA sigue presente tras quitarla." }
    Write-Host "CA quitada de $ubicacion\$Almacen." -ForegroundColor Green
    exit 0
}

if ($instalada) { Write-Host "La CA ya está instalada en $ubicacion\$Almacen. No se hizo ningún cambio."; exit 0 }

$argumentos = $flagUsuario + @("-addstore", "-f", $Almacen, (Resolve-Path -LiteralPath $CaCert).Path)
if ($Simular) { Write-Host "[SIMULACIÓN] certutil $($argumentos -join ' ')"; exit 0 }

# --- 3. Instalar y comprobar -------------------------------------------------
$salida = (& certutil @argumentos 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { Fallar "certutil falló al instalar la CA (código $LASTEXITCODE).`n$salida" }
if (-not (Test-Path -LiteralPath $rutaAlmacen)) { Fallar "certutil terminó, pero la CA no aparece en $ubicacion\$Almacen." }

Write-Host "CA instalada en $ubicacion\$Almacen." -ForegroundColor Green
Write-Host "Cierra y vuelve a abrir Chrome o Edge para que la reconozcan. Firefox: ver el manual, sección 3.3."
exit 0
