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
`crear_permiso`, `crear_sesion_activa`, `crear_expediente`, y `client`/
`db_session` (cada test corre en un SAVEPOINT que se revierte al final, no
deja datos entre pruebas).

Estado actual: **86 pruebas, todas pasan.**

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

Otro hallazgo menor de la misma revisión, sin resolver:
- `POST /api/obd/evaluar/{id}` pide `tipo_vehiculo`/`combustible`/`modelo`
  como parámetros que debe mandar el caller, en vez de leerlos del
  `Vehiculo` ya poblado por HU-012 — inconsistente con la regla de negocio
  #6 ("el expediente completo, nunca solo placa/datos sueltos").

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
  (409) sin `vehiculo.combustible` y, de paso, **ahora sí escribe**
  `Verificacion.combustible_validado` (antes ningún endpoint lo hacía —
  ver hallazgo del 2026-08-06, ya resuelto). `guardar_resultado_prueba` en
  Prueba también rechaza (409) si falta, en vez de defaultear a cadena
  vacía.
