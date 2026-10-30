# Scripts Operativos de Respaldo y Restauración (D4)

Este directorio contiene las herramientas ejecutables para cumplir con la política de respaldos y recuperación ante desastres de la base de datos PostgreSQL local (**Entregable D4**).

---

## 1. Contenido

| Archivo | Plataforma | Propósito |
|---|---|---|
| `backup_db.sh` | Linux (Ubuntu Server / Debian) | Respaldo automatizado con `pg_dump`, verificación de integridad y rotación a 30 días. |
| `restore_db.sh` | Linux (Ubuntu Server / Debian) | Restauración de base de datos con `pg_restore --clean --if-exists`. |
| `backup_db.ps1` | Windows / PowerShell | Script equivalente para entornos de prueba y desarrollo local. |
| `restore_db.ps1` | Windows / PowerShell | Script equivalente de restauración para Windows / PowerShell. |
| `respaldo.sh` / `restaurar.sh` | Linux | Variante de respaldo y restauración con `pg_dump` comprimido y confirmación explícita (ver `README.md` de la raíz). |
| `smoke_e2e_flujo.mjs` | Node.js 18+ (cualquier SO) | Prueba de humo del ciclo vehicular completo contra la API local. Ver sección 4. |

---

## 2. Parámetros y Variables de Entorno

Los scripts aceptan variables de entorno o parámetros de invocación:

- `CONTAINER_NAME`: Nombre del contenedor PostgreSQL (por defecto `verificacion-oaxaca-db-1` en local, o `verificacion-oaxaca-db-1` / `db` según compose).
- `POSTGRES_USER`: Usuario administrador de la base de datos (por defecto `verificacion`).
- `POSTGRES_DB`: Nombre de la base de datos (por defecto `verificacion`).
- `BACKUP_DIR`: Directorio destino (por defecto `/var/backups/verificacion` en Linux o `.\backups` en Windows).
- `RETENTION_DAYS`: Días de retención antes de purgar respaldos antiguos (por defecto `30`).

---

## 3. Ejemplos de Uso

### En Linux (Producción Verificentro)

```bash
# Respaldo manual
chmod +x scripts/*.sh
./scripts/backup_db.sh

# Restauración manual
./scripts/restore_db.sh /var/backups/verificacion/verificacion_verificacion_20261022_120000.dump
```

#### Programación Diaria con Cron (02:00 AM)
```bash
sudo crontab -e
# Agregar la línea:
0 2 * * * /opt/verificacion-oaxaca/scripts/backup_db.sh >> /var/log/verificacion_backup.log 2>&1
```

### En Windows / PowerShell (Desarrollo y Pruebas)

```powershell
# Respaldo
.\scripts\backup_db.ps1

# Restauración
.\scripts\restore_db.ps1 -BackupFile .\backups\verificacion_verificacion_20261022_120000.dump
```

---

## 4. Prueba de humo del ciclo vehicular (`smoke_e2e_flujo.mjs`)

Recorre el ciclo completo contra la API local y confirma el estado del expediente después de cada paso, hasta `IMPRESO`. Sirve para comprobar, tras un despliegue o un cambio grande, que Captura, Prueba y Impresión Central siguen conectadas entre sí. Usa solo `fetch` nativo (Node.js 18 o superior) y no instala dependencias.

**Pasos que valida** (cada uno imprime `✓` o `✗`):

1. Detección de estación y login en Captura.
2. Creación del expediente con una placa única `PRU-` + 6 dígitos del reloj.
3. Captura de datos del vehículo y del certificado, y normalización.
4. Login en Prueba, inspección visual aprobada (el checklist se lee de `GET /api/inspeccion/checklist`) y evaluación OBD/SBD.
5. Configuración, inicio y resultado de la prueba con lecturas aprobadas (modo de equipo `manual`, o `simulador` con escenario `APROBADO`).
6. Login en Impresión Central, verificación del inventario de folios (da de alta un lote si no quedan), tipo de certificado, solicitud de folio e impresión, con estado final `IMPRESO`.

Al terminar cierra las sesiones que abrió, incluso si un paso falla. Termina con código `0` si todo salió bien y `1` si falló alguno.

**Requisitos:** backend, PostgreSQL y Redis arriba, y los datos de desarrollo cargados (`python -m app.seed`, que crea las estaciones `CAPTURA-REFORMA-L1`, `PRUEBA-REFORMA-L1` e `IMPRESION-REFORMA-01` y los usuarios `operador1` y `supervisor1`).

```powershell
# Contra el backend local (http://localhost:8000)
node scripts\smoke_e2e_flujo.mjs

# Contra otra URL o con otras credenciales
$env:API_URL = "http://127.0.0.1:8000"
$env:SMOKE_USUARIO = "operador1"; $env:SMOKE_PASSWORD = "operador1"
node scripts\smoke_e2e_flujo.mjs
```

| Variable | Por defecto | Uso |
|---|---|---|
| `API_URL` | `http://localhost:8000` | Dirección base de la API. |
| `SMOKE_USUARIO` / `SMOKE_PASSWORD` | `operador1` / `operador1` | Operador con permisos de Captura, Prueba e Impresión en la línea 1. |
| `SMOKE_SUPERVISOR` / `SMOKE_SUPERVISOR_PASSWORD` | `supervisor1` / `supervisor1` | Solo se usa para dar de alta folios si el inventario está vacío. |
| `SMOKE_EST_CAPTURA` / `SMOKE_EST_PRUEBA` / `SMOKE_EST_IMPRESION` | estaciones de la semilla | `device_identifier` de cada estación. |
| `SMOKE_TIPO_CERTIFICADO` / `SMOKE_TIPO_VERIFICACION` | `PARTICULAR` / `ORDINARIA` | Tipo de certificado y de verificación a usar. |

> **Datos que deja:** cada corrida crea un expediente `PRU-…` en `IMPRESO` y consume un folio. Úsalo en desarrollo o en un ambiente de pruebas, no en producción. Tras 5 contraseñas incorrectas seguidas el backend bloquea al usuario 15 minutos (X1); el script no reintenta logins fallidos.
