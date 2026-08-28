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

## Frontend — Impresión (2026-08-18)

`ImpresionView.vue` deja de ser el cascarón de René (Aug 4, que solo
listaba la cola) y cubre el flujo completo de esta estación, igual que
`CapturaView`/`PruebaView`: `GET /impresion/cola` para la lista, y una
vista de detalle con cuatro secciones que se habilitan/deshabilitan según
el estado del expediente abierto:

- **Certificado**: `POST /impresion/tipo-certificado/{id}` calcula y
  guarda `certificado_tipo`; la vista previa (`GET
  /impresion/vista-previa/{id}`, blob de PDF abierto en pestaña nueva)
  solo se habilita una vez calculado. "Calcular tipo de certificado" solo
  se habilita en `PENDIENTE_IMPRESION`/`FOLIO_ERROR` (mismos estados que
  "Solicitar folio") — recalcular con el expediente ya en
  `FOLIO_ASIGNADO` devuelve 409 en el backend (ver "Folios e Impresión"
  arriba), así que el frontend evita ofrecer esa acción una vez que ya no
  aplica, en vez de dejar que el operador se tope con el error.
- **Folio externo**: `POST /folios/solicitar/{id}` solo si ya hay
  `certificado_tipo` y el expediente está en `PENDIENTE_IMPRESION` o
  `FOLIO_ERROR` (reintentable) y no tiene folio ya asignado. Si el sistema
  externo no responde (`data.folio` nulo), la vista muestra la alerta roja
  y no bloquea — el expediente queda en `FOLIO_ERROR`, reintentable desde
  el mismo botón.
- **Impresión**: `POST /impresion/imprimir/{id}`, habilitado solo con
  folio asignado y estado `FOLIO_ASIGNADO`/`IMPRESION_FALLIDA` (el botón
  cambia su texto a "Reintentar impresión" en el segundo caso). Si la
  impresora no responde, la respuesta trae `intentos` y el expediente se
  queda en `IMPRESION_FALLIDA` para reintentar.
- **Cierre**: `POST /impresion/cerrar/{id}`, habilitado solo en estado
  `IMPRESO` sin `cerrado_at`; al confirmar, vuelve a la cola tras 1.2s.

Validado manualmente contra el backend real (no simulado): cola, detalle,
cálculo de tipo de certificado (`RECHAZO_VISUAL`), vista previa de PDF
(HTTP 200), y el camino `FOLIO_ERROR` (alerta roja correcta, botones de
Imprimir/Cerrar correctamente bloqueados). **El camino
folio→imprimir→cerrar exitoso sigue sin probarse**:
`_consultar_sistema_externo_folios` (`app/api/routers/folios.py`) está
hardcodeado a devolver `{"status": "error"}` — no hay sistema externo de
folios real ni mecanismo de mock todavía (pendiente de definir con el
equipo de backend). Build de producción sin errores.

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

### Bug real encontrado al investigar la colisión demo/pruebas (2026-08-21)

Al construir lo de arriba, sembrar `seed_demo` (centro `reforma`) rompía 3
pruebas que usan centro `OAX-01`. La causa NO era solo "misma base para
dev y test" (eso sigue siendo cierto, ver Etapa 2): era que **el número de
línea nunca se comparaba junto con el centro**, pese a que
`Workstation.center_id`/`Verificacion.centro_id` existen justo para eso.
Una estación de la "línea 1" del centro `OAX-01` podía ver y operar
expedientes de la "línea 1" de CUALQUIER OTRO centro (`reforma` incluido)
con el mismo número de línea — el 403 de HU-008 ("Este expediente
pertenece a otra línea") nunca se disparaba entre centros porque
`assert_linea_permitida` y las colas de Prueba/Impresión solo miraban
`linea_id`, nunca `centro_id`.

- **`assert_linea_permitida(session, centro_id, linea_id)`**
  (`app/api/deps.py`): ahora exige `session.center_id == centro_id`
  además del número de línea. Cambió la firma (antes solo `linea_id`);
  actualizados los 11 llamadores (`expedientes`, `pruebas`, `impresion`,
  `folios`, `obd`, `inspeccion`, `siox`) para pasar
  `verificacion.centro_id`.
- **`cola_prueba`** (`app/api/routers/pruebas.py`) y **`cola_impresion`**
  (`app/api/routers/impresion.py`): ahora filtran también por
  `Verificacion.centro_id == session.center_id`.
- **Hallazgo más serio en el camino**: `GET /api/expedientes`
  (`listar_expedientes`, usado por `CapturaView`/`PruebaView`) **no
  dependía de ninguna sesión** — sin `X-Session-Id`, y sin importar los
  filtros `?centro_id=&linea_id=` de la query (el frontend manda los
  suyos, pero nada del lado del servidor los validaba), devolvía TODOS
  los expedientes de TODOS los centros del sistema. Ahora exige sesión
  activa, valida que `centro_id`/`linea_id` de la query (si se mandan)
  coincidan con lo que la sesión puede ver (403 si no), y si se omiten se
  acota por default al centro/líneas de la sesión — nunca a todo el
  sistema.
- Pruebas nuevas: `tests/test_expedientes.py` (4, incluye 401 sin sesión y
  403 por centro/línea ajenos), `tests/test_colas_y_lineas.py` (2, "misma
  línea, otro centro" en cola de Prueba y en el 403 de HU-008), y
  `tests/test_siox_router.py::test_historial_consultas_ordena_mas_reciente_primero`
  corregido (escaneaba `SioxConsulta` sin filtrar por expediente — un bug
  de aislamiento del test, no de producción).

**Resultado**: 111 pruebas, todas pasan — incluso con `seed_demo` ya
sembrado. La advertencia anterior ("no correr `seed_demo` antes de
`pytest`") ya no aplica: era sintomática de este bug, no un límite
permanente del setup de pruebas.

## Unificación de ramas y simulador de folios (2026-08-24)

`etapa1-y-siox` y `frontend-impresion-central` estaban separadas por 4
commits. Al momento de unificar resultó que `frontend-impresion-central`
ya había hecho merge de `etapa1-y-siox` por su cuenta (commit `07c6417`,
2026-08-21) — `etapa1-y-siox` era ancestro directo, así que unificar fue
un fast-forward limpio, sin conflicto que resolver en `ImpresionView.vue`
ni en `CLAUDE.md`.

**Flujo completo verificado contra el backend real** (crear expediente →
SIOX → normalizar → inspección visual → OBD → configurar/iniciar/resultado
de prueba → determinar certificado → solicitar folio → imprimir → cerrar):
se corta exactamente en "solicitar folio", como se esperaba —
`_consultar_sistema_externo_folios` devolvía siempre error.

- **Simulador de folios configurable** (`app/services/folios_client.py`):
  reemplaza el stub hardcodeado por `FoliosExternoClient`, inyectable vía
  `Depends(get_folios_client)`, con 5 modos (`ModoFolioExterno`: EXITO,
  ERROR, TIMEOUT, FOLIO_DUPLICADO, FOLIO_INVALIDO). El modo se selecciona
  sobrescribiendo la dependencia en pruebas
  (`app.dependency_overrides[get_folios_client]`, limpiado automáticamente
  por el fixture `client`), nunca con una variable global compartida.
  Default de producción: ERROR (mismo comportamiento observable que antes
  — sigue sin haber sistema externo real).
- Se agrega validación de formato del folio recibido
  (`folio_tiene_formato_valido`) — antes se confiaba ciegamente en
  `respuesta["folio"]` cuando `status == "asignado"`. Un folio con formato
  inválido ahora deja el expediente en `FOLIO_ERROR` con el motivo en
  `integration_logs`, no se asigna sin más.
- `tests/test_folios.py`: 4 pruebas nuevas — éxito asigna y transiciona,
  timeout/duplicado/formato inválido dejan `FOLIO_ERROR` con el mensaje
  correcto, y un expediente completo llega a `CERRADO` pasando de verdad
  por `/folios/solicitar` (las pruebas de impresión existentes inyectaban
  `FOLIO_ASIGNADO` directo en la fixture, sin ejercer nunca ese endpoint
  en la cadena completa).

**Guards de estado en Prueba y OBD**: al recorrer el flujo real se
encontraron varios `TransitionNotAllowed` sin manejar (500) en
`pruebas.py` (`configurar`/`iniciar`/`resultado`) y `obd.py`
(`solicitar`/`resultado`) — llamar cualquiera de estos fuera de su estado
de origen esperado tiraba 500 en vez de un 409 claro, mismo patrón ya
corregido antes en `folios.py`. Se agregaron guards explícitos de estado
antes de cada `state_machine.transition()`.

**Regla #5/#9 implementada en el backend, no solo en el frontend**:
`configurar_prueba` no validaba nada contra el combustible — aceptaba
cualquier `tipo_prueba`. Ahora sí: gasolina propone `DINAMICA` por
defecto (cambiable a `ESTATICA` solo con `cambio_manual=true` y `motivo`,
auditado en `event_log` con usuario/motivo/fecha); cualquier otro
combustible usa `OPACIDAD` sin cambio permitido.

- `tests/test_pruebas.py`: 6 pruebas nuevas (default por combustible,
  bloqueo de cambio inválido, auditoría del cambio dinámica→estática, no
  se puede iniciar prueba sin pasar por inspección/OBD, no se puede
  guardar resultado sin haber iniciado la prueba).
- `tests/test_obd.py`: 3 pruebas nuevas (guards de `solicitar`/`resultado`
  fuera de estado, camino completo solicitar→resultado).

**Resultado**: 124 pruebas, todas pasan. Commits sobre `etapa1-y-siox`,
**NO pusheados todavía** (pendiente de confirmación explícita, como
siempre en este proyecto). Pendiente real que sigue abierto:
`enviar_uno_a_central` sigue sin integración real (sin cambios).

## Inventario local de folios (2026-08-25) — corrige el hallazgo #1 del Figma

La revisión del Figma del 2026-08-24 (`~/Descargas/Revision_Figma_Verificentros_
Oaxaca_2026-08-24.pdf`) encontró que `folios_client.py`/`certificado.py`
construidos ese mismo día simulaban un sistema externo de folios que no
existe en el diseño real: el handoff dice explícitamente que este backend
ES la fuente de verdad del inventario, con 4 tipos de certificado
(PARTICULAR/DOBLE_CERO/INTENSIVO/RECHAZO, no los 3 nombres inventados que
usaba `certificado.py`). Esta sesión implementa los puntos 1 y 2 del orden
sugerido en esa revisión (sección 14): inventario local + selección manual
de tipo de certificado. Puntos 3-5 (split de `CERRADO`, campos de
propietario/domicilio/PBV/Tracción, checklist real de inspección visual)
siguen pendientes — ver "Pendiente real" al final de esta sección.

- **`app/models/folio.py`** (nuevo, reemplaza `folio_request.py`/
  `folio_assignment.py`, eliminados): `FolioLote` (alta masiva por rango —
  el usuario eligió rango sobre archivo, ya que el handoff deja el método
  sin definir) y `Folio` (una fila por folio físico, `estatus` en
  DISPONIBLE/ASIGNADO/IMPRESO/DANADO/INVALIDADO). `Folio.orden` es una
  `IDENTITY` de Postgres — asignar "el siguiente folio disponible" es
  tomar el de menor `orden` con `estatus=DISPONIBLE` vía `FOR UPDATE SKIP
  LOCKED` (`app/services/folio_inventario.py::asignar_siguiente_folio`),
  así dos asignaciones concurrentes del mismo tipo nunca chocan.
- **`POST /api/folios/lotes`** (`requiere_supervisor`): registra un rango
  (`folio_inicio`..`folio_fin`, deben compartir prefijo y terminar en un
  número) como folios DISPONIBLE. El handoff pide que sea el "Superadmin"
  quien registre folios, pero ese rol de plataforma (separado de
  Supervisor por-verificentro) no existe en este sistema todavía — el
  usuario, preguntado explícitamente, eligió `requiere_supervisor` como
  aproximación temporal. Si se construye un Superadmin global más
  adelante, este endpoint es el primer candidato a migrarle el guard.
- **`GET /api/folios/inventario`** (`requiere_supervisor`): conteo por
  tipo/estatus, consumido por la pestaña "Folios" de `SupervisorView.vue`.
- **`POST /api/folios/solicitar/{id}`**: ya no llama a un cliente externo
  simulado — toma atómicamente el siguiente folio local del tipo pedido.
  Sin conservar la idempotencia de antes (reintentar reutiliza cualquier
  folio ya ASIGNADO/IMPRESO del mismo tipo para ese expediente). Sin
  inventario del tipo, 409 "Sin folio disponible... registre un nuevo
  lote" — verificado en vivo que es exactamente el mensaje que exige el
  handoff (no un timeout de red). Las transiciones de estado
  (PENDIENTE_IMPRESION/FOLIO_ERROR → FOLIO_SOLICITADO → FOLIO_ASIGNADO/
  FOLIO_ERROR) no cambiaron — se conservó el `state_machine.py` existente
  a propósito, solo cambió qué pasa *entre* esas transiciones.
- **`app/services/certificado.py`**: `determinar_tipo_certificado` ahora
  distingue lo confirmado en el handoff — RECHAZADO (por prueba o por
  inspección visual) es el único caso que se infiere solo (un solo tipo
  posible); un resultado APROBADO exige que el Operador de Impresión mande
  `tipo_certificado` (Particular/Doble Cero/Intensivo) porque no hay regla
  de elegibilidad automática todavía. `POST /impresion/tipo-certificado/
  {id}` devuelve 422 (`TipoCertificadoRequiereSeleccionManual`) si un
  aprobado no manda el parámetro, o si alguien intenta mandar RECHAZO en
  un aprobado. `vista-previa`/`imprimir` ya NO infieren el tipo por su
  cuenta (antes tenían un fallback a `determinar_tipo_certificado` sin
  selección manual) — ahora exigen que `certificado_tipo` ya esté fijado,
  409 si no.
- **Frontend**: `ImpresionView.vue` muestra un `v-select` con los 3 tipos
  aprobados solo cuando `resultado_final === "APROBADO"` (nunca para
  RECHAZO, que se sigue infiriendo solo); `SupervisorView.vue` tiene una
  pestaña nueva "Folios" con el resumen de inventario y el formulario de
  alta de lote por rango.
- **Migración** `5519017f44f2`: dropea `folio_requests`/`folio_assignments`
  (y sus tipos ENUM de Postgres) y crea `folio_lotes`/`folios`.
- Probado end-to-end contra el backend real con Chrome (no solo pytest):
  login como `supervisor1`, alta de lote `OAX-000001..5` PARTICULAR desde
  la pestaña Folios, login como `operador1` en la estación de Impresión
  simulada (`VITE_DEVICE_IDENTIFIER=IMPRESION-REFORMA-01`), selección
  manual PARTICULAR para el expediente diésel aprobado de `seed_demo`
  (`MKD-674-D`) → folio real `OAX-000001` asignado → imprimir → cerrar;
  y el camino RECHAZO de `RSC-238-F` (se infiere solo, sin selector) contra
  un inventario RECHAZO vacío → 409 "Sin folio disponible" correcto. Ambos
  expedientes de `seed_demo` se restauraron a mano a `PENDIENTE_IMPRESION`
  (sin `certificado_tipo`/`folio_externo`/`cerrado_at`) y se borraron las
  filas de `event_log`/`sync_outbox` que generó la prueba manual, mismo
  cuidado documentado en la sesión del 2026-08-18 (la BD de dev es la
  misma que usa `pytest`). 132 pruebas, todas pasan.
- Commits sobre `etapa1-y-siox`, **NO pusheados todavía** (pendiente de
  confirmación explícita).

**Pendiente real (puntos 3-5 del orden sugerido, sin tocar en esta
sesión)** — ver el PDF de la revisión del Figma para el detalle exacto de
cada uno. **Punto 1 resuelto el 2026-08-26, ver sección más abajo.**
1. ~~Dividir `EstadoVerificacion.CERRADO` en `CERRADO_APROBADO`/
   `CERRADO_RECHAZADO`, más `PENDIENTE_DE_IMPRESION_RECHAZO` como estado
   propio del camino de rechazo.~~
2. El modelo de reimpresión completo del handoff (sección 3): folio
   DAÑADO antes de imprimir (el operador lo marca, sin motivo, no cuenta
   como reimpresión), corrección de tipo ANTES de imprimir (libera el
   folio viejo a DISPONIBLE), corrección de tipo o reimpresión DESPUÉS de
   imprimir (exclusiva de Supervisor, sin motivo obligatorio en corrección
   de tipo, con motivo en reimpresión por daño; el folio usado pasa a
   INVALIDADO, se conserva Hora Salida). El modelo `Folio` ya tiene los
   campos (`danado_at`, `invalidado_at`, `reemplazado_por_folio_id`) pero
   ningún endpoint los usa todavía.
3. `Certificate Result Projection Contract v1` (sección 4 del PDF):
   sobreimpresión con `projection_version`/`layout_version` por tipo de
   prueba, fuente única `resultado_prueba.normalized_payload` — hoy
   `generar_pdf_certificado` es un HTML mínimo de trazabilidad, no el
   contrato real.
4. Semestre y prórroga del certificado (concepto de negocio nuevo, sin
   representación en el backend — ver sección 5 del PDF).
5. Campos de propietario/domicilio y `PBV`/`Tracción` en `Vehiculo`
   (regla #5 del handoff, lista exacta de campos permitidos en la sección
   7 del PDF).
6. Checklist real de inspección visual (8 puntos específicos con
   Bueno/Malo/No aplica, sección 8 del PDF) — hoy sigue siendo el
   checklist de 8 puntos inventado en la sesión del 2026-08-14.

## Split de CERRADO en APROBADO/RECHAZADO (2026-08-26) — punto 1 del orden sugerido

Implementa el punto 1 pendiente de la sección "Orden de trabajo sugerido"
de la revisión del Figma (2026-08-24, sección 14): `EstadoVerificacion`
ya no tiene un `CERRADO` único — se reemplaza por `CERRADO_APROBADO`/
`CERRADO_RECHAZADO`, y el camino de rechazo (inspección visual o prueba)
usa su propia cola `PENDIENTE_DE_IMPRESION_RECHAZO` en vez de compartir
`PENDIENTE_IMPRESION` con el aprobado.

- **`app/models/enums.py`**: `EstadoVerificacion.CERRADO` eliminado,
  agregados `CERRADO_APROBADO`, `CERRADO_RECHAZADO`,
  `PENDIENTE_DE_IMPRESION_RECHAZO`.
- **`app/services/state_machine.py`**: `TERMINAL_STATES` ahora incluye
  ambos cierres; `INSPECCION_VISUAL_RECHAZADA` transiciona a
  `PENDIENTE_DE_IMPRESION_RECHAZO` (antes `PENDIENTE_IMPRESION`);
  `PRUEBA_FINALIZADA` puede ir a cualquiera de las dos colas según el
  resultado; `IMPRESO` transiciona a cualquiera de los dos cierres.
- **`app/api/routers/pruebas.py`** (`guardar_resultado`): la cola destino
  tras `PRUEBA_FINALIZADA` ahora depende de `resultado_final`
  (APROBADO → `PENDIENTE_IMPRESION`, RECHAZADO →
  `PENDIENTE_DE_IMPRESION_RECHAZO`) — antes ambos casos compartían
  `PENDIENTE_IMPRESION` sin distinción.
- **`app/api/routers/inspeccion.py`**: el rechazo visual (regla de negocio
  #3, salta directo a impresión) ahora entra a
  `PENDIENTE_DE_IMPRESION_RECHAZO`.
- **`app/api/routers/impresion.py`**: `cola_impresion` incluye
  `PENDIENTE_DE_IMPRESION_RECHAZO`; `cerrar_expediente` decide el estado
  de cierre según `certificado_tipo` — `RECHAZO` → `CERRADO_RECHAZADO`,
  cualquier otro (`PARTICULAR`/`DOBLE_CERO`/`INTENSIVO`) →
  `CERRADO_APROBADO`. Reusa el mismo dato que ya distingue la cola de
  impresión, no agrega una fuente nueva de verdad.
- **`app/api/routers/folios.py`**: `ESTADOS_SOLICITABLES` incluye
  `PENDIENTE_DE_IMPRESION_RECHAZO` — solicitar folio de un certificado de
  rechazo ya no depende de que comparta estado con el aprobado.
- **`app/api/routers/supervision.py`**: `ESTADOS_TERMINALES` (excluidos
  del monitor en vivo) ahora son los dos cierres + `CANCELADO`.
- **Migración `c6386724bf52`**: recrea el tipo ENUM `estado_verificacion`
  completo (mismo patrón de reemplazo total que la migración de folios del
  2026-08-25, no `ALTER TYPE ... ADD VALUE` con valores huérfanos) —
  `verificaciones.estado` y `event_log.estado_anterior`/`estado_nuevo`
  (ambas columnas usan el mismo tipo) se migran con un `USING` que reparte
  las filas `CERRADO` existentes por `certificado_tipo`
  (`RECHAZO` → `CERRADO_RECHAZADO`, cualquier otro → `CERRADO_APROBADO`);
  en `event_log` (bitácora, no estado autoritativo) el mapeo es siempre a
  `CERRADO_APROBADO` por simplicidad. `downgrade()` revierte ambos pasos.
  Ningún expediente estaba en `CERRADO` al aplicar la migración en esta
  base de dev, así que el mapeo no se ejerció con datos reales — solo
  probado por lectura del SQL generado.
- **`app/seed_demo.py`**: `RSC-238-F` (rechazado en inspección visual)
  nace en `PENDIENTE_DE_IMPRESION_RECHAZO`, no `PENDIENTE_IMPRESION`. La
  fila ya sembrada en la base de dev de sesiones anteriores no se
  actualiza sola (el seed es idempotente, `_existe()` se salta placas ya
  creadas) — se corrigió a mano por SQL directo para que el dato de demo
  siga coincidiendo con el seed actualizado.
- **Frontend**: `ImpresionView.vue` agrega
  `PENDIENTE_DE_IMPRESION_RECHAZO` a `ESTADOS_SOLICITABLES` (habilita
  "Calcular tipo de certificado"/"Solicitar folio" también desde la cola
  de rechazo). `ExpedienteHeader.vue`/`SupervisorView.vue`: se quitó la
  comparación exacta `estado === "CERRADO"` en `colorEstado` — ya no
  existe ese valor, y `CERRADO_APROBADO`/`CERRADO_RECHAZADO` ya caían
  correctamente en las ramas `includes("APROBAD")`/`includes("RECHAZAD")`
  existentes, así que el chip se sigue coloreando bien sin ese caso.
- **Pruebas nuevas**: `tests/test_pruebas.py::test_guardar_resultado_rechazado_va_a_cola_de_rechazo`
  (rechazo por prueba, no solo por inspección, también va a la cola
  propia) y `tests/test_impresion.py::test_cerrar_expediente_con_certificado_rechazo_llega_a_cerrado_rechazado`.
  4 pruebas existentes actualizadas (`test_inspeccion.py`,
  `test_impresion.py`, `test_folios.py`, `test_supervision.py`) que
  esperaban el `CERRADO`/`PENDIENTE_IMPRESION` únicos de antes. **134
  pruebas, todas pasan.** Build de frontend (`npm run build`) limpio.
- Verificado contra la base de dev real (no solo pytest): migración
  aplicada sin la base de datos corriendo pytest en paralelo, conteo de
  `estado` por fila antes/después, y la corrección manual de `RSC-238-F`
  confirmada por `SELECT` directo.
- Commit pendiente de crear y de confirmación explícita de push, como
  siempre en este proyecto.
- Pendiente real: puntos 2, 3 y 4-6 de la lista de arriba siguen sin
  tocar (modelo de reimpresión completo, `Certificate Result Projection
  Contract v1`, semestre/prórroga, propietario/domicilio/PBV/Tracción,
  checklist real de inspección visual).

## Modelo de reimpresión completo (2026-08-27) — punto 2 del orden sugerido

Implementa el punto 2 pendiente de la sección "Orden de trabajo sugerido"
de la revisión del Figma (sección 3 del PDF, "Folios e impresión — modelo
completo de reimpresión y cierre"). Backend completo; **frontend
pendiente** — ver "Pendiente real" al final de esta sección.

Aprovecha campos que el modelo `Folio` ya tenía sin cablear
(`danado_at`, `motivo_danado`, `invalidado_at`, `motivo_invalidacion`,
`reemplazado_por_folio_id`) — no hizo falta migración nueva. También cerró
un hueco preexistente: nada ponía nunca `Folio.estatus = IMPRESO` tras un
`/imprimir` exitoso (el inventario se quedaba en ASIGNADO para siempre);
`impresion._imprimir_y_registrar` ahora lo hace, tolerando el caso de
fixtures antiguas que asignan `folio_externo` como string suelto sin fila
real de `Folio` (no rompe con `folio is None`).

**"Hora Salida" del handoff no es una columna nueva**: es
`PrintJob.created_at`. El `PrintJob` se crea una sola vez, en el primer
clic en Imprimir, *antes* de generar el PDF y llamar a la impresora
(mismo orden que pedía el handoff); todo intento posterior —reintento
técnico, reimpresión por daño, corrección de tipo— reusa esa misma fila en
vez de crear una nueva, así que `created_at` nunca se vuelve a tocar sin
necesidad de un campo dedicado.

- **Folio dañado ANTES de imprimir** (`POST
  /api/impresion/folio/marcar-danado/{id}`, `requiere_estacion(IMPRESION)`,
  sin Supervisor ni motivo — no cuenta como reimpresión): solo desde
  `FOLIO_ASIGNADO` con el folio actual en estatus `ASIGNADO`. Marca el
  folio actual `DANADO` y toma atómicamente el siguiente folio disponible
  del mismo tipo (`asignar_siguiente_folio`, ya existente). Si el
  inventario de ese tipo también está agotado, el expediente cae a
  `FOLIO_ERROR` (transición nueva: `FOLIO_ASIGNADO → FOLIO_ERROR` en
  `state_machine.ALLOWED_TRANSITIONS`) — mismo estado que una solicitud de
  folio sin inventario, reintentable desde `/folios/solicitar` en cuanto
  haya un lote nuevo.
- **Corrección de tipo ANTES de imprimir**: el endpoint existente `POST
  /api/impresion/tipo-certificado/{id}` ahora cubre dos casos según el
  estado. En `PENDIENTE_IMPRESION`/`PENDIENTE_DE_IMPRESION_RECHAZO`/
  `FOLIO_ERROR` sigue siendo la selección inicial (sin cambios). En
  `FOLIO_ASIGNADO` con un tipo distinto al ya fijado, es la corrección
  "antes de imprimir": libera el folio previo a `DISPONIBLE` (no
  `DANADO`, no cuenta como reimpresión) y asigna atómicamente el
  siguiente folio del tipo nuevo. Si el tipo nuevo no tiene folio
  disponible, la operación completa se aborta sin tocar nada (ni el folio
  viejo ni `certificado_tipo`) — no hay `db.commit()` intermedio, así que
  el rollback implícito de `get_db` al propagar el 409 basta (mismo
  patrón que ya usaba `folios.solicitar` para sus 409). Llamar este
  endpoint con el expediente ya en `IMPRESO`/`CERRADO_*` ahora es 409
  (antes no había ningún guard de estado en el backend, solo el frontend
  deshabilitaba el botón) — la corrección posterior a imprimir es una
  operación distinta, ver abajo.
- **Reintento técnico posterior al primer Imprimir → exclusivo de
  Supervisor**: `POST /api/impresion/imprimir/{id}` seguía abierto a
  cualquier operador de Impresión incluso para reintentar desde
  `IMPRESION_FALLIDA`. Ahora, si el expediente está en `IMPRESION_FALLIDA`
  (ya hubo un clic y la impresora falló), el endpoint exige
  `can_supervise=True` (`app.api.deps.es_supervisor`, variante no
  bloqueante de `requiere_supervisor` que solo lanza 403 si el llamador la
  invoca) — el primer clic sigue sin necesitar Supervisor.
- **Reimpresión por certificado físico dañado** (`POST
  /api/impresion/folio/reimprimir-por-dano/{id}`, `requiere_supervisor`,
  `motivo: str` obligatorio en el body): solo desde `IMPRESO` o ya
  `CERRADO_APROBADO`/`CERRADO_RECHAZADO` (`ESTADOS_CON_CERTIFICADO_IMPRESO`
  — deliberadamente excluye `IMPRESION_FALLIDA`, donde nunca se imprimió
  nada físico y el camino correcto es el reintento técnico de arriba).
  Marca el folio actual `DANADO` con el motivo, toma el siguiente folio
  disponible del mismo tipo, y reimprime de inmediato (PDF + impresora +
  `PrintAttempt`, vía el helper compartido `_imprimir_y_registrar`) — el
  folio nuevo pasa a `IMPRESO` si la reimpresión física tiene éxito. El
  estado del expediente **no cambia** (ni siquiera si ya estaba
  `CERRADO_*`): es una operación de datos, no una transición de la máquina
  de estados. Si la reimpresión física falla, el folio nuevo se queda en
  `ASIGNADO` y una llamada posterior al mismo endpoint (mismo Supervisor,
  motivo ya no obligatorio) reintenta el envío físico sin volver a canjear
  folio — el endpoint distingue el caso por el estatus del folio actual
  (`IMPRESO` = primera reimpresión, `ASIGNADO` = reintento del envío ya
  autorizado).
- **Corrección de tipo DESPUÉS de imprimir** (`POST
  /api/impresion/tipo-certificado-post-impresion/{id}`,
  `requiere_supervisor`, sin motivo obligatorio — "la propia acción de
  corrección identifica la causa", cita del handoff): mismo gate de
  estado que la reimpresión por daño. El folio usado pasa a `INVALIDADO`
  (no `DANADO` — el papel no estaba defectuoso), se asigna un folio nuevo
  del tipo correcto y se reimprime con el mismo helper compartido.
  `RECHAZO` sigue sin admitir corrección manual en ningún sentido (ni
  como tipo nuevo, ni como tipo anterior a corregir) — se infiere solo,
  igual que en la selección inicial.
- **`_folio_actual(db, verificacion)`**: helper que resuelve la fila de
  `Folio` que corresponde al `folio_externo` vigente del expediente —
  nunca ambiguo, porque cada reemplazo actualiza `folio_externo` al string
  del folio nuevo, así que el string viejo deja de matchear la fila que
  reemplazó.
- Cadena de reemplazo trazable end-to-end vía
  `Folio.reemplazado_por_folio_id` en los tres casos (folio dañado antes
  de imprimir, reimpresión por daño, corrección de tipo post-impresión).
- **16 pruebas nuevas** en `tests/test_reimpresion.py` (folio dañado con y
  sin reemplazo disponible, corrección de tipo antes de imprimir con
  rollback implícito cuando no hay folio nuevo, guard de estado en el
  endpoint de "antes" una vez impreso, reimpresión por daño con y sin
  Supervisor/motivo, reimpresión funcionando con expediente ya
  `CERRADO_APROBADO`, corrección de tipo post-impresión incluyendo el
  bloqueo de RECHAZO y de "mismo tipo", y que `Folio.estatus` llega a
  `IMPRESO` tras un `/imprimir` exitoso). Más 2 pruebas actualizadas en
  `tests/test_impresion.py` para la nueva regla de Supervisor en el
  reintento técnico (una ajustada a usar sesión de supervisor, una nueva
  para el 403 sin supervisor). **151 pruebas, todas pasan.** No se probó
  contra Chrome en esta sesión — commit pendiente de crear y de
  confirmación explícita de push, como siempre en este proyecto.

**Pendiente real:**
1. **Frontend**: nada de esto tiene UI todavía. Hace falta en
   `ImpresionView.vue` (botón "Marcar folio dañado" en `FOLIO_ASIGNADO`,
   habilitar corrección de tipo también en ese estado) y en
   `SupervisorView.vue` o una vista de detalle de expediente accesible a
   Supervisor (reimpresión por daño con motivo, corrección de tipo
   post-impresión) — ninguna pantalla de Supervisor hoy permite abrir un
   expediente específico fuera del monitor/bitácora existentes, así que
   probablemente hace falta un punto de entrada nuevo (buscar por
   placa/folio) antes de poder construir los diálogos.
2. Puntos 3-6 de la lista original (`Certificate Result Projection
   Contract v1`, semestre/prórroga, propietario/domicilio/PBV/Tracción,
   checklist real de inspección visual) siguen sin tocar.
