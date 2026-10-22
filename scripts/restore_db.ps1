<#
.SYNOPSIS
    Script de Restauración de Base de Datos PostgreSQL (D4) para entornos Windows / PowerShell.
.DESCRIPTION
    Ejecuta pg_restore dentro del contenedor de PostgreSQL a partir de un archivo .dump.
.PARAMETER BackupFile
    Ruta obligatoria al archivo .dump a restaurar.
.PARAMETER ContainerName
    Nombre del contenedor de Docker (por defecto 'verificacion-oaxaca-db-1').
.PARAMETER PostgresUser
    Usuario de PostgreSQL (por defecto 'verificacion').
.PARAMETER PostgresDb
    Nombre de la base de datos destino (por defecto 'verificacion').
#>
[CmdletBinding()]
param (
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$BackupFile,

    [string]$ContainerName = "verificacion-oaxaca-db-1",
    [string]$PostgresUser = "verificacion",
    [string]$PostgresDb = "verificacion"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $BackupFile)) {
    Write-Error "[ERROR] El archivo de respaldo '$BackupFile' no existe."
    exit 1
}

if ((Get-Item $BackupFile).Length -eq 0) {
    Write-Error "[ERROR] El archivo de respaldo '$BackupFile' se encuentra vacío."
    exit 1
}

Write-Host "[$((Get-Date).ToString('s'))] Iniciando restauración de PostgreSQL..." -ForegroundColor Cyan
Write-Host "  Archivo: $BackupFile"
Write-Host "  Contenedor: $ContainerName"
Write-Host "  Base de datos destino: $PostgresDb"

# Verificar Docker y contenedor
try {
    $runningContainers = docker ps --format "{{.Names}}"
    if ($LASTEXITCODE -ne 0) {
        throw "No fue posible comunicarse con el servicio de Docker."
    }
}
catch {
    Write-Error "[ERROR] Docker no se encuentra en ejecución o no está disponible: $_"
    exit 1
}

if ($runningContainers -notcontains $ContainerName) {
    Write-Error "[ERROR] El contenedor '$ContainerName' no está en ejecución."
    exit 1
}

# Ejecutar pg_restore
try {
    Get-Content $BackupFile -Raw -Encoding Byte | & docker exec -i $ContainerName pg_restore -U $PostgresUser -d $PostgresDb --clean --if-exists
    Write-Host "[OK] Restauración completada exitosamente desde $BackupFile." -ForegroundColor Green
}
catch {
    Write-Error "[ERROR] Falló la restauración con pg_restore: $_"
    exit 1
}
