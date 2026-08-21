# Verificación Vehicular Oaxaca

Sistema de verificación vehicular (control de emisiones) para el estado de
Oaxaca. Backend FastAPI + Postgres, frontend Vue. El expediente
(`Verificacion`) es el objeto central: nada se opera sobre un vehículo sin
antes crear su expediente.

Repo: `Rene3FG/verificacion-oaxaca` (privado). Rama de trabajo:
`etapa1-y-siox` (no `main`).

## Arquitectura

- `backend/app/api/routers/`: un router por módulo funcional — `expedientes`,
  `siox`, `inspeccion`, `obd`, `pruebas`, `impresion`, `folios`, `estaciones`.
- `backend/app/services/state_machine.py`: única puerta para cambiar
  `Verificacion.estado`. Ningún router debe hacer `UPDATE` directo sobre
  `estado`; todo pasa por `state_machine.transition()`, que valida contra
  `ALLOWED_TRANSITIONS` y escribe la fila correspondiente en `event_log` de
  forma atómica con el cambio de estado.
- `backend/app/services/siox_client.py`: cliente del portal público SIOX
  (`https://siox.finanzasoaxaca.gob.mx/pagoTenencia`), hecho por ingeniería
  inversa — la respuesta es HTML, no JSON, y el sitio reutiliza IDs de forma
  inconsistente entre MARCA/LINEA/VERSIÓN/MOTOR (ver el docstring del
  archivo). No tocar la lógica de parseo sin releer ese comentario.
- Identidad de sesión: `backend/app/api/deps.py`. `get_current_session`
  resuelve `SessionContext` (usuario, estación, línea, centro) a partir del
  header `X-Session-Id` — ningún router debe volver a pedirle `linea_id` ni
  `usuario_id` al cliente. `requiere_estacion(StationType)` es la variante
  que además exige un tipo de estación específico (Captura/Prueba/Impresión),
  devolviendo 403 si no coincide.
- `assert_linea_permitida(session, linea_id)`: valida que una sesión pueda
  operar sobre el expediente de esa línea (403 si no). Estaciones
  centralizadas (`is_centralized=True`) usan `allowed_line_ids` en vez de una
  sola línea.

## Pruebas

Corren contra Postgres real (los modelos usan `ARRAY`/`UUID`/`JSONB`, no
simulables en SQLite). `pytest.ini` fija
`asyncio_default_fixture_loop_scope = function`.

```bash
docker start verificacion-oaxaca-db-1 verificacion-oaxaca-redis-1  # si no están arriba
cd backend && source .venv/bin/activate && python -m pytest -q
```

`tests/conftest.py` trae fixtures reusables: `crear_estacion`,
`crear_permiso`, `crear_sesion_activa`, `crear_sesion_supervisor`,
`crear_expediente`, y `client`/`db_session` (cada test corre en un
SAVEPOINT que se revierte al final, no deja datos entre pruebas).

Estado actual: **95 pruebas, todas pasan.**

## Etapa 1 — hecho

Login con validación de línea del permiso, colas por sesión (la línea sale
de la sesión, nunca de la URL), bloqueo de expediente ajeno (403), auditoría
de accesos (`access_events`).

## Etapa 2 — progreso

- **HU-019/HU-018** (crear expediente, heredar línea de la estación): hecho.
  `POST /api/expedientes` hereda `centro_id`/`linea_id`/`operador_id` de la
  sesión (el payload no puede sobreescribirlos), nace en estado `CREADO`, y
  solo una estación de tipo Captura puede crearlo
  (`requiere_estacion(StationType.CAPTURA)`).
- **HU-011** (conectar SIOX al expediente): hecho. `POST
  /api/siox/consultar/{id}` consulta por placa, guarda evidencia en
  `siox_consultas` e `integration_logs`, y expone los estados
  `EXITOSA`/`SIN_DATOS`/`ERROR` sin bloquear nunca al operador — si SIOX no
  responde o no encuentra datos, `POST /api/siox/captura-manual/{id}` habilita
  la captura manual asistida. Ambos endpoints restringidos a estación de
  Captura.
- **HU-012** (importar y normalizar): hecho. Cuando la consulta es
  `EXITOSA`, los campos de la respuesta normalizada que tienen columna en
  `Vehiculo` (`niv`, `marca`, `linea`, `modelo`, `tipo_vehiculo`) se escriben
  ahí, `fuente_datos` pasa a `SIOX`, y el evento `datos_siox_importados` en
  `event_log` registra qué campos se actualizaron. `estatus`/`version`/`motor`
  no tienen columna propia y quedan solo en
  `siox_consultas.response_normalized`.

### Flujo de estados relevante para Etapa 2

```
CREADO → DATOS_SIOX_CONSULTADOS → DATOS_SIOX_IMPORTADOS ─┐
      └─────────────────────────→ DATOS_CAPTURADOS_MANUALMENTE ─┴→ DATOS_NORMALIZADOS → INSPECCION_VISUAL_PENDIENTE
```

`DATOS_SIOX_CONSULTADOS` es el estado intermedio tanto si SIOX respondió con
datos como si no; desde ahí, `SIN_DATOS`/`ERROR` habilitan captura manual
(`DATOS_CAPTURADOS_MANUALMENTE`) sin pasar por un estado de error — el
expediente nunca se traba por una falla de SIOX.

`DATOS_SIOX_IMPORTADOS`/`DATOS_CAPTURADOS_MANUALMENTE` → `DATOS_NORMALIZADOS`
→ `INSPECCION_VISUAL_PENDIENTE` es una **confirmación manual** del operador
de Captura vía `POST /api/expedientes/{id}/normalizar` (decisión de negocio
2026-08-07, ver más abajo) — no es automática.

### Nota sobre `requiere_estacion`

Aplicado en `expedientes.py` (Captura), `siox.py` (Captura), `pruebas.py`
(Prueba), `impresion.py` (Impresión), `folios.py` (Impresión — la
solicitud de folio se dispara desde la misma estación que imprime),
`inspeccion.py` (Prueba) y `obd.py` (Prueba). Las dos últimas se definieron
el 2026-08-07: el modelo de estaciones solo tiene 3 tipos físicos (`CAPTURA`,
`PRUEBA`, `IMPRESION`, ver `seed.py`); se decidió que inspección visual y
OBD/SBD corren en la misma estación física donde después se hace la prueba
dinámica/estática/opacidad, junto al equipo de prueba.

### Resuelto (2026-08-07): la cadena que se rompía después de importar/capturar

El 2026-08-06 se encontró que ningún endpoint transicionaba
`DATOS_SIOX_IMPORTADOS`/`DATOS_CAPTURADOS_MANUALMENTE` → `DATOS_NORMALIZADOS`
→ `INSPECCION_VISUAL_PENDIENTE`, dejando `POST /api/inspeccion/{id}`
inalcanzable en la práctica. Se decidió que ese paso es una **confirmación
manual** del operador de Captura (no automática): revisa/corrige los datos
importados o capturados y confirma explícitamente antes de mandar el
expediente a Inspección Visual.

Implementado como `POST /api/expedientes/{id}/normalizar`
(`requiere_estacion(StationType.CAPTURA)`): valida que el expediente esté en
`DATOS_SIOX_IMPORTADOS` o `DATOS_CAPTURADOS_MANUALMENTE` (409 si no), y hace
las dos transiciones (`DATOS_NORMALIZADOS` → `INSPECCION_VISUAL_PENDIENTE`)
en una sola llamada. `tests/test_estacion_guard.py::test_flujo_completo_captura_a_inspeccion_visual`
cubre el camino end-to-end completo (SIOX exitoso → normalizar → inspección
visual) que antes era imposible.

## Frontend — Captura (2026-08-13)

`CapturaView.vue` deja de ser un cascarón: cubre el paso de Registro
(consulta SIOX con historial, datos del vehículo editables, propietario,
confirmar/normalizar). El stepper visual muestra los 4 pasos conceptuales,
pero Inspección Visual y OBD/SBD **no viven aquí** — corren en la estación
de Prueba (decisión 2026-08-07), así que esta vista no los implementa.
`PruebaView.vue` sigue siendo un cascarón; ahí es donde esos dos pasos
tendrían que completarse.

## Frontend — Prueba (2026-08-14)

`PruebaView.vue` deja de ser un cascarón (antes solo listaba `GET
/pruebas/cola`, que además solo cubre `LISTO_PARA_PRUEBA` — no sirve para
ver expedientes en Inspección Visual u OBD). Ahora, igual que
`CapturaView`, usa `GET /api/expedientes?centro_id=&linea_id=` y filtra
client-side a los 8 estados que le corresponden a esta estación
(`INSPECCION_VISUAL_PENDIENTE` … `PRUEBA_EN_PROCESO`), y renderiza una
sección distinta según el estado del expediente abierto:

- **Inspección visual**: checklist fijo de 8 puntos (luces, limpiaparabrisas/
  claxon, espejos, llantas, fugas, escape, placas) — **propuesto por Claude
  a falta del documento de diseño del proyecto** (mismo caso que el
  checklist de impresión en `app/services/certificado.py`, a confirmar con
  el equipo de Prueba). El resultado (`APROBADA`/`RECHAZADA`) se calcula
  solo de si algún ítem quedó sin marcar; un rechazo exige texto de causal
  y, al confirmar, el expediente sale de esta vista (regla de negocio #3:
  salta directo a Impresión Central, ya no pasa por OBD ni Prueba).
- **OBD/SBD**: tres botones según el estado (`evaluar aplicabilidad` →
  `solicitar` → `guardar resultado`), sin captura de `codigos_error`/
  `datos_raw` (opcionales en el schema, sin UI todavía — pendiente si se
  necesita).
- **Prueba**: tipo por defecto según combustible del vehículo (gasolina →
  dinámica, cambiable a estática con motivo obligatorio; cualquier otro
  combustible → opacidad, sin cambio permitido) — replica en el frontend la
  regla de negocio #5/#9 que ya vive en el backend, pero **no lee
  `cat_parametros_sistema`** (`gasolina_prueba_default`,
  `gasolina_permite_cambio_estatica`) porque no hay endpoint que exponga
  parámetros de sistema; si se vuelven configurables de verdad, hace falta
  ese endpoint. Configurar → iniciar → resultado (editor de pares
  clave/valor libres para `valores_medidos_json`, sin `limites_aplicados_json`
  todavía). Al guardar resultado, el expediente sale a Impresión Central.

Probado end-to-end contra el backend real (no simulado): 3 expedientes
nuevos por `curl` cubriendo los 3 caminos completos de la máquina de
estados — aprobación con OBD aplicable (gasolina 2022, dinámica), rechazo
en inspección visual (salta a impresión), y OBD no aplicable (diésel,
directo a Prueba, opacidad). Los 3 expedientes de prueba y las filas de
`sync_outbox` que generaron se borraron después de verificar — **la base de
datos de desarrollo (puerto 5433) es la misma que usa `pytest`
(`SessionLocal`, no hay DB de test separada)**, así que cualquier POST real
contra el `uvicorn` de desarrollo dejaba entradas que sí afectaban después
las aserciones de `tests/test_sync.py` y `tests/test_colas_y_lineas.py`
(conteos globales de `sync_outbox`/`PENDIENTE_IMPRESION` sin filtrar por
placa de prueba). Si se vuelve a probar manualmente contra el servidor de
desarrollo, limpiar después (`DELETE FROM sync_outbox` y los expedientes de
prueba) antes de confiar en la suite. Build de producción sin errores; sin
extensión de Chrome conectada en esta sesión, no se probó visualmente en
navegador.

## Corrección de vehículo desde Prueba (2026-08-14)

Decisión de producto del cliente: el operador debe poder corregir los datos
del vehículo después de normalizar, porque Inspección Visual (estación de
Prueba) puede detectar un error que antes no había forma de arreglar sin
devolver el expediente a Captura.

- `requiere_estacion` (`app/api/deps.py`) ahora acepta múltiples
  `StationType` (`*tipos`) en vez de uno solo — cambio retrocompatible, los
  demás endpoints que le pasaban un único tipo siguen igual.
- `PATCH /api/expedientes/{id}/vehiculo` (HU-016) ahora acepta Captura
  **o** Prueba (antes solo Captura). Sin chequeo de estado del expediente
  (decisión explícita: se puede corregir en cualquier punto mientras el
  expediente siga abierto, no solo antes de normalizar).
- `PruebaView.vue`: panel colapsable "Datos del vehículo" (arriba de
  Inspección Visual/OBD/Prueba, visible en cualquier sub-estado de esta
  estación) que reusa el mismo patrón de formulario de `CapturaView.vue`
  contra el mismo endpoint.
- Pruebas actualizadas en `tests/test_expedientes.py`:
  `test_actualizar_vehiculo_desde_estacion_de_prueba_responde_200`
  (antes esperaba 403, ahora es el camino soportado) y nueva
  `test_actualizar_vehiculo_desde_estacion_de_impresion_responde_403`
  (Impresión sigue sin poder tocar datos del vehículo). 100 pruebas, todas
  pasan.

## Folios e Impresión — cerrado (2026-08-13)

- **Folios**: `/api/folios/solicitar` ya reutilizaba una `FolioRequest`
  ASIGNADA previa del mismo tipo (idempotencia real, HU-066/HU-071);
  quedó cubierto con pruebas (5 reintentos → 1 folio; reintento tras
  error → 1 asignación). Se agregó `solicitud_id` al payload que se manda
  al sistema externo (documentado como idempotency key, nunca se enviaba).
  Bug encontrado y corregido: pedir un segundo `tipo_certificado` con el
  expediente ya en `FOLIO_ASIGNADO` tiraba `TransitionNotAllowed` sin
  manejar (500); ahora es 409.
- **Impresión** (HU-061, HU-062, HU-072 a HU-079):
  - `POST /api/impresion/tipo-certificado/{id}`: determina
    `certificado_tipo` (columna que nunca se escribía). Reglas
    **propuestas** por Claude a falta del documento de diseño del
    proyecto (no está en el repo) — ver docstring de
    `app/services/certificado.py`, a confirmar/corregir.
  - `GET /api/impresion/vista-previa/{id}`: PDF con WeasyPrint, sin tocar
    estado.
  - `POST /api/impresion/imprimir/{id}`: ya no pide `print_job_id` (nada
    lo creaba — el endpoint viejo era imposible de llamar en la
    práctica); ahora obtiene o crea su propio `PrintJob`. Reintento desde
    `IMPRESION_FALLIDA` reusa `folio_externo`. Impresora física es un
    stub inyectable (`app/services/impresora.py`).
  - `POST /api/impresion/cerrar/{id}`: separado de `/imprimir` (antes una
    sola llamada hacía `IMPRESO`→`CERRADO` sin condición). Las 5
    condiciones de cierre también son **propuestas**, a falta del
    documento de diseño — ver `_condiciones_de_cierre_incumplidas` en
    `app/api/routers/impresion.py`.

## Supervisor/Administrador — primer bloque (2026-08-13)

- **HU-119 (autenticación real)**: modelo `cat_usuarios` (username,
  password_hash con bcrypt, is_active). `POST /api/estaciones/login`
  ahora exige username+password válidos contra ese hash — antes
  aceptaba cualquier UUID como `user_id` sin verificar nada. Mismo 401
  genérico para usuario inexistente o contraseña incorrecta (no
  filtrar cuál). Seed crea `operador1`/`operador1` y
  `supervisor1`/`supervisor1` (dev).
- **HU-121 (roles y permisos)**: CRUD en `/api/permisos` sobre
  `UserStationPermission`, antes solo se tocaba por base de datos
  directa.
- **Nueva dependencia `requiere_supervisor`** (`app/api/deps.py`): a
  diferencia de `requiere_estacion`, no depende del tipo de estación
  física donde se inició sesión — valida `can_supervise=True` en algún
  `UserStationPermission` del usuario. La usan HU-121, HU-114 y
  HU-111/117.
- **HU-114 (reasignación de línea)**: `POST
  /api/expedientes/{id}/reasignar-linea`, motivo obligatorio, bloqueada
  si el expediente ya tiene `resultado_final` o `folio_externo`.
  Acotada al mismo centro de la sesión del supervisor.
- **HU-111/HU-117 (monitor y bitácora)**: `GET /api/supervision/monitor`
  (todas las líneas activas del centro, excluye CERRADO/CANCELADO) y
  `GET /api/supervision/expedientes/{id}/bitacora` (línea de tiempo de
  `event_log`, todos los módulos).

Pendiente de Prompt 4 (no implementado): nada explícito quedó fuera de
las 4 historias pedidas, pero el frontend de supervisión/administración
(pantallas para todo lo anterior) no existe — solo backend.

### Frontend Supervisor/Administrador (2026-08-14)

`SupervisorView.vue` (ruta `/supervisor`, `meta.requiereSupervisor`) cubre
las 4 historias del bloque anterior en dos pestañas:

- **Monitor**: tabla de `GET /api/supervision/monitor` (todas las líneas
  activas del centro de la sesión), con botones por fila para abrir la
  **bitácora** (`GET /api/supervision/expedientes/{id}/bitacora`, en un
  diálogo con `v-timeline`) y **reasignar línea**
  (`POST /api/expedientes/{id}/reasignar-linea`, diálogo con línea nueva +
  motivo obligatorio).
- **Permisos**: tabla de `GET /api/permisos?center_id=<centro de la
  sesión>` con switches inline para `can_operate`/`can_supervise` (PATCH
  al cambiar) y borrado (`DELETE`). Alta de permiso en diálogo
  (`POST /api/permisos`).

Dos piezas de plomería que no existían y hicieron falta para que la
pantalla fuera usable (no son historias nuevas, son huecos técnicos):

- **`StationSessionRead.can_supervise`** (`app/schemas/estacion.py`): no es
  columna de `StationSession` — el login nunca decía si la sesión puede
  supervisar. Se calcula en `POST /api/estaciones/login`
  (`app/api/routers/estaciones.py`) a partir del
  `UserStationPermission` (`permiso_valido`) que autorizó el acceso, y se
  inyecta como atributo suelto en el objeto antes de serializar (no se
  persiste). El frontend (`session.puedeSupervisar` en
  `stores/session.js`) lo usa para mostrar el botón "Supervisor" en
  `TopAppBar.vue` y para el guard de router de `/supervisor` —
  independiente del `station_type` físico de la estación donde se hizo
  login.
- **`GET /api/usuarios`** (`app/api/routers/usuarios.py`, nuevo router,
  `requiere_supervisor`): antes no había forma de listar `cat_usuarios`
  desde la API — se necesitaba para poblar el selector de usuario al dar
  de alta un permiso. Es de solo lectura; `cat_usuarios` se sigue
  administrando solo por `app/seed.py`, no hay alta de usuarios desde la
  app todavía.

Pruebas nuevas: `can_supervise` en el response de login
(`tests/test_login.py`) y `tests/test_usuarios.py`. 99 pruebas, todas
pasan. Probado end-to-end contra el backend real vía curl (login como
`supervisor1`, monitor, bitácora, reasignar línea ida y vuelta, alta/
edición/baja de permiso) — sin extensión de Chrome conectada en esta
sesión, no se pudo probar la vista visualmente en el navegador.

## Captura — cerrado (2026-08-13)

- **HU-013**: `GET /api/siox/consultas/{id}` — historial de consultas SIOX,
  más reciente primero, sin exponer `response_raw`.
- **HU-014**: cada intento de `consultar_siox` audita en `event_log`
  (`siox_consulta_intentada`, con número de intento) aunque no dispare una
  transición válida — un reintento nunca queda invisible.
- **HU-016**: `PATCH /api/expedientes/{id}/vehiculo` corrige datos del
  vehículo (campos opcionales); si el dato corregido venía de SIOX,
  `fuente_datos` pasa a `CORREGIDO_OPERADOR`. Lógica compartida en
  `app/services/vehiculo.py`.
- **HU-015**: `POST /api/siox/captura-manual/{id}` acepta opcionalmente los
  mismos campos, reutilizando `app/services/vehiculo.py`.
- **HU-017**: combustible obligatorio. `normalizar_expediente` rechaza
  (409) sin `vehiculo.combustible` y, de paso, escribe
  `Verificacion.combustible_validado` en ese punto (Captura, antes de
  Inspección Visual). `guardar_resultado_prueba` en Prueba también
  rechaza (409) si falta, en vez de defaultear a cadena vacía.

Hallazgos menores de la revisión 2026-08-07 — **resueltos 2026-08-10**
(en paralelo a lo anterior, por otra vía — ver nota):
- `Verificacion.combustible_validado` también se escribe en `POST
  /api/obd/evaluar/{id}` al momento de evaluar, tomando el valor
  directamente del `Vehiculo` normalizado. Con HU-017 ya garantizando
  combustible desde Captura, esta segunda escritura es redundante pero
  inofensiva (mismo valor, mismo campo) — queda como defensa adicional
  si algún expediente llegara a OBD sin pasar por `/normalizar`.
- `POST /api/obd/evaluar/{id}` ya no acepta `tipo_vehiculo`/`combustible`/
  `modelo` del caller — los lee del `Vehiculo` via `selectinload`. Devuelve
  422 si el vehículo no tiene esos campos (expediente no normalizado).
  3 pruebas nuevas en `tests/test_obd.py` cubren el comportamiento.

## Etapa 12 — operación sin internet — cerrada (2026-08-13)

Análisis previo (retomado del WIP en `64bdfd5`): todos los modelos usan
`UUIDPKMixin` con `default=uuid.uuid4`, así que cada fila nace con un id
propio y estable generado en Python antes del INSERT. Por eso
`sync_outbox.entity_uuid` alcanza como clave de deduplicación: el central
hace upsert-por-id sin importar cuántas veces se reenvíe la misma fila. Lo
único que no era idempotente era `PrintJob.intentos` (contador mutado), ya
resuelto — ver abajo.

- **Productor** (`app/services/sync.py`): `encolar_sync`/
  `registrar_evento_con_sync` (agrega un `EventLog` Y lo encola junto con
  un snapshot idempotente de `Verificacion`). `state_machine.transition()`
  encola automáticamente cada transición — cubre casi todo el flujo con un
  solo punto de código. Los 3 sitios que escribían `EventLog` directo sin
  pasar por `transition()` (`crear_expediente`, `reasignar_linea`, HU-014
  de `siox.py`, HU-016 de `vehiculo.py`) están migrados a
  `registrar_evento_con_sync`.
- **`PrintAttempt`** (`app/models/print_attempt.py`): un intento de
  impresión es su propia fila inmutable, no un contador mutado.
  `impresion.py` ya no hace `print_job.intentos += 1`: crea una fila
  `PrintAttempt` (`exitoso`/`error_message`) por intento y recalcula
  `print_job.intentos` contando filas — caché idempotente bajo reenvío.
- **Consumidor** (`POST /api/sync/procesar`, `requiere_supervisor`): no hay
  Celery configurado pese a estar en `requirements.txt`, así que el envío
  se dispara manualmente (botón de supervisor, o un cron/systemd timer
  local pegándole al endpoint). Llama a `procesar_pendientes`: envío
  ordenado por `created_at` (FIFO) de filas `PENDING`/`ERROR`, backoff
  exponencial (`calcular_espera_segundos`, base 5s, tope 3600s) antes de
  reintentar, y marca `SYNCED`/`ERROR` según la respuesta de
  `enviar_uno_a_central` (stub inyectable — sin integración real definida
  con un central, mismo patrón que `siox_client`/`impresora`/sistema de
  folios). `tests/test_sync.py` cubre backoff, orden FIFO, y que reenviar
  la misma operación 5 veces produce un solo registro en el central
  (upsert-por-id).
- **Alcance decidido — catálogos/usuarios fuera de `sync_outbox`**:
  `CatUsuario`, `UserStationPermission`, `Workstation` y
  `CatParametroSistema` NO se encolan. `sync_outbox` es unidireccional
  (local → central) para datos operativos generados por Captura/Prueba/
  Impresión durante un corte de conexión; no es un mecanismo de
  replicación de catálogos. La administración de usuarios/permisos/
  estaciones (`/api/permisos`, login) requiere conexión — es consistente
  con que el login ya depende de `cat_usuarios` poblado localmente de
  antemano, no de un alta hecha sin conexión. Si en el futuro se necesita
  administrar catálogos sin conexión, es un mecanismo aparte
  (central → local), no una extensión de este.
- **Regla de negocio** (ya garantizada estructuralmente, no por este
  módulo): sin conexión se puede capturar y probar, pero no imprimir el
  certificado definitivo — `folio_externo is None → 409` en
  `impresion.py`, porque el folio requiere el sistema externo.

Pendiente real: `enviar_uno_a_central` sigue sin integración — no hay
central definido todavía. Cuando exista, se conecta ahí sin tocar
`procesar_pendientes` ni el productor.

### Visibilidad de sincronización para el operador (2026-08-20)

El diseño original pedía que el operador viera "En línea / Sin internet / N
pendientes / Sincronizando / Todo sincronizado", pero nada lo exponía:
`session.conexion` en el frontend estaba fijo en `"en_linea"` y Supervisor
no tenía botón para disparar `/api/sync/procesar` (el endpoint ya existía).

- **`GET /api/sync/estado`** (`app/api/routers/sync.py`): conteos de
  `sync_outbox` por `sync_status` (`pendientes` = PENDING+ERROR,
  `sincronizando`, `en_error`, `sincronizados`, `pendiente_mas_antiguo`).
  A diferencia de `/procesar`, usa `get_current_session` (no
  `requiere_supervisor`): es de solo lectura y lo consume el Top App Bar
  en cualquier estación, no solo Supervisor.
- **`TopAppBar.vue`**: refresca `session.actualizarEstadoSync()` cada 30s
  (mismo patrón de polling que el resto del sistema); el chip de conexión
  ahora muestra "Sincronizando…" / "N pendientes" / "Todo sincronizado" /
  "M en error" según la respuesta real, en vez del texto fijo anterior.
- **`SupervisorView.vue`**: nueva pestaña "Sincronización" con los mismos
  conteos y un botón "Sincronizar ahora" (`POST /api/sync/procesar`).

**Advertencia de base de datos compartida (recordatorio, ver arriba):**
tras `python -m app.seed_demo`, 3 pruebas fallan
(`test_cola_prueba_deriva_de_la_sesion`,
`test_impresion_cola_limitada_a_allowed_line_ids`,
`test_historial_consultas_ordena_mas_reciente_primero`) porque asumen
tablas vacías a nivel global y la demo deja un expediente real en línea 1 /
`LISTO_PARA_PRUEBA` y filas de `SioxConsulta`. No es una regresión: es el
mismo riesgo ya documentado (dev DB = test DB, sin DB de test separada).
Para confiar en la suite completa: `TRUNCATE TABLE verificaciones,
vehiculos, sync_outbox CASCADE;` y NO correr `seed_demo` antes de
`pytest`. Para grabar una demo: correr `seed_demo` y aceptar que esas 3
pruebas van a fallar hasta la próxima limpieza.
