# Reporte de coordinación técnica para René

**De:** Sebas
**Para:** René
**Fecha:** 2026-11-05
**Rama:** `frontend-impresion-central`, sincronizada con `origin` en `77a2f95`
**Alcance:** lo que quedó listo de nuestro lado y lo que necesita tu decisión o tu trabajo en `backend/**` y en las vistas que son tuyas. No modifiqué nada de tu código.

---

## 1. Resumen: qué necesito de ti, en orden

| # | Qué | Tipo | Esfuerzo | Detalle |
|---|---|---|---|---|
| 1 | Conocer el cambio de despliegue: sin certificados, `docker compose up` ya no arranca | Aviso | — | Sección 2 |
| 2 | Elegir cómo registrar la auditoría administrativa (`event_log` nullable o `admin_event_logs`) | **Decisión** | — | 3.1 |
| 3 | Elegir la Opción A o B de la inspección visual (NOM-047) | **Decisión** | — | 4 |
| 4 | Campo 001 del certificado: tomar el técnico desde `operador_id` (ya definido por el cliente; confirmar que se imprime el `username`) | Backend | Bajo | 4.3 |
| 5 | Endpoint de desbloqueo `POST /api/usuarios/{id}/desbloquear` | Backend | Bajo a medio | 3.2 |
| 6 | IP real en `access_events` y bloqueo por (usuario, IP) | Backend | Medio | 3.3 |
| 7 | Vencimiento absoluto de sesión | Backend | Bajo | 3.4 |
| 8 | Contraseñas comunes ampliadas, cambio propio y `must_change_password` | Backend | Medio | 3.5 |
| 9 | Corregir el manejo de `localStorage` bloqueado en `session.js` (3 líneas) | Defecto | Bajo | 5 |
| 10 | Pendientes menores y pruebas de 403 | Backend | Medio | 3.6 y 3.7 |

Orden sugerido: primero las tres decisiones (2, 3 y 4), porque desbloquean el resto, y después 7 y 9, que son las más rápidas.

---

## 2. Aviso de despliegue: cambia el flujo de instalación

Hay **dos cambios** que afectan a quien despliegue con `docker-compose.prod.yml`:

1. **Los certificados TLS son obligatorios.** nginx termina el HTTPS en el puerto 443 y el 80 solo redirige (`3d52483`). Sin `certs/server/server.crt` y `server.key`, `docker compose up` falla con un error de ruta inexistente (a propósito: es preferible a un nginx reiniciándose sin parar).
2. **`POSTGRES_PASSWORD` es obligatoria** (`5043f4e`). El compose falla con un mensaje claro si falta o está vacía, y `.env.prod.example` ya no trae contraseña de relleno.

Pasos de instalación nuevos:

```bash
# 1. CA local y certificado del servidor (requiere openssl; en Windows, Git Bash o WSL)
scripts/generar_certificados.sh --hosts "verificentro.local,192.168.1.100"

# 2. Variables: definir POSTGRES_PASSWORD (obligatoria) y, si hace falta, WEB_TLS_PORT y CERTS_DIR
cp .env.prod.example .env.prod

# 3. Levantar
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

- `--hosts` recibe una lista separada por comas con nombres e IPs mezclados; `localhost` y `127.0.0.1` van siempre. También se pueden repetir `--host NOMBRE` y `--ip DIRECCION`. La IP `192.168.1.100` es un ejemplo: cada centro usa la que asigne su router.
- El script crea una CA propia en `certs/ca/` y el certificado en `certs/server/`. Solo `certs/server/` se monta en nginx; **la llave de la CA nunca entra al contenedor** y debe guardarse fuera del servidor. `certs/` no se versiona.
- Las estaciones instalan la CA una sola vez (procedimiento en `docs/MANUAL_INSTALACION_Y_OPERACION.md`, sección 3.3). Renovar el certificado es volver a ejecutar el script con las mismas opciones: si la CA existe se reutiliza y las estaciones no cambian nada.
- Todos los comandos de `docker compose -f docker-compose.prod.yml` necesitan `--env-file .env.prod`, porque la contraseña ahora es obligatoria al interpretar el archivo. Tus `respaldo.sh` y `restaurar.sh` ya lo pasan, así que no se ven afectados.
- Tus `respaldo.sh` y `restaurar.sh` conviven con nuestros `backup_db.*` y `restore_db.*`. Cuando puedas, definamos cuál juego queda como oficial.
- El desarrollo local no cambia: `docker-compose.yml` no pasa por nginx.

Otros cambios en nginx que conviene conocer: límite de 30 peticiones por minuto por IP en `POST /api/estaciones/login` (la respuesta 429 es un JSON con `detail`), cabeceras de seguridad, `X-Real-IP` y `X-Forwarded-For` fijados con la IP real del cliente, y una `Content-Security-Policy` **en modo solo reporte**.

---

## 3. Tareas de backend derivadas de la auditoría de seguridad

Fuente: `docs/AUDITORIA_SEGURIDAD_X1_X7.md`. Ninguna de estas tareas existe hoy: lo verifiqué con `grep` en `backend/app` (0 coincidencias de `desbloquear`, `X-Real-IP`, vencimiento absoluto, `clave_tecnico`, auditoría administrativa y `must_change_password`).

### 3.1 Auditoría de acciones administrativas (decisión tuya)

**Problema.** `usuarios`, `permisos`, `parametros`, `equipos` y `folios` tienen 0 escrituras de bitácora. No queda registrado quién creó un usuario, restableció una contraseña, otorgó un permiso de supervisor, cambió un parámetro (por ejemplo `certificado_rechazo_dias_vigencia`) o registró un lote de folios.

**La decisión del equipo fue usar `EventLog`** (`modulo="administracion"`, `evento="usuario_creado"`, etc.) para tener una sola bitácora transaccional. Eso **no se puede hacer sin cambios en el backend**, porque `EventLog.verificacion_id` es `NOT NULL` con clave foránea, y tres sitios asumen un expediente:

| Sitio | Qué pasaría con un evento sin expediente |
|---|---|
| `services/sync.py` · `_serializar_event_log` | `str(event.verificacion_id)` enviaría `"None"` al central |
| `api/routers/supervision.py` · auditoría (`join(Verificacion, ...)`) | El `JOIN` interno **descartaría en silencio** esos eventos |
| Filtro por centro de esa misma auditoría | El centro sale de `Verificacion`; un evento administrativo no tiene |

**Opción 1: `event_log.verificacion_id` nullable.** Migración, `_serializar_event_log` tolerante a `None`, `LEFT JOIN` en la auditoría y el centro guardado en el evento (columna `centro_id` o `detalle_json`). Una sola bitácora, pero se toca algo que usan los flujos de expediente.
**Opción 2: tabla `admin_event_logs`.** No toca `event_log` ni los flujos de expediente, pero necesita su propia sincronización y su propio endpoint de consulta para el supervisor.

Ambas son viables. Dime cuál prefieres; mi recomendación es la opción 2 si quieres aislar el riesgo y la 1 si pesa más tener una sola bitácora.

**Qué registrar** (sin contraseñas ni valores secretos, solo el hecho, el actor y los campos afectados): alta de usuario, restablecimiento de contraseña, activar y desactivar; alta, cambio y baja de permisos; cambio de parámetros; alta y edición de equipos; registro de lotes de folios.

**Criterio de aceptación:** cada una de esas acciones deja un evento con actor, fecha, centro y descripción, visible en la auditoría del supervisor, y el central lo recibe sin error. **Pruebas:** una por acción.

### 3.2 `POST /api/usuarios/{id}/desbloquear`

**Contexto.** El bloqueo de login (5 fallos, 15 min) se calcula en `estaciones.py::_segundos_de_bloqueo` contando los `AccessEvent` `DENEGADO` con motivo `Credenciales inválidas` posteriores al último `PERMITIDO`. Hoy no hay vía por API para destrabar a un operador; la decisión del equipo es que lo destrabe el supervisor del centro.

**Propuesta.**
- Agregar el valor `DESBLOQUEO` al enum `access_event_resultado` (en PostgreSQL, `ALTER TYPE ... ADD VALUE`; en Alembic conviene ejecutarlo dentro de `autocommit_block()`, porque el valor nuevo no se puede usar en la misma transacción que lo crea).
- El endpoint (`requiere_supervisor`) inserta un `AccessEvent(resultado=DESBLOQUEO, user_id=<objetivo>, session_id=<sesión del supervisor>)`, de modo que queda quién lo hizo, y `_segundos_de_bloqueo` toma el más reciente entre `PERMITIDO` y `DESBLOQUEO` como punto de reinicio.
- Un supervisor bloqueado no puede autenticarse para llamar al endpoint; para ese caso existe `scripts/desbloquear_usuario.sh` y `.ps1` (`309fb5d`), que anota `(desbloqueado por soporte)` en el motivo de los intentos fallidos. Cuando exista el endpoint, el script puede adoptar el mismo mecanismo de `DESBLOQUEO`.

**Pruebas:** 5 fallos dan 429; el supervisor desbloquea y el login funciona; un no supervisor recibe 403; un usuario inexistente da 404; queda el evento.

### 3.3 IP real en `access_events` y bloqueo por (usuario, IP)

**Problema.** `ip_address` y `device_fingerprint` los manda el cliente en el cuerpo del login; el frontend **no los manda nunca** (siempre `NULL`) y el backend no lee `request.client`. La bitácora de accesos no tiene un origen fiable, y sin él no se puede limitar por IP ni investigar un incidente.

**Propuesta.**
- Una función `ip_cliente(request)` que tome `X-Real-IP` si existe y, si no, `request.client.host`. nginx ya fija `X-Real-IP` y `X-Forwarded-For` con `$remote_addr` en todo `/api/` (`1bd0eba`), y en producción el backend no publica puertos, así que solo nginx puede alcanzarlo. Si prefieres no depender del encabezado, la alternativa es arrancar uvicorn con `--forwarded-allow-ips` apuntando a la red de Compose.
- Guardar esa IP en `access_events.ip_address` y `station_sessions.ip_address`, e **ignorar** el campo del cuerpo (se puede eliminar de `LoginRequest`).
- Con eso, bloquear por **pareja (usuario, IP)** en lugar de solo por usuario, más un contador por IP para fallos con usuarios inexistentes. Evita que alguien bloquee a un supervisor desde otra máquina y da tope al *password spraying*.
- En el mismo cambio: ejecutar `verify_password` contra un hash ficticio cuando el usuario no existe (iguala tiempos de respuesta) y serializar por usuario con `pg_advisory_xact_lock` para que peticiones simultáneas no excedan el límite.

**Pruebas:** usuario inexistente con 6 intentos; bloqueo por (usuario, IP) sin afectar a otra IP; la IP sale de la conexión y no del cuerpo.

### 3.4 Vencimiento absoluto de sesión

**Problema.** La sesión solo expira por inactividad (30 min). Una sesión con actividad continua nunca vence, y un identificador robado y usado a diario dura indefinidamente.

**Propuesta.** Variable `SESION_DURACION_MAX_H` (por ejemplo 12 h, un turno; `0` la apaga) en `config.py`, en el compose y en `.env.prod.example`, evaluada en `get_current_session` contra `login_at`, con el mismo 401 y el estado `expirada`. **Pruebas:** sesión activa que supera el máximo absoluto.

### 3.5 Contraseñas

**Problema.** La política (`services/auth.py`) solo rechaza una lista de 16 contraseñas y compara la cadena completa. Hoy **se aceptan** `Password123`, `Oaxaca2026`, `Abcd1234`, `Verificentro1`, `12345678a`, `Operador2026` y `Admin2026`. Además, el supervisor fija las contraseñas ajenas y por tanto las conoce, y no existe cambio por el propio usuario.

**Propuesta.**
1. Ampliar la lista de comunes con un diccionario de unas miles de entradas empaquetado en el repositorio, y rechazar contraseñas que **contengan** el usuario, el nombre del centro, "oaxaca" o "verificacion".
2. `POST /api/usuarios/me/password`, que exija la contraseña actual.
3. Columna `must_change_password`, activa al crear o restablecer, para que el supervisor deje de conocer la contraseña definitiva. Pendiente de confirmar con el equipo si se acepta que el supervisor conozca las iniciales; mientras tanto es recomendable.
4. Sin caducidad periódica forzada (la guía NIST SP 800-63B la desaconseja salvo sospecha de compromiso). Sí cambiar y cerrar sesiones al restablecer.
5. Normalizar el usuario a minúsculas con unicidad sin distinguir mayúsculas (hoy `Admin` y `admin` son cuentas distintas).

**Pruebas:** los casos de la lista anterior deben rechazarse; contraseña que contiene el usuario; cambio propio con y sin la actual correcta; `must_change_password`.

### 3.6 Pendientes menores

- **Cerrar sesiones** del usuario al revocar o cambiar un permiso y al restablecer su contraseña (la misma instrucción `UPDATE station_sessions` que ya usa `actualizar_usuario` al desactivar). Hoy un permiso revocado no corta la sesión abierta.
- **Guarda de entorno en `seed.py`**: crea `supervisor1` con contraseña pública y no comprueba el entorno. Ejecutarlo por error en producción dejaría un supervisor con contraseña conocida (`APP_ENV` o `--forzar`).
- **Apagar `/docs`, `/redoc` y `/openapi.json` en producción** (`docs_url=None` según una variable).
- **Reducir `WorkstationRead`** en `GET /api/estaciones/{device_identifier}` (público): solo `id`, `name`, `station_type`, `center_id`, `line_id` y `allowed_line_ids`. Hoy expone también `capacidad_dinamometro_kg` y `is_centralized`.
- **Validar que el usuario exista** en `POST /api/permisos` (hoy acepta un `user_id` inexistente; la tabla no tiene clave foránea).
- **Fallar cerrado** en `get_current_session` si el usuario no existe (hoy deja pasar una sesión huérfana).
- **Rol de BD de mínimo privilegio** en lugar del superusuario del contenedor (puede ir en `bootstrap_prod`).
- Puertos de desarrollo en `127.0.0.1` en `docker-compose.yml` (lo hago yo si estás de acuerdo).

### 3.7 Pruebas

- **Una prueba que recorra todas las rutas** (`app.routes`), llame a cada una sin `X-Session-Id` y exija 401, con una lista blanca explícita de las 3 públicas (`POST /api/estaciones/login`, `GET /api/estaciones/{device_identifier}`, `GET /health`). Falla en cuanto alguien agregue una ruta sin guarda. Hoy: 71 de las 74 rutas tienen guarda.
- **Pruebas de 403** para las rutas que **modifican** datos. De las 32 rutas de supervisor, 13 no tienen la suya: `usuarios` PATCH, `permisos` POST/PATCH/DELETE, `parametros` PATCH, `estaciones` PATCH, `equipos` GET tipos/POST/PATCH, `folios/inventario`, `pruebas/limites-emision` GET, prórroga de semestre y bitácora. La lista completa con las de estación está en el Anexo A de la auditoría.
- Opcional: poner la dependencia de sesión a nivel de `include_router` para todos los routers salvo `estaciones`, de modo que una ruta nueva nazca protegida aunque se olvide la guarda.

---

## 4. NOM-047: inspección visual y campo 001

Detalle completo en `docs/PROPUESTA_FLUJO_INSPECCION_VISUAL_NOM047.md`. Lo que el cliente respondió el 2026-10-30 (reportado por el equipo): la inspección visual va antes de terminar la captura; un componente que falla es rechazo directo sin prueba de emisiones; el OBD va antes de la prueba; el campo 001 del certificado es el ID del técnico; y las plantillas son las mismas para aprobados y rechazados.

### 4.1 Lo que ya se cumple

Revisé `state_machine.py` y **casi todo existe**: `INSPECCION_VISUAL_RECHAZADA` pasa a `PENDIENTE_DE_IMPRESION_RECHAZO` en la misma petición, y `INSPECCION_VISUAL_APROBADA` pasa por `OBD_*` antes de `LISTO_PARA_PRUEBA`. No hacen falta estados nuevos. Lo que cambia es **qué estación registra la inspección visual**: hoy Prueba (`inspeccion.py` exige `StationType.PRUEBA`) y el cliente indica Captura.

### 4.2 Decisión: Opción A u Opción B

- **Opción A (recomendada): mover la estación sin tocar la máquina de estados.** La inspección sigue después de normalizar, pero la hace la caseta. Cambios: `inspeccion.py` (`GET /checklist` y `POST /{id}`) pasa de `requiere_estacion(PRUEBA)` a `requiere_estacion(CAPTURA)` (o a ambas durante la transición, como ya hace `datos-certificado`); revisar que la cola de Prueba empiece en `INSPECCION_VISUAL_APROBADA`; en `CapturaView.vue`, agregar `INSPECCION_VISUAL_PENDIENTE` a `ESTADOS_CAPTURA`, el paso del checklist y el subtítulo del paso "Inspección visual" (hoy dice "Estación de Prueba"); en `PruebaView.vue`, quitar `INSPECCION_VISUAL_PENDIENTE` de `ESTADOS_PRUEBA` y el bloque del checklist.
- **Opción B: reordenar los estados** para que la inspección ocurra antes de `DATOS_NORMALIZADOS`. Toca `ALLOWED_TRANSITIONS`, `ESTADOS_NORMALIZABLES`, `CANCELABLE_FROM`, `/normalizar` y las colas, y obliga a decidir qué hacer con expedientes en vuelo al desplegar. Solo vale la pena si el cliente quiere la inspección **antes de confirmar los datos** (pregunta abierta con el cliente).

**Mi parte cuando decidas:** mover a `CapturaView.test.js` las 7 pruebas del bloque de inspección y las 3 de avisos que llaman a `registrarInspeccion` (hoy en `PruebaView.test.js`), y ajustar la matriz de trazabilidad. **No toco** `CapturaView.vue`, `PruebaView.vue` ni `backend/**`.

### 4.3 Campo 001 = ID del usuario (RESUELTO por el cliente el 2026-11-06)

Don Rubén (el cliente) confirmó: el 001 es el **identificador del usuario del sistema**. En un certificado aprobatorio va el técnico que hizo la prueba de emisiones; en uno de rechazo, el técnico que emitió el rechazo (inspección visual o fin de la prueba de emisiones). Esto respalda además la **Opción A**: en su sistema actual la inspección visual es el último paso de la captura.

Hoy el 001 sale del parámetro fijo `certificado_numero_equipo` (`certificado.py`, clave de layout `equipo_numero`), igual para todos. Con la respuesta del cliente **ya no hace falta la columna `clave_tecnico`** que proponía este reporte: se resuelve con datos existentes.

**Propuesta simplificada.**
1. Al generar la proyección del certificado (no al imprimir), tomar el `operador_id` del `ResultadoPrueba` (aprobado o rechazo por emisiones) o el de `InspeccionVisual` (rechazo visual), y guardar el técnico en `certificate_projection_json`, que se fija una sola vez, para que una reimpresión conserve el mismo técnico.
2. Imprimir ese valor en `equipo_numero`.
3. **Detalle a decidir:** `operador_id` es un UUID y no cabe en el campo. Lo que se imprimiría es el `username` del usuario (hasta 60 caracteres), así que conviene confirmar con el cliente el formato y la longitud esperados; si prefiere un código corto tipo `001`, entonces sí haría falta un campo dedicado. Si el usuario no tiene un valor imprimible, recomiendo bloquear la impresión con un 409 en lugar de usar el parámetro fijo.

**Otra pregunta abierta con el cliente:** el cliente dice que las plantillas son las mismas para aprobados y rechazados, pero `_LAYOUT_RECHAZO` sale de `RECHAZO.doc`, que el propio cliente entregó el 22 de octubre (sin holograma y con fecha límite). No conviene tocar `_LAYOUT_RECHAZO` hasta aclarar cuál prevalece. Un rechazo visual no tiene lecturas ni potencia que imprimir, así que lo más coherente parece que solo el rechazo por emisiones use la plantilla común, pero hay que confirmarlo.

---

## 5. Defecto en `session.js`: `localStorage` bloqueado al resolver `?estacion=`

**Dónde:** `frontend/src/stores/session.js`, `resolverDeviceIdentifier()`, líneas 9 a 19.
**Archivo compartido**, así que lo coordino contigo antes de tocarlo.

**Qué pasa.** Todo está dentro de un único `try`. Si el equipo se abre con `?estacion=NOMBRE` y `localStorage.setItem` lanza una excepción (modo privado, cuota llena o almacenamiento bloqueado), la excepción salta el `return delUrl` de la línea 13 y el `catch` descarta el identificador de la URL. El equipo se identifica entonces con el valor de build o con el de ejemplo (`CAPTURA-REFORMA-L1`), es decir, **como otra estación**, y sin avisar.

**Reproducción verificada** con una réplica en Node (`window` y `localStorage` simulados):

| Escenario | Esperado | Código vigente |
|---|---|---|
| `?estacion=CAPTURA-L2` y `setItem` lanza | `CAPTURA-L2` | `DEV-BUILD` ✗ |
| `?estacion=CAPTURA-L2` y todo `localStorage` bloqueado | `CAPTURA-L2` | `DEV-BUILD` ✗ |
| Resto (5 escenarios) | ver prueba | correcto |

**Corrección propuesta** (verificada con los mismos 7 escenarios):

```js
function resolverDeviceIdentifier() {
  let delUrl = null;
  try {
    delUrl = new URLSearchParams(window.location.search).get("estacion");
  } catch {
    // sin acceso a la URL
  }
  if (delUrl) {
    try {
      localStorage.setItem("device_identifier", delUrl);
    } catch {
      // modo privado o cuota llena: se usa igualmente el valor de la URL
    }
    return delUrl;
  }
  try {
    const guardado = localStorage.getItem("device_identifier");
    if (guardado) return guardado;
  } catch {
    // sin localStorage
  }
  return import.meta.env.VITE_DEVICE_IDENTIFIER || "CAPTURA-REFORMA-L1";
}
```

**Prueba ya escrita:** `frontend/tests/session.test.js`, línea 220, `it.fails("con ?estacion=NOMBRE y localStorage no disponible usa igualmente el valor de la URL")`. Pasa mientras el defecto exista; al corregirlo se pondrá en rojo y basta quitarle el `.fails`. **Dime si prefieres corregirlo tú o que lo haga yo**: tengo la prueba lista y son pocas líneas.

---

## 6. Lo que quedó listo de mi lado (ya subido)

| Qué | Dónde |
|---|---|
| Auditoría de seguridad X1 a X7 con evidencia y plan | `docs/AUDITORIA_SEGURIDAD_X1_X7.md` (`1693465`) |
| Sección 3.3 de `PENDIENTES` al día | `dd5d1a4`, `5c2e9ad` |
| `.gitignore` de respaldos y certificados | `4be3162` |
| `POSTGRES_PASSWORD` obligatoria | `5043f4e` |
| nginx: límite de login, cabeceras, `X-Real-IP` | `1bd0eba` |
| Script de desbloqueo (Linux y Windows) | `309fb5d` |
| TLS: generador de certificados con `--hosts`, nginx 443, compose, manual | `e8a7072`, `3d52483`, `9ea9878`, `e4ec760`, `77a2f95` |
| Matriz de trazabilidad 2026-11-04 (101 HUs en HECHO, 363 SP, 89,4 %) | `docs/trazabilidad/trazabilidad_hu_2026-11-04.*` |
| Propuesta de NOM-047 | `164d86b` |

**Cuando termines cada tarea**, de mi lado hago: las pruebas de frontend que correspondan (por ejemplo, la interfaz del desbloqueo o el campo de la clave del técnico, si me dices dónde la pones), quitar los `.fails`, actualizar la matriz y la documentación, y validar con Docker.

---

## 7. Qué se probó y qué no

**Probado:**
- El generador de certificados, en Windows (OpenSSL 3.2) y en Linux (WSL2, OpenSSL 3.0): validación de argumentos, cadena de confianza, nombres e IP, reutilización de la CA, renovación y el caso de `--hosts` con tu lista exacta.
- Un **handshake TLS real** con los certificados generados: conecta con TLS 1.3 con la CA instalada, rechaza un nombre ajeno al certificado, desconfía si la estación no tiene la CA y rechaza TLS 1.1.
- El compose, con `docker compose config` (falla con mensaje claro sin `POSTGRES_PASSWORD`; publica 80 y 443).
- **Validación de Nginx TLS con Docker (`nginx:1.27-alpine`):** `nginx -t` ejecutado con éxito (`syntax is ok / test is successful`) cargando certificados ECDSA y cabeceras de seguridad.
- **Corrida E2E vehicular (`scripts/smoke_e2e_flujo.mjs`) contra el backend real en Docker:** 17 de 17 pasos aprobados en 9.6 s, incluyendo generación real del PDF con WeasyPrint en el contenedor y expediente en estado final `IMPRESO`. Recorre la **API**; no automatiza las pantallas.
- **Comportamiento del nginx real, levantado solo en Docker (2026-11-05):** el puerto 80 redirige a HTTPS conservando la ruta; el desafío ACME no se redirige; las cabeceras de seguridad salen también en `/assets/` y en respuestas 404; no se publica la versión de nginx; y el límite de login activa un **429 en JSON con `detail` legible** tras la ráfaga, sin afectar a las demás rutas de `/api/`. Además, `nginx -t` falla como debe con una llave que no corresponde al certificado y sin la carpeta de certificados.
- Los scripts de desbloqueo, con un `docker` simulado.
- La corrección de `session.js`, con una réplica en Node.
- Frontend: 397 de 397 pruebas en Vitest. El backend (468 pruebas) es el recuento que ustedes reportaron; **no lo volví a ejecutar**.

**No probado todavía:**
- Probar con un navegador con la CA instalada y pasar la CSP de modo reporte a modo enforcing.
- Los scripts de desbloqueo contra un Postgres real **de pruebas** (no se prueban contra producción: modifican datos).
- Un E2E de interfaz con navegador (el script de humo solo recorre la API).
- Let's Encrypt en el VPS: documentado como "sin probar".

---

## 8. Decisiones que necesito de ti

1. **Auditoría administrativa:** `event_log.verificacion_id` nullable o tabla `admin_event_logs` (3.1).
2. **Inspección visual:** Opción A u Opción B (4.2).
3. **Campo 001:** ya definido por el cliente (ID del usuario que hizo la prueba o emitió el rechazo). Solo confirmar que se imprime el `username` y no se necesita un código corto aparte (4.3).
4. **`session.js`:** quién lo corrige (5).
5. **Scripts de respaldo:** cuál juego queda como oficial, `respaldo.sh` y `restaurar.sh` o `backup_db.*` y `restore_db.*`.
6. **Orden y tiempos:** qué de la lista de la sección 1 entra primero.

---

## 9. Referencias

| Documento | Para qué |
|---|---|
| `docs/AUDITORIA_SEGURIDAD_X1_X7.md` | Hallazgos con evidencia por archivo y línea, mitigaciones, plan y anexos |
| `docs/PROPUESTA_FLUJO_INSPECCION_VISUAL_NOM047.md` | Opciones A y B, cambios por archivo y campo 001 |
| `docs/PENDIENTES_2026-10-20.md` | Estado de bloqueos (B), supuestos (S) y pendientes (X, D, Q) |
| `docs/MANUAL_INSTALACION_Y_OPERACION.md`, sección 3.3 | Certificados TLS: generación, instalación de la CA y renovación |
| `scripts/README.md`, secciones 5 y 6 | Script de desbloqueo y generador de certificados |
| `CLAUDE_HANDOFF.md` | Estado y tareas inmediatas |
