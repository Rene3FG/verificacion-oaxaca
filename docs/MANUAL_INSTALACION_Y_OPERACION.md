# Manual de Instalación y Operación — Verificación Vehicular Oaxaca

**Sistema de Verificación Vehicular del Estado de Oaxaca**  
**Versión del documento:** 1.0 (Fase 4 / Corte Octubre 2026)  
**Clasificación:** Manual Técnico y Operativo (D6)

---

## 1. Arquitectura del Sistema

El sistema opera bajo un modelo de **alta resiliencia local con sincronización asíncrona**: cada centro de verificación (verificentro) cuenta con un servidor local que aloja la base de datos operativa y los servicios centrales, permitiendo la operación continua sin interrupciones incluso ante cortes prolongados de internet.

```
                           RED INTERNA DEL VERIFICENTRO (LAN)
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                                                                              │
 │   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐  │
 │   │ Estación     │   │ Estación     │   │ Estación     │   │ Estación     │  │
 │   │ Captura L1/L2│   │ Prueba L1/L2 │   │ Impresión    │   │ Supervisión  │  │
 │   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘  │
 │          │                  │                  │                  │          │
 │          └──────────────────┴─────────┬────────┴──────────────────┘          │
 │                                       │ HTTP / LAN (Puerto 80)               │
 │                                       ▼                                      │
 │                     ┌──────────────────────────────────┐                     │
 │                     │  Nginx Reverse Proxy & Frontend  │                     │
 │                     │  (Vue 3 / Vuetify / SPA)         │                     │
 │                     └─────────────────┬────────────────┘                     │
 │                                       │ /api/* (Puerto 8000)                 │
 │                                       ▼                                      │
 │                     ┌──────────────────────────────────┐                     │
 │                     │  Backend FastAPI (Python 3.12)   │                     │
 │                     │  (Alembic, WeasyPrint, Hash SHA) │                     │
 │                     └────────┬─────────────────┬───────┘                     │
 │                              │                 │                             │
 │                              ▼                 ▼                             │
 │                     ┌────────────────┐ ┌───────────────┐                     │
 │                     │ PostgreSQL 16  │ │ Redis 7       │                     │
 │                     │ (Base local)   │ │ (Cola local)  │                     │
 │                     └────────────────┘ └───────────────┘                     │
 └───────────────────────────────────────┬──────────────────────────────────────┘
                                         │ Sincronización Outbox (HTTPS)
                                         ▼
                     ┌──────────────────────────────────────┐
                     │ Sistema Central Estatal (Secretaría) │
                     └──────────────────────────────────────┘
```

---

## 2. Requisitos de Infraestructura y Hardware

### 2.1 Servidor Local del Verificentro
- **Procesador:** x86-64 con 4 núcleos o superior (Intel Core i5 / AMD Ryzen 5 mínimo).
- **Memoria RAM:** Mínimo 8 GB (Recomendado 16 GB).
- **Almacenamiento:** Mínimo 120 GB SSD con tecnología de tolerancia a fallos.
- **Sistema Operativo:** Ubuntu Server 22.04 LTS / 24.04 LTS o Debian 12 (en desarrollo se soporta Windows 10/11 x64).
- **Software Base:** Docker Engine v24+ y Docker Compose v2+.

### 2.2 Estaciones Operativas (Clientes)
- Navegador Google Chrome v120+ o Microsoft Edge Chromium v120+.
- Resolución recomendada: 1920×1080 (FHD) o 1366×768 (HD). Soporte responsive hasta 1024×768 para terminales compactas.
- Conectividad LAN cableada gigabit hacia el switch del verificentro.

### 2.3 Periféricos e Impresoras
- **Impresora de Certificados:** Impresora láser monocromática/color dedicada exclusivamente para papel valorado oficial del Estado de Oaxaca.
- **Impresora de Resultados:** Impresora láser estándar para reportes complementarios en papel bond blanco (HU-074).
- **Equipos de Medición:** Analizador de gases, dinamómetro y opacímetro conectados a la línea física.

---

## 3. Instalación y Despliegue en Servidor Local

### 3.1 Preparación de Archivos
1. Clonar el repositorio oficial en el servidor del verificentro:
   ```bash
   git clone https://github.com/Rene3FG/verificacion-oaxaca.git /opt/verificacion-oaxaca
   cd /opt/verificacion-oaxaca
   ```

2. Generar el archivo de variables de entorno de producción a partir de la plantilla:
   ```bash
   cp .env.prod.example .env.prod
   chmod 600 .env.prod
   ```

### 3.2 Configuración de Variables de Entorno (`.env.prod`)
Editar el archivo `.env.prod` con los parámetros correspondientes al centro:

```env
# --- Base de Datos PostgreSQL ---
POSTGRES_USER=verificacion
# OBLIGATORIO: sin esta contraseña `docker compose` no arranca. Definir una larga y única
# (no usar la de ningún ejemplo). Se genera una con:  openssl rand -base64 24
POSTGRES_PASSWORD=
POSTGRES_DB=verificacion

# --- Puertos de Exposición Web en LAN ---
# WEB_PORT solo redirige a HTTPS; WEB_TLS_PORT (443) es el puerto real de la aplicación.
WEB_PORT=80
WEB_TLS_PORT=443
# Carpeta con server.crt y server.key (por defecto ./certs/server, ver 3.3).
# CERTS_DIR=./certs/server

# --- Modo de Integración con Equipos de Medición ---
# manual = Captura manual de lecturas reportadas por el equipo
# simulador = EXCLUSIVO DESARROLLO/QA (NUNCA en producción)
EQUIPO_GATEWAY_MODO=manual

# --- Sincronización con el Sistema Central Estatal ---
# Dejar vacío si el centro aún no cuenta con enlace al servidor central
CENTRAL_SYNC_URL=https://central.medioambiente.oaxaca.gob.mx/api/v1/sync
CENTRAL_SYNC_TOKEN=TokenDeAutenticacionCentroReforma01

# --- Políticas de Seguridad y Acceso (X1, X2) ---
LOGIN_MAX_INTENTOS=5
LOGIN_BLOQUEO_MIN=15
SESION_INACTIVIDAD_MIN=30
```

### 3.3 Certificados TLS (obligatorio antes de arrancar)
Todo el tráfico va cifrado: la contraseña del login y el identificador de sesión ya no viajan en claro por la red del verificentro. El `nginx` del stack termina el HTTPS y el puerto 80 solo redirige. Sin certificados, `docker compose up` falla con un error de ruta inexistente (a propósito: es preferible a un nginx reiniciándose sin parar).

**1. Generar la CA local y el certificado del servidor** (requiere `openssl`; en Windows, desde Git Bash o WSL):
```bash
scripts/generar_certificados.sh --hosts "verificentro.local,192.168.1.100"
```
`--hosts` recibe una lista separada por comas, con nombres e IPs mezclados; `localhost` y `127.0.0.1` se incluyen siempre. También se pueden repetir `--host NOMBRE` y `--ip DIRECCION`. **Las estaciones deben abrir el sistema con uno de esos nombres o direcciones**: si usan otro, el navegador avisará que el certificado no coincide.

Valores recomendados:
- **Red local del verificentro:** el nombre `verificentro.local` y la **IP fija del servidor** en la subred del centro. `192.168.1.100` es solo un ejemplo: **cambiarla por la que asigne el router de cada centro**.
- **Nombres `.local`:** se resuelven solo si la red lo permite (mDNS o Bonjour, un registro en el DNS del router o una línea en el archivo `hosts` de cada estación). Si no se resuelve, las estaciones abren el sistema por la IP (`https://192.168.1.100`), que también está en el certificado.
- **Nube (staging) `stg-analizador.verificacionoaxaca.com`:** conviene un certificado público (ver el punto 4), no esta CA. Si aun así se quisiera usar la CA local ahí, se agrega ese nombre (`--hosts "verificentro.local,192.168.1.100,stg-analizador.verificacionoaxaca.com"`) y cada equipo de prueba debe instalar la CA.

El script deja:

| Archivo | Para qué |
|---|---|
| `certs/server/server.crt` y `server.key` | Lo único que monta `nginx` |
| `certs/ca/ca.crt` | CA pública: se instala en cada estación |
| `certs/ca/ca.key` | CA **privada**: guardarla **fuera del servidor** (USB cifrada o gestor de secretos) |

La carpeta `certs/` no se versiona. Al terminar, el script muestra la **huella SHA-256 de la CA**; anótela para comprobarla al instalar la CA en cada estación.

**2. Instalar la CA en cada estación** (una sola vez; después los certificados renovados se aceptan solos):

| Sistema / navegador | Procedimiento |
|---|---|
| Windows con Chrome o Edge | PowerShell como administrador: `Import-Certificate -FilePath .\ca.crt -CertStoreLocation Cert:\LocalMachine\Root` (o `certutil -addstore -f "ROOT" ca.crt`) |
| Firefox | Ajustes → Privacidad y seguridad → Ver certificados → Autoridades → Importar → marcar "Confiar en esta CA para identificar sitios web". O bien, en `about:config`, `security.enterprise_roots.enabled = true` para que use el almacén de Windows |
| Linux | `sudo cp ca.crt /usr/local/share/ca-certificates/verificacion-oaxaca-ca.crt && sudo update-ca-certificates` |

Comprobar siempre que la huella que muestra el sistema coincida con la anotada.

Para no hacerlo a mano, los scripts `scripts/instalar_ca.ps1` (Windows, usa `certutil`) y `scripts/instalar_ca.sh` (Linux) validan que el archivo sea una CA vigente, comparan la huella con `-HuellaEsperada` / `--huella` (la anotada al generar los certificados), instalan solo si coincide y son repetibles; ver `scripts/README.md`, sección 7. En Linux, Chrome y Chromium usan su propia base NSS: ejecutar además `scripts/instalar_ca.sh --nss` como el usuario de la estación.

**3. Renovación.** El certificado del servidor dura 825 días. Anotar la fecha y renovarlo **antes** de que venza (con 60 días de margen):
```bash
openssl x509 -in certs/server/server.crt -noout -enddate        # fecha de vencimiento
scripts/generar_certificados.sh --hosts "verificentro.local,192.168.1.100"   # mismas opciones que la primera vez
docker compose -f docker-compose.prod.yml --env-file .env.prod restart web
```
Como la CA se reutiliza, las estaciones no cambian nada. Solo si se perdiera la CA o se sospechara de su llave se usa `--forzar-ca`, y entonces hay que reinstalar la CA en todas las estaciones. El mismo procedimiento sirve si cambia la IP o el nombre del servidor.

**4. Servidor en la nube (VPS con dominio).** Con un dominio público conviene un certificado público (por ejemplo, Let's Encrypt) en lugar de la CA local. Se obtienen `fullchain.pem` y `privkey.pem` con `certbot`, se dejan copias llamadas `server.crt` (cadena completa) y `server.key` en una carpeta, y se apunta `CERTS_DIR` a ella. Al renovar hay que reemplazar las copias y reiniciar `web`. *Este camino no se ha probado todavía;* si se usara `certbot --webroot`, falta montar en el servicio `web` la carpeta `/var/www/certbot` que el puerto 80 ya expone para el desafío.

**Problemas frecuentes**

| Síntoma | Causa y solución |
|---|---|
| `docker compose up` falla con "bind source path does not exist" | No existen los certificados: ejecutar el paso 1 o revisar `CERTS_DIR` |
| El navegador dice "la conexión no es privada" | La CA no está instalada en esa estación, o se abrió con un nombre o IP que no está en el certificado |
| `web` se reinicia en bucle | `docker compose ... logs web`; suele ser un `server.crt` y `server.key` que no corresponden (volver a generar) |

### 3.4 Puesta en Marcha del Stack
Ejecutar el comando de arranque de Docker Compose:
```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

El despliegue automático realiza las siguientes acciones:
1. Inicia el contenedor de PostgreSQL 16 con verificación de salud (`healthcheck`).
2. Inicia Redis 7 para colas de trabajo.
3. Compila el contenedor backend FastAPI e invoca automáticamente las migraciones pendientes con `alembic upgrade head`.
4. Compila el frontend Vue 3 en Nginx, que sirve la aplicación por HTTPS en el puerto `WEB_TLS_PORT` (443) y redirige el puerto `WEB_PORT` (80) a HTTPS.

### 3.5 Verificación del Despliegue
Verificar que todos los servicios se encuentren en estado `Up (healthy)`:
```bash
docker compose -f docker-compose.prod.yml ps
```
Comprobar que nginx responde por HTTPS con la CA local:
```bash
curl --cacert certs/ca/ca.crt -I https://localhost/
```
Respuesta esperada: `HTTP/2 200` (la pantalla de la aplicación) y, con `curl -I http://localhost/`, un `301` hacia `https://`.

El estado de salud del backend lo informa `docker compose ... ps` (el contenedor `backend` tiene un `healthcheck` sobre `/health`, ruta interna que nginx no expone).

### 3.6 Rol de base de datos de mínimo privilegio (opcional, X5-e)

Por defecto el backend se conecta a PostgreSQL con `POSTGRES_USER`, que es superusuario del contenedor. Si alguien lograra ejecutar código o SQL a través de la aplicación, alcanzaría toda la instancia. Esta sección reemplaza esa conexión por un rol que **solo lee y escribe datos**: no crea ni borra tablas, no administra roles y no puede vaciar tablas.

> **Estado:** preparado y no aplicado en ningún ambiente. **Probado 2026-11-11 contra PostgreSQL 16 real** (contenedor desechable): el script rechaza los 3 casos inválidos (sin `app_user`, contraseña corta, `app_user` = dueño), es repetible, y el rol no puede `TRUNCATE`, `DROP`, `ALTER`, `CREATE TABLE`, `CREATE ROLE` ni leer `alembic_version`. Con el backend conectado como ese rol, el smoke E2E de API (17 pasos) pasó completo, también con `inmutables=1`, y bloqueo/desbloqueo/logout funcionaron sin errores de permisos. `desbloquear_usuario.sh` (con `--simular` y real) también se probó contra esa base. El archivo de Compose combinado no se levantó completo (solo se validó con `docker compose config`). Pruébalo primero en un ambiente de pruebas, con una copia de la base.

Piezas:

| Archivo | Qué hace |
|---|---|
| `scripts/sql/minimo_privilegio.sql` | Crea (o actualiza) el rol de la aplicación y le da los permisos mínimos. Se ejecuta una vez por base; es repetible. |
| `docker-compose.minimo-privilegio.yml` | Segundo archivo de Compose, opcional: corre las migraciones con el dueño en un servicio aparte y arranca el backend con el rol limitado. |
| `APP_DB_USER`, `APP_DB_PASSWORD` | Variables de `.env.prod` con el rol y su contraseña (en `.env.prod.example`, comentadas). |

**Por qué hay un servicio de migraciones aparte.** El backend normalmente ejecuta `alembic upgrade head` al arrancar, y eso exige cambiar el esquema. Con el rol limitado no puede. Con el segundo archivo de Compose, el servicio `migrate` corre las migraciones con las credenciales del dueño y termina; el backend espera a que concluya bien y no recibe nunca la contraseña del dueño. Esto no requiere modificar el código del backend (`alembic` lee `DATABASE_URL_SYNC` y la aplicación lee `DATABASE_URL`, variables distintas).

**Pasos**

1. Con el stack ya instalado y las migraciones aplicadas al menos una vez, elige la contraseña del rol (16 caracteres o más, solo letras y números, para que sirva sin escapar dentro de la URL de conexión) y aplica el SQL **con el mismo usuario que corre las migraciones**:

   ```bash
   read -rsp "Contraseña del rol de la aplicación: " APP_DB_PASSWORD; echo
   { printf '\\set app_user verificacion_app\n\\set app_password %s\n' "'$APP_DB_PASSWORD'"; \
     cat scripts/sql/minimo_privilegio.sql; } \
   | docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db \
       sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -'
   ```

   Debe terminar con `OK: rol verificacion_app creado o actualizado con privilegios mínimos.` El script verifica los permisos y, si algo no queda como se espera, deshace todo. Para que además las bitácoras `event_log` y `access_events` queden de solo escritura, agrega la línea `\set inmutables 1` antes del `cat` (pruébalo antes con la suite completa).
2. Agrega a `.env.prod`: `APP_DB_USER=verificacion_app` y `APP_DB_PASSWORD=` con la misma contraseña.
3. Arranca con los dos archivos:

   ```bash
   docker compose -f docker-compose.prod.yml -f docker-compose.minimo-privilegio.yml \
       --env-file .env.prod up -d --build
   ```

4. Comprueba que el backend funciona (inicio de sesión y un expediente de prueba) y que el rol no es superusuario:

   ```bash
   echo "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = 'verificacion_app';" \
   | docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db \
       sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
   ```

**Importante**

- En **todos** los comandos posteriores hay que repetir los dos `-f` (o el contenedor del backend volvería al modo normal y fallaría al no tener permiso para migrar).
- Los scripts de soporte (`respaldo.sh`, `restaurar.sh`, `desbloquear_usuario.*`) siguen usando `POSTGRES_USER`, como corresponde: son tareas de administración.
- El script quita el permiso de conexión a `PUBLIC` sobre la base. Si usas otro rol para monitoreo, concédele `CONNECT` aparte.
- Las migraciones nuevas que agregue el equipo funcionan sin repetir el SQL: los permisos se asignan por defecto a las tablas que cree el dueño.
- La contraseña pasa por la entrada estándar y no queda en el historial del shell, pero el SQL la recibe en claro: si activas `log_statement = all` en PostgreSQL, quedaría en el registro del servidor.
- **Volver al modo normal:** omitir el segundo `-f` y reiniciar. El rol puede quedarse o eliminarse con `DROP OWNED BY verificacion_app; DROP ROLE verificacion_app;` ejecutado como dueño.

---

## 4. Configuración y Roles de Estaciones

Cada equipo cliente en la red local se identifica mediante su identificador de dispositivo (`device_identifier`) registrado en el catálogo `cat_estaciones`.

| Tipo de Estación | Vista Asignada | Permisos Requeridos | Responsabilidades |
|---|---|---|---|
| **CAPTURA** | `/captura` | Operador Captura | Búsqueda en SIOX, captura de datos vehiculares y emisión a línea. |
| **PRUEBA** | `/prueba` | Técnico Verificador | Inspección visual, OBD, gases NOM-041 / opacidad NOM-045. |
| **IMPRESION** | `/impresion` | Operador Impresión | Asignación de folio, validación de tipo, impresión física y entrega. |
| **SUPERVISION** | `/supervision` | Supervisor del Centro | Gestión de incidencias, reintentos, reimpresión, canjes y parámetros. |

---

## 5. Manual de Operación Diaria por Estación

### 5.1 Políticas de Seguridad de Acceso (X1, X2, X6)
1. **Complejidad de Contraseña:** Mínimo 8 caracteres, al menos una letra y un número. No se permiten contraseñas triviales ni iguales al nombre de usuario.
2. **Bloqueo por Intentos Fallidos (X1):** Al acumular 5 contraseñas erróneas consecutivas, la cuenta queda bloqueada temporalmente durante 15 minutos (código HTTP 429).
3. **Caducidad por Inactividad (X2):** Tras 30 minutos sin actividad interactiva, la sesión concluye automáticamente requiriendo reautenticación.

### 5.2 Estación de Captura
1. Iniciar sesión con usuario asignado a la estación de captura.
2. Ingresar placa o NIV para consultar los datos vehiculares en el padrón estatal (SIOX).
3. En caso de contingencia o vehículo foráneo sin registro previo, proceder con la captura manual fidedigna de la tarjeta de circulación.
4. Asignar la línea operativa disponible y confirmar el envío a prueba técnica.

### 5.3 Estación de Prueba
1. Seleccionar el expediente formado en la cola de la línea.
2. Realizar la **Inspección Visual** de componentes vehiculares (fugas, estado de neumáticos, escape).
3. Registrar diagnóstico **OBD/SBD** (monitores de diagnóstico vehicular).
4. Para vehículos a diésel, validar obligatoriamente el **Checklist NOM-045** de 6 puntos de seguridad previa.
5. Iniciar la prueba de emisiones (dinámica o estática según corresponda).
6. **Manejo de Falla de Equipo (HU-054 / HU-083):** Si el analizador o dinamómetro pierde comunicación durante la prueba, el expediente transiciona al estado `ERROR_INTEGRACION` y se notifica al monitor de Supervisión. La prueba queda pausada y no avanza hasta que el Supervisor autorice el reintento explícito (`POST /api/pruebas/reintentar/{id}`).

### 5.4 Estación de Impresión Central
1. Visualizar la cola central de vehículos terminados.
2. **Filtro de Resultado Técnico (HU-057):** Utilizar el selector para aislar aprobados o distinguir rechazos por prueba física frente a rechazos visuales.
3. **Asignación de Folio:** Hacer clic en "Solicitar folio" para descontar el siguiente folio numérico consecutivo del inventario local del tipo correspondiente.
4. **Regla Crítica N2 (Tipo de Verificación):** Si el padrón vehicular no suministró el tipo de verificación (Ordinaria, Extemporánea, Voluntaria o Reposición), el operador debe seleccionarlo obligatoriamente en pantalla; el botón de impresión permanecerá deshabilitado hasta cumplir esta regla.
5. **Generar Vista Previa:** Validar en pantalla la alineación de datos del certificado contra el número de folio asignado.
6. **Manejo de Folio Dañado:** Si el papel valorado sufre un daño físico antes de imprimir (atasco en bandeja), utilizar el botón *"Marcar folio dañado"*; el sistema registrará el folio como dañado y consumirá el siguiente folio válido sin requerir supervisor.
7. **Impresión y Cierre Formal (HU-059):** Al enviar a impresión física, el expediente pasa al estado `IMPRESO`. Tras comprobar físicamente la correcta salida del certificado y entregar la documentación al ciudadano, hacer clic en *"Cerrar expediente"* para sellar de forma definitiva e inmutable el trámite.

### 5.5 Estación de Supervisión
1. **Monitor de Incidencias:** Supervisar rechazos, errores de sincronización y fallas de equipo en la pestaña *"Errores y reintentos"*.
2. **Autorización de Reintentos:** Desbloquear expedientes con problemas de hardware o fallas de impresora previa inspección física en línea.
3. **Reimpresión por Daño:** Atender solicitudes de reimpresión de certificados entregados que hayan sufrido deterioro, asentando el motivo formal de canje y registrando el nuevo folio asignado.

---

## 6. Procedimiento ante Contingencias y Pérdida de Internet

El sistema cuenta con resiliencia total frente a cortes del enlace estatal de internet (HU-104):

1. **Detección Automática:** El indicador en la barra superior (`TopAppBar`) cambiará automáticamente al estado:
   ```text
   [mdi-wifi-off] Operando sin internet · N pendientes
   ```
2. **Continuidad Operativa:** El centro **NO debe suspender operaciones**. Las capturas, pruebas, asignaciones de folio e impresiones continúan ejecutándose normalmente contra la base de datos local.
3. **Cola de Salida (`sync_outbox`):** Cada evento y medición queda registrado con firma de integridad SHA-256 en la cola transaccional local.
4. **Restablecimiento del Servicio:** Al volver la conectividad, el servicio de sincronización en segundo plano drenará progresivamente los registros pendientes hacia el servidor central. El supervisor también puede forzar el reintento inmediato mediante el botón *"Sincronizar ahora"*.
5. **Un solo proceso de backend:** el bucle de sincronización corre dentro de cada proceso de uvicorn. La imagen de producción arranca con `--workers 1`; no aumentar ese número, porque cada proceso extra repetiría los envíos al central (son idempotentes, pero duplican tráfico y bloqueos).

---

## 7. Política de Respaldos y Restauración de Base de Datos (D4)

La base de datos PostgreSQL local almacena el registro legal y formal de los certificados emitidos. Debe asegurarse un respaldo periódico diario. En el servidor (Linux) se usan `scripts/respaldo.sh` y `scripts/restaurar.sh`, que trabajan sobre el stack de producción (`docker-compose.prod.yml` y `.env.prod`) y se ejecutan **desde la raíz del repositorio**. Los scripts de PowerShell (`backup_db.ps1`, `restore_db.ps1`) son solo para desarrollo en Windows y producen otro formato (`.dump`): sus archivos no se restauran con los scripts de Linux.

### 7.1 Respaldo automatizado diario
```bash
scripts/respaldo.sh /var/respaldos/verificacion
```
Deja un archivo `verificacion_AAAAMMDD_HHMMSS.sql.gz`, comprueba que esté íntegro (`gzip -t`) y que no esté vacío, y conserva los últimos 14 (`RETENCION=n` para cambiarlo). Programarlo con `cron` (diario, 02:00):

```bash
0 2 * * * cd /ruta/verificacion-oaxaca && scripts/respaldo.sh /var/respaldos/verificacion
```
Copiar los archivos **fuera del servidor** con regularidad: un respaldo en el mismo disco no protege de la falla del disco.

### 7.2 Comprobar que un respaldo se puede restaurar
Que el archivo esté íntegro no prueba que sirva. Se comprueba cargándolo en una base temporal, sin tocar la real:

```bash
COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod"
ARCHIVO=/var/respaldos/verificacion/verificacion_AAAAMMDD_HHMMSS.sql.gz

$COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE verificacion_prueba"'
gzip -dc "$ARCHIVO" | $COMPOSE exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d verificacion_prueba'
$COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d verificacion_prueba -c "SELECT count(*) FROM verificaciones"'
$COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE verificacion_prueba"'
```
La cuenta debe coincidir (o ser algo menor, si se registró trabajo después del respaldo) con la de la base real. Hacerlo periódicamente y siempre antes de una actualización (sección 8).

### 7.3 Procedimiento de restauración
```bash
scripts/restaurar.sh /var/respaldos/verificacion/verificacion_AAAAMMDD_HHMMSS.sql.gz
```
Pide escribir `SI` porque **borra la base actual**: detiene el backend, la recrea, carga el respaldo y vuelve a iniciar el backend. Después, comprobar el estado del stack como se indica en la sección 3.5.

---

## 8. Actualización del Stack en Producción Conservando los Datos (D10)

Procedimiento para pasar el servidor de una versión a otra sin perder los registros: **respaldo previo verificado → actualización de imágenes y migraciones → verificación → rollback si algo falla**. Las migraciones de base de datos (`alembic upgrade head`) se aplican solas al arrancar el backend.

> **Estado:** procedimiento redactado a partir de los scripts y de la configuración del repositorio. **No se ha ejecutado de punta a punta con datos reales** y los comandos de Compose no se corrieron al redactarlo. Ensayarlo primero en un ambiente aparte (un servidor de pruebas con una copia de un respaldo) antes de la primera actualización real.

**Antes de empezar**
- La actualización **detiene el servicio**: las estaciones no pueden operar mientras dura. Hacerla fuera del horario de verificación y avisar.
- Todos los comandos asumen la variable `COMPOSE` de abajo. Si se usa el rol de base de datos de mínimo privilegio (sección 3.6), agregar `-f docker-compose.minimo-privilegio.yml` en **todos** los comandos `$COMPOSE`, también en el rollback (`scripts/restaurar.sh` es la excepción: usa fijo `docker-compose.prod.yml`, lo cual basta porque solo toca la base de datos).
- El servidor construye las imágenes (`--build`): necesita acceso a internet para bajar imágenes base y dependencias. Si la red del verificentro es limitada, ejecutar `$COMPOSE build` **antes** de la ventana, con el servicio aún en marcha, y dejar solo `up -d` para la ventana.

```bash
COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod"
VERSION=<etiqueta o rama de la versión nueva>
```

### 8.1 Preparación (antes de la ventana)
1. Anotar la versión actual del código y la revisión de la base de datos (con el rol de mínimo privilegio, `alembic` no puede leer su propia tabla, por eso se consulta desde `db`):
   ```bash
   git rev-parse --short HEAD
   $COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT version_num FROM alembic_version"'
   ```
2. Traer la versión nueva **sin aplicarla** y revisar qué cambia, sobre todo migraciones, Compose y variables:
   ```bash
   git fetch origin --tags
   git log --oneline HEAD.."$VERSION"
   git diff --stat HEAD "$VERSION" -- backend/alembic/versions docker-compose.prod.yml .env.prod.example frontend/nginx.conf
   ```
3. Agregar a `.env.prod` las variables que la versión nueva requiera (`git diff HEAD "$VERSION" -- .env.prod.example`). Una variable obligatoria que falte hace que `docker compose` se niegue a arrancar, y se detecta en el paso 8.2.4.
4. Leer las notas de cambio de la versión: algunas migraciones imponen condiciones sobre los datos. Por ejemplo, `e1f4a8c2d5b9` falla si hay dos usuarios que solo difieren en mayúsculas; se comprueba antes con:
   ```bash
   $COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT lower(username), count(*) FROM cat_usuarios GROUP BY 1 HAVING count(*) > 1"'
   ```
5. Recomendado, sobre todo la primera vez: ensayar en un ambiente aparte (restaurar una copia reciente del respaldo, arrancar la versión nueva y comprobar que las migraciones corren y que los datos siguen ahí).

### 8.2 Ventana de actualización
1. **Cerrar el servicio** para que no se escriba nada durante el respaldo:
   ```bash
   $COMPOSE stop web backend
   ```
2. **Respaldo previo**, verificado (sección 7.2) y con los conteos anotados:
   ```bash
   scripts/respaldo.sh /var/respaldos/verificacion
   $COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT (SELECT count(*) FROM verificaciones) AS verificaciones, (SELECT count(*) FROM folios) AS folios, (SELECT count(*) FROM sync_outbox) AS sync_outbox, (SELECT count(*) FROM cat_usuarios) AS usuarios"'
   ```
   Copiar ese archivo fuera del servidor y anotar su nombre: **es el punto de retorno**. Conservarlo hasta haber comprobado la versión nueva; no dejar que la rotación lo borre.
3. **Actualizar el código:**
   ```bash
   git checkout "$VERSION"
   ```
4. **Validar la configuración** (falla con un mensaje claro si falta una variable obligatoria):
   ```bash
   $COMPOSE config -q
   ```
5. **Construir y arrancar.** El backend aplica las migraciones pendientes al iniciar (con el Compose de mínimo privilegio lo hace el servicio `migrate`):
   ```bash
   $COMPOSE up -d --build
   $COMPOSE logs -f backend
   ```
   Esperar a ver `Application startup complete` en el backend. Si aparece un error de migración, ir directamente a 8.4.

### 8.3 Verificación posterior
- `$COMPOSE ps`: todos los servicios en `Up` y el backend `healthy`.
- La versión de la base coincide con la de la versión nueva: la consulta `SELECT version_num FROM alembic_version` (la del paso 8.1.1) debe devolver el mismo valor que `$COMPOSE exec -T backend alembic heads`.
- Repetir la consulta de conteos del paso 8.2.2: ninguno puede ser **menor** que el anotado.
- `curl --cacert certs/ca/ca.crt -I https://localhost/` responde `HTTP/2 200`.
- Desde una estación: iniciar sesión como supervisor, abrir un expediente existente y comprobar que sus datos están completos; en Supervisión, revisar las pendientes de sincronización.
- Revisar el registro unos minutos: `$COMPOSE logs --since 10m backend`, sin errores repetidos.
- **No** ejecutar en producción `scripts/smoke_e2e_flujo.mjs` ni `scripts/smoke_e2e_ui.mjs`: crean expedientes de prueba y consumen un folio. Son solo para pruebas.

Si todo está bien, anotar la actualización (fecha, versión anterior y nueva, archivo del respaldo previo).

### 8.4 Rollback
Cuándo: una migración falla, el backend no queda `healthy`, la verificación 8.3 no pasa o se detecta pérdida de datos.

Se vuelve atrás **restaurando el respaldo previo**, no con `alembic downgrade`: hay migraciones que se aplican por partes (por ejemplo las que agregan valores a un tipo de PostgreSQL) y una migración fallida puede dejar la base a medias, y un `downgrade` no devuelve los datos modificados.

1. Guardar el registro del fallo para diagnosticarlo después: `$COMPOSE logs backend > /var/respaldos/fallo_actualizacion.log`
2. Detener y quitar los contenedores, **conservando el volumen de datos**:
   ```bash
   $COMPOSE down
   ```
   **Nunca** agregar `-v` ni `--volumes`: borraría la base de datos.
3. Volver al código anterior (el commit anotado en 8.1.1):
   ```bash
   git checkout <commit anotado>
   ```
4. Levantar **solo la base de datos** y esperar a que `$COMPOSE ps` la muestre `healthy`:
   ```bash
   $COMPOSE up -d db
   ```
   No arrancar todavía el backend ni `migrate`: con la base aún en el esquema nuevo, las migraciones de la versión anterior fallarían (y con el Compose de mínimo privilegio, `migrate` fallido impide que el backend arranque).
5. Restaurar el respaldo previo:
   ```bash
   scripts/restaurar.sh /var/respaldos/verificacion/verificacion_AAAAMMDD_HHMMSS.sql.gz
   ```
   Pide escribir `SI`, detiene el backend (que aquí aún no existe), recrea la base y carga el respaldo. Este script usa fijo `docker-compose.prod.yml` y `.env.prod`, sin el archivo de mínimo privilegio, lo cual basta porque solo toca la base de datos. Su último paso inicia el backend, y como en este punto no hay contenedor de backend es posible que termine con un aviso o un error en ese paso: la restauración ya se hizo antes. Comprobarlo con la consulta de revisión (`alembic_version`) y la de conteos de 8.2.2, y continuar.
6. **Solo si se usa el rol de mínimo privilegio** (sección 3.6): volver a aplicar `scripts/sql/minimo_privilegio.sql` (paso 1 de 3.6, con la misma contraseña de `APP_DB_PASSWORD`). Restaurar borra y recrea la base, y un respaldo de `pg_dump` no conserva los permisos a nivel de base de datos (el `REVOKE` y `GRANT CONNECT ON DATABASE` del script): sin este paso la aplicación funciona, pero la base queda más abierta que antes. El script es repetible, así que no estorba si ya estaban.
7. Levantar el stack con la versión anterior (el servicio `migrate`, si se usa, no tendrá nada que migrar):
   ```bash
   $COMPOSE up -d --build
   ```
8. Repetir la verificación 8.3: `alembic_version` debe mostrar la revisión anterior y los conteos deben coincidir con los anotados antes de actualizar.

Notas del rollback:
- Todo lo registrado entre el respaldo y el rollback se pierde; por eso el servicio se cierra durante la ventana (8.2.1).
- Los registros de `sync_outbox` que la versión nueva alcanzó a enviar al sistema central se reenviarán: el envío es idempotente, el duplicado es inofensivo.
- Reconstruir la versión anterior usa la caché de capas de Docker si no hay internet. No ejecutar `docker system prune` hasta haber comprobado la versión nueva.
- Si el rollback también falla, conservar el servidor apagado y el respaldo intacto, y escalar con el equipo de desarrollo antes de borrar nada.
