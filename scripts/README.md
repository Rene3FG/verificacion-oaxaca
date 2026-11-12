# Scripts Operativos de Respaldo y Restauración (D4)

Este directorio contiene las herramientas ejecutables para cumplir con la política de respaldos y recuperación ante desastres de la base de datos PostgreSQL local (**Entregable D4**).

---

## 1. Contenido

| Archivo | Plataforma | Propósito |
|---|---|---|
| `respaldo.sh` | Linux (producción) | Respaldo del stack de producción (`docker-compose.prod.yml` con `.env.prod`): `pg_dump` comprimido (`.sql.gz`), verificación de integridad y retención de los últimos 14 (`RETENCION=n`). Ver `README.md` de la raíz. |
| `restaurar.sh` | Linux (producción) | Restauración de un `.sql.gz` hecho con `respaldo.sh`, con confirmación explícita (`SI`). **Destruye la base actual.** |
| `backup_db.ps1` | Windows / PowerShell | Respaldo de la base de **desarrollo y pruebas** (contenedor `verificacion-oaxaca-db-1`, formato `.dump` de `pg_dump -F c`). |
| `restore_db.ps1` | Windows / PowerShell | Restauración de un `.dump` hecho con `backup_db.ps1`, con `pg_restore --clean --if-exists`. |
| `smoke_e2e_flujo.mjs` | Node.js 18+ (cualquier SO) | Prueba de humo del ciclo vehicular completo contra la API local. Ver sección 4.1. |
| `smoke_e2e_ui.mjs` | Node.js 18+ (Puppeteer-core / Chrome / Edge) | Prueba de humo E2E de interfaz en navegador headless (cubre las 5 vistas). Ver sección 4.2. |
| `desbloquear_usuario.sh` / `.ps1` | Linux / Windows | Soporte: desbloquea a un usuario bloqueado por intentos fallidos de login (X1). Ver sección 5. |
| `sql/minimo_privilegio.sql` | PostgreSQL (psql) | Crea el rol de BD de mínimo privilegio de la aplicación (X5-e). Opcional y no aplicado; ver el manual, sección 3.6. |
| `generar_certificados.sh` | Linux, o Windows con Git Bash o WSL | Genera la CA local y el certificado TLS del servidor (X3). Ver sección 6. |
| `instalar_ca.sh` / `.ps1` | Linux / Windows | Instala o quita la CA local en el almacén de confianza de las estaciones cliente (X3). Ver sección 7. |

---

> **Consolidación (2026-11-10):** se retiraron `backup_db.sh` y `restore_db.sh`, que duplicaban a `respaldo.sh` y `restaurar.sh` (que sí usan el compose de producción). Hay un solo juego por plataforma. **Los formatos no son intercambiables:** los scripts de Linux producen y leen `.sql.gz`; los de Windows, `.dump`. No se puede restaurar un archivo de una plataforma con los scripts de la otra.

---

## 2. Parámetros

**Linux (`respaldo.sh`, `restaurar.sh`):** se ejecutan desde la raíz del repositorio y leen `.env.prod`.
- `respaldo.sh [directorio]`: directorio destino (por defecto `./respaldos`).
- `RETENCION`: cantidad de respaldos que se conservan (por defecto `14`).

**Windows (`backup_db.ps1`, `restore_db.ps1`):** parámetros de PowerShell.
- `-ContainerName`: contenedor de PostgreSQL (por defecto `verificacion-oaxaca-db-1`).
- `-PostgresUser` y `-PostgresDb`: usuario y base (por defecto `verificacion`).
- `-BackupDir`: destino de los respaldos (por defecto `.\backups`).
- `-RetentionDays`: días de retención antes de purgar respaldos antiguos (por defecto `30`).
- `restore_db.ps1 -BackupFile`: archivo `.dump` a restaurar.

Los directorios `respaldos/`, `backups/` y los archivos `*.dump` y `*.sql.gz` están en `.gitignore`: contienen datos de propietarios y placas y no deben subirse al repositorio.

---

## 3. Ejemplos de Uso

### En Linux (Producción Verificentro)

```bash
# Respaldo manual
chmod +x scripts/*.sh
scripts/respaldo.sh /var/respaldos/verificacion

# Restauración manual (pide confirmación y destruye la base actual)
scripts/restaurar.sh /var/respaldos/verificacion/verificacion_AAAAMMDD_HHMMSS.sql.gz
```

#### Programación Diaria con Cron (02:00 AM)
```bash
sudo crontab -e
# Agregar la línea:
0 2 * * * cd /opt/verificacion-oaxaca && scripts/respaldo.sh /var/respaldos/verificacion >> /var/log/verificacion_backup.log 2>&1
```

### En Windows / PowerShell (Desarrollo y Pruebas)

```powershell
# Respaldo
.\scripts\backup_db.ps1

# Restauración
.\scripts\restore_db.ps1 -BackupFile .\backups\verificacion_verificacion_20261022_120000.dump
```

---

## 4. Pruebas de Humo E2E (PENDIENTES Q2)

### 4.1 Ciclo vehicular por API (`smoke_e2e_flujo.mjs`)

Recorre el ciclo completo contra la API local y confirma el estado del expediente después de cada paso, hasta `IMPRESO`. Sirve para comprobar, tras un despliegue o un cambio grande, que Captura, Prueba y Impresión Central siguen conectadas entre sí. Usa solo `fetch` nativo (Node.js 18 o superior) y no instala dependencias.

**Pasos que valida** (cada uno imprime `✓` o `✗`):

1. Detección de estación y login en Captura.
2. Creación del expediente con una placa única `PRU-` + 6 dígitos del reloj.
3. Captura de datos del vehículo y del certificado, normalización e inspección visual aprobada en caseta (NOM-047 Opción A; el checklist se lee de `GET /api/inspeccion/checklist`).
4. Login en Prueba y evaluación OBD/SBD.
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

---

### 4.2 Interfaz de usuario en navegador (`smoke_e2e_ui.mjs`)

Automatiza la navegación e interacción real en navegador headless (Chrome o Edge) cubriendo las 5 pantallas del sistema mediante `puppeteer-core`. Valida:

1. Detección automática de la estación en `LoginView` y el título institucional.
2. Manejo visual y mensaje de error ante credenciales incorrectas.
3. Cambio dinámico de estación mediante parámetro `?estacion=CAPTURA-REFORMA-L1`.
4. Inicio de sesión y redirección a `CapturaView`.
5. Formulario de placa y creación reactiva de un expediente en Captura.
6. Cambio a `PRUEBA-REFORMA-L1`, login y visualización de cola en `PruebaView`.
7. Cambio a `IMPRESION-REFORMA-01`, login, filtros rápidos y cola en `ImpresionView`.
8. Login de supervisor y visualización de las 5 pestañas de `SupervisorView` (Monitor, Errores y Reintentos, Reimpresión, Auditoría y Administración).

**Uso:**
```powershell
# Requiere el frontend y el backend levantados
node scripts\smoke_e2e_ui.mjs

# Contra otra URL de frontend
$env:APP_URL = "http://localhost:5173"
node scripts\smoke_e2e_ui.mjs
```

---

## 5. Desbloqueo de usuarios (`desbloquear_usuario.sh` y `.ps1`)

Herramienta de **soporte** para destrabar a un usuario que el backend bloqueó por intentos fallidos de login (PENDIENTES X1: 5 fallos seguidos, 15 minutos). Sirve sobre todo para un **supervisor bloqueado**, que no tiene a quién pedirle el desbloqueo. Para un operador, lo habitual es esperar a que venza el bloqueo o que lo destrabe el supervisor del centro, pero esa vía todavía no existe en la API (falta `POST /api/usuarios/{id}/desbloquear`).

**Qué hace y qué no.** No borra intentos ni inventa un login. A los intentos fallidos que hoy cuentan para el bloqueo les agrega al motivo `(desbloqueado por soporte)`. Se conservan su fecha, estación e IP, y el backend deja de contarlos. Antes de modificar muestra la lista y pide escribir `SI` (en mayúsculas); al terminar comprueba que ya no quede ningún intento vigente.

```bash
# Linux (producción). Primero con --simular para ver qué se liberaría
scripts/desbloquear_usuario.sh supervisor1 --simular
scripts/desbloquear_usuario.sh supervisor1
# Desarrollo: otro compose
COMPOSE_ARGS="-f docker-compose.yml" scripts/desbloquear_usuario.sh operador1
```

```powershell
# Windows / PowerShell
.\scripts\desbloquear_usuario.ps1 supervisor1 -Simular
.\scripts\desbloquear_usuario.ps1 supervisor1
.\scripts\desbloquear_usuario.ps1 operador1 -ComposeFile docker-compose.yml
```

| Opción | Por defecto | Uso |
|---|---|---|
| Usuario (primer argumento) | obligatorio | De 3 a 60 caracteres entre letras, números y `. _ @ -`. El valor viaja como argumento de `psql`, nunca dentro del texto SQL. |
| `--simular` / `-Simular` | apagado | Solo muestra qué se liberaría. |
| `--ventana-min` / `-VentanaMin` | 15 | **Debe coincidir con `LOGIN_BLOQUEO_MIN`** del backend; si es menor, el script avisa que quedan intentos vigentes y falla. |
| `COMPOSE_ARGS` / `-ComposeFile` y `-EnvFile` | `docker-compose.prod.yml` y `.env.prod` | Qué compose usar. |

**Límites a tener presentes**
- Requiere que el contenedor `db` esté en ejecución y modifica la base directamente: hacer un respaldo antes si hay dudas.
- Solo levanta el bloqueo **por intentos**. No reactiva a un usuario desactivado (`is_active = false`); eso se hace desde Administración.
- Tras el desbloqueo, la contraseña sigue siendo la misma: si el usuario no la recuerda, un supervisor debe restablecerla.
- Los scripts se probaron con un `docker` simulado (validación de argumentos, confirmación, simulación, error si quedan intentos y que el SQL sea ASCII y no contenga el usuario). **No se han ejecutado contra un Postgres real**: la primera corrida debería hacerse con `--simular` en un ambiente de pruebas.

---

## 6. Certificados TLS (`generar_certificados.sh`)

Genera lo necesario para servir el sistema por HTTPS en la red local del verificentro (PENDIENTES X3): una **CA propia** y un **certificado de servidor** firmado por ella. Las estaciones instalan la CA una sola vez y desde entonces aceptan los certificados que ella firme, también al renovarlos. Requiere `openssl`. El procedimiento completo, con la instalación de la CA en las estaciones, está en el manual (sección 3.3).

```bash
scripts/generar_certificados.sh --hosts "verificentro.local,192.168.1.100"
```

| Opción | Por defecto | Uso |
|---|---|---|
| `--hosts LISTA` | `localhost` y `127.0.0.1` siempre incluidos | Atajo: lista separada por comas con nombres e IPs mezclados (`"verificentro.local,192.168.1.100"`). |
| `--host NOMBRE` (repetible) | | Nombre con el que las estaciones abren el sistema. |
| `--ip DIRECCION` (repetible) | | Dirección IPv4 del servidor en la red. |
| `--salida DIR` | `certs` | Carpeta de salida (Git la ignora). |
| `--dias N` | 825 | Vigencia del certificado del servidor. |
| `--forzar-ca` | apagado | Crea una CA nueva aunque ya exista; obliga a reinstalarla en todas las estaciones. |

**Qué deja:** `certs/ca/ca.crt` (CA pública, se instala en las estaciones), `certs/ca/ca.key` (CA privada: **guardarla fuera del servidor**) y `certs/server/server.crt` y `server.key` (lo único que monta `nginx`). Claves ECDSA P-256 y nombres alternativos (SAN) obligatorios, que son los que validan los navegadores.

**Renovar:** volver a ejecutarlo con las mismas opciones. Si la CA existe y no vence en 30 días, se reutiliza y las estaciones no cambian nada; solo se firma un certificado de servidor nuevo.

**Cómo se probó:** en Windows (Git Bash, OpenSSL 3.2) y en Linux (WSL2, OpenSSL 3.0). Se comprobó la validación de argumentos (incluida la lista de `--hosts`: espacios internos, IPs mal escritas y nombres que parecen IP), la cadena de confianza, los nombres y la IP recomendados, la reutilización de la CA y la renovación, y se hizo un **handshake TLS real** con un servidor y clientes de prueba: conecta con TLS 1.3 con la CA instalada, rechaza un nombre que no está en el certificado, desconfía si la estación no tiene la CA y rechaza TLS 1.1. **No se ha probado con el `nginx` del stack** (pendiente de encender Docker).

---

## 7. Instalación de la CA en Estaciones Cliente (`instalar_ca.sh` / `instalar_ca.ps1`)

Registra el certificado de la CA raíz (`certs/ca/ca.crt`) en el almacén de certificados de confianza de las estaciones cliente del verificentro (**PENDIENTES X3**), permitiendo que Chrome y Edge establezcan conexiones HTTPS seguras sin advertencias.

```bash
# Linux (almacén del sistema, requiere sudo)
sudo scripts/instalar_ca.sh --ca certs/ca/ca.crt --huella "CA:ED:09:..."

# Linux (base NSS de Chrome/Chromium del usuario, sin sudo)
scripts/instalar_ca.sh --nss --ca certs/ca/ca.crt --huella "CA:ED:09:..."
```

```powershell
# Windows (PowerShell como Administrador, almacén Equipo/Root)
.\scripts\instalar_ca.ps1 -CaCert certs\ca\ca.crt -HuellaEsperada "CA:ED:09:..."

# Modo simulación
.\scripts\instalar_ca.ps1 -Simular
```

| Opción | Por defecto | Uso |
|---|---|---|
| `-CaCert` / `--ca` | `certs/ca/ca.crt` | Ruta al archivo de la CA exportada desde el servidor. |
| `-HuellaEsperada` / `--huella` | Opcional | Huella SHA-256 informada al generar los certificados. Si no coincide, rechaza la instalación. |
| `-Desinstalar` / `--desinstalar` | Desactivado | Retira el certificado del almacén de confianza. |
| `-Simular` / `--simular` | Desactivado | Valida el certificado y muestra el comando sin modificar el sistema. |
| `-Alcance` (Windows) | `Equipo` | `Equipo` instala para todos los usuarios y exige PowerShell como administrador; `Usuario` solo para el usuario actual (Windows muestra un cuadro de confirmación). |
| `-Almacen` (Windows) | `Root` | Almacén de destino; solo se cambia para pruebas. |
| `--destino` (Linux) | según la distribución | Carpeta de anclas del sistema (`/usr/local/share/ca-certificates` o `/etc/pki/ca-trust/source/anchors`); solo para pruebas o distribuciones raras. |

Ambos scripts rechazan un archivo que no sea una CA (por ejemplo `server.crt`), una CA vencida o una huella que no coincida, y son repetibles: si la CA ya está instalada no hacen nada.

**Verificación (2026-11-11):** la versión de Windows se probó con el `certutil` real contra un almacén de prueba del usuario (instalar, repetir, desinstalar y rechazos), sin tocar `Root`; la de Linux, con `update-ca-certificates` e `id` simulados. **No se han ejecutado** contra el almacén `Root` de una estación real, ni `update-ca-trust` (Fedora/RHEL), ni la base NSS real (`--nss`, solo en simulación). Probar primero en una estación de pruebas.

