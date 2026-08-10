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

Estado actual: **38 pruebas, todas pasan.**

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

Hallazgos menores de la revisión 2026-08-07 — **resueltos 2026-08-10**:
- `Verificacion.combustible_validado` ahora se escribe en `POST
  /api/obd/evaluar/{id}` al momento de evaluar, tomando el valor directamente
  del `Vehiculo` normalizado. `pruebas.py` ya lo lee correctamente.
- `POST /api/obd/evaluar/{id}` ya no acepta `tipo_vehiculo`/`combustible`/
  `modelo` del caller — los lee del `Vehiculo` via `selectinload`. Devuelve
  422 si el vehículo no tiene esos campos (expediente no normalizado).
  3 pruebas nuevas en `tests/test_obd.py` cubren el comportamiento.
