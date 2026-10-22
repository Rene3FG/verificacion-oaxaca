<#
.SYNOPSIS
    Script de Respaldo de Base de Datos PostgreSQL (D4) para entornos Windows / PowerShell.
.DESCRIPTION
    Ejecuta pg_dump dentro del contenedor de PostgreSQL y guarda el archivo .dump en el directorio destino.
.PARAMETER ContainerName
    Nombre del contenedor de Docker (por defecto 'verificacion-oaxaca-db-1').
.PARAMETER PostgresUser
    Usuario de PostgreSQL (por defecto 'verificacion').
.PARAMETER PostgresDb
    Nombre de la base de datos (por defecto 'verificacion').
.PARAMETER BackupDir
    Directorio donde se almacenarán los respaldos (por defecto '.\backups').
.PARAMETER RetentionDays
    Días de retención para rotar respaldos antiguos (por defecto 30).
#>
[CmdletBinding()]
param (
    [string]$ContainerName = "verificacion-oaxaca-db-1",
    [string]$PostgresUser = "verificacion",
    [string]$PostgresDb = "verificacion",
    [string]$BackupDir = ".\backups",
    [int]$RetentionDays = 30
)

$ErrorActionPreference = "Stop"

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupFile = Join-Path $BackupDir "verificacion_${PostgresDb}_${Timestamp}.dump"

Write-Host "[$((Get-Date).ToString('s'))] Iniciando respaldo de PostgreSQL..." -ForegroundColor Cyan
Write-Host "  Contenedor: $ContainerName"
Write-Host "  Base de datos: $PostgresDb"
Write-Host "  Destino: $BackupFile"

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

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

# Ejecutar pg_dump
try {
    # Redirigir el stream binario de docker exec directamente al archivo
    & docker exec $ContainerName pg_dump -U $PostgresUser -F c $PostgresDb > $BackupFile
    
    if ((Test-Path $BackupFile) -and ((Get-Item $BackupFile).Length -gt 0)) {
        $sizeMB = [math]::Round(((Get-Item $BackupFile).Length / 1MB), 2)
        Write-Host "[OK] Respaldo generado exitosamente: $BackupFile ($sizeMB MB)" -ForegroundColor Green
    } else {
        throw "El archivo de respaldo no fue creado o tiene tamaño cero."
    }
}
catch {
    Write-Error "[ERROR] Falló la ejecución de pg_dump: $_"
    if (Test-Path $BackupFile) { Remove-Item $BackupFile -Force }
    exit 1
}

# Rotación de respaldos
$cutoffDate = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem -Path $BackupDir -Filter "verificacion_${PostgresDb}_*.dump" |
    Where-Object { $_.LastWriteTime -lt $cutoffDate } |
    ForEach-Object {
        Write-Host "  Eliminando respaldo antiguo: $($_.Name)" -ForegroundColor Yellow
        Remove-Item $_.FullName -Force
    }

Write-Host "[$((Get-Date).ToString('s'))] Proceso completado exitosamente." -ForegroundColor Green
