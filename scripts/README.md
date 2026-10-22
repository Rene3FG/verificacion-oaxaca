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
