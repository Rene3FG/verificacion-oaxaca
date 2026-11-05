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

---

## 7. Política de Respaldos y Restauración de Base de Datos (D4)

La base de datos PostgreSQL local almacena el registro legal y formal de los certificados emitidos. Debe asegurarse un respaldo periódico diario.

### 7.1 Respaldo Automatizado Diario
Crear una tarea programada en el servidor local (`/etc/cron.daily/respaldo_verificacion.sh`):

```bash
#!/bin/bash
FECHA=$(date +%Y%m%d_%H%M%S)
DESTINO="/var/backups/verificacion"
mkdir -p "$DESTINO"

docker exec -t verificacion-oaxaca-db-1 pg_dump -U verificacion -F c verificacion > "$DESTINO/respaldo_${FECHA}.dump"
find "$DESTINO" -name "respaldo_*.dump" -mtime +30 -delete
```

### 7.2 Procedimiento de Restauración
Para restaurar la base de datos a partir de un respaldo:

1. Detener los servicios operativos:
   ```bash
   docker compose -f docker-compose.prod.yml stop backend web
   ```
2. Restaurar el archivo `.dump` en la base de datos:
   ```bash
   docker exec -i verificacion-oaxaca-db-1 pg_restore -U verificacion -d verificacion --clean --if-exists < /var/backups/verificacion/respaldo_FECHA.dump
   ```
3. Reiniciar el stack completo:
   ```bash
   docker compose -f docker-compose.prod.yml restart
   ```
4. Comprobar la integridad ejecutando el healthcheck:
   ```bash
   curl http://localhost/api/health
   ```
