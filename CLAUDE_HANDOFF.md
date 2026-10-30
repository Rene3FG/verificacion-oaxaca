# Handoff Técnico de Arquitectura: Verificación Vehicular Oaxaca

**De:** Antigravity (AI Pair Programmer)  
**Para:** Claude (AI Assistant) & Sebas  
**Fecha de corte:** 29 de octubre de 2026 (Semana 7 — Jueves)  
**Rama activa:** `frontend-impresion-central` (merge de upstream `5bc31cd` integrado)  
**Estado upstream:** Upstream de René (`origin/etapa1-y-siox` en `a3aeafd`) integrado vía merge `5bc31cd` (conflictos solo en `.gitignore` y `CLAUDE.md`, resueltos).

---

## 1. Resumen de Avances Recientes (Delta)

1. **Merge de Upstream de René (`2beb0ba`):**
   - Se integraron los 5 commits de René (`bb37411`, `5d4e112`, `5e29783`, `03c219c`, `8564929`) sin conflictos.
   - **Bloqueo B1 y HU-070 RESUELTOS en Backend:** Se implementó `_LAYOUT_RECHAZO` en `backend/app/services/certificado.py` utilizando las coordenadas vectoriales de `RECHAZO.doc` (sin holograma, fecha límite a 30 días, configurable con `certificado_rechazo_dias_vigencia`). 
   - **HU-007 en Backend y LoginView:** El endpoint `POST /api/estaciones/login` responde 403 con `{"detail", "permisos_asignados": [{station_type, center_id, line_id}]}`. En `LoginView.vue`, el Estado B renderiza la fila *"Estaciones asignadas"*.
   - **Suite Backend:** Subió de 450 a **459 pruebas en Pytest (100% pasando)**.

2. **Suite de Pruebas Unitarias para `CapturaView.vue` (`9bf7083`):**
   - Creado [`frontend/tests/CapturaView.test.js`](file:///c:/Users/LENOVO%20330s/OneDrive/Escritorio/verificacion-oaxaca/verificacion-oaxaca/frontend/tests/CapturaView.test.js) con **18 pruebas unitarias en Vitest**.
   - Cobertura: detección de caseta, listado por centro/línea, creación por placa con error 422 Pydantic, apertura y cierre reactivo, flujo SIOX con recuperación ante conflicto HTTP 409, captura manual, persistencia con `limpiarPayload`, y guardias de normalización (combustible obligatorio, transición a `INSPECCION_VISUAL_PENDIENTE`).
   - **Suite Frontend:** Subió de 98 a **116 pruebas en Vitest (8 suites al 100% pasando)**. Build de producción verificado limpio (694 módulos).

2b. **HU-007 en `LoginView.test.js` y suite de `PruebaView` (`99a2b87`, `cbb46b8`):**
   - `LoginView.test.js`: 11 → 15 pruebas (estaciones asignadas, "Ninguna", tipo fuera de catálogo, limpieza en 401/`cambiarUsuario`).
   - Nuevo `frontend/tests/PruebaView.test.js` con 62 pruebas: lista por estados, inspección visual, OBD/SBD, configuración, preparación NOM-045, captura manual gasolina/diésel, integración con equipo (sondeo y `test_run_id`), reintento F2, interrupción y corrección de vehículo. Polyfill local de `visualViewport` para el diálogo de Vuetify.
   - **Suite Frontend: 182 pruebas en 9 suites al 100%** (antes de SupervisorView). Build limpio.
   - **Defecto conocido (de René, pendiente de aviso):** `cerrarExpediente()` borra `aviso.value` justo después de que `registrarInspeccion`, `guardarResultadoPrueba` (PruebaView) y `confirmarNormalizacion` (CapturaView) lo fijan; el operador nunca ve esos avisos. Las pruebas de PruebaView lo documentan con `it.fails` (quitar `.fails` al corregirlo). El caso de CapturaView está confirmado leyendo el código (`CapturaView.vue:305-306` fija el aviso y `:231` lo borra); aún sin prueba.

2c. **Suite de `SupervisorView` (`5fb62a1`) — cierra Q1:**
   - Nuevo `frontend/tests/SupervisorView.test.js` con **101 pruebas**: carga inicial y monitor, mensajes de error de los 9 cargadores, bitácora y reasignación de línea, permisos, errores y reintentos (bloqueo por estación, carreras de consultas obsoletas), sync, folios, límites de emisión, capacidad de dinamómetro, semestre y prórroga, reimpresión por daño, corrección de tipo y auditoría paginada. `AdministracionPanel` va stubbeado.
   - **Suite Frontend: 283 pruebas en 10 suites al 100%.** Build limpio (15.7 s). Q1 (vistas grandes con pruebas) CERRADO.
   - **4º caso del defecto de mensajes perdidos (de René):** `actualizarPermiso` (SupervisorView) fija `error.value` y luego `cargarPermisos()` lo pone en `null`; el supervisor nunca ve por qué se rechazó el cambio. Documentado con `it.fails`.
   - Defecto consolidado: 4 casos (PruebaView ×2 funciones, CapturaView ×1, SupervisorView ×1) del mismo patrón de reactividad: se fija un mensaje y una limpieza posterior lo borra. Al corregirse, quitar `.fails` en `PruebaView.test.js` (2 pruebas) y `SupervisorView.test.js` (1 prueba).

3. **Pruebas HU-005/006, Upstream Merge de Avisos y Matriz Semanal (`27f2a5a`, `a9bd56f`, `a1dc8a3`):**
   - **Pruebas HU-005 y HU-006 (`27f2a5a`):** 14 pruebas añadidas en `LoginView.test.js` (4), `TopAppBar.test.js` (7) e `ImpresionView.test.js` (3). **Categoría `SOLO_FRONTEND` erradicada al 100% (0 HUs)**.
   - **Merge de Upstream de René (`a9bd56f`):** Integrados commits `dd06270` y `d791bb8` de René desde `origin/etapa1-y-siox`. René implementó `avisoTipo` (warning/ámbar ante rechazos) y `cerrarExpediente(conservarAviso = true)` en `PruebaView.vue`.
   - **Actualización de `PruebaView.test.js` (`a1dc8a3`):** 62 → 78 pruebas. Retirados los 2 `.fails` (ahora pasan en verde) y agregadas 16 pruebas para `avisoTipo` y persistencia en lista. Queda únicamente 1 prueba `.fails` en `SupervisorView.test.js` (`actualizarPermiso`).
   - **Suite Frontend: 313 pruebas en 10 suites al 100% pasando.** Build limpio en 10.4s.
   - **Matriz de Trazabilidad 2026-10-27:** 96 HECHO (337 SP / 83.0%), 10 PARCIAL, 0 SOLO_FRONTEND, 4 DESFASADA_SHEET, 0 SIN_EVIDENCIA. Total 110 HUs / 406 SP.

4. **Modularización y Optimización de Contexto de IA:**
   - [`CLAUDE.md`](file:///c:/Users/LENOVO%20330s/OneDrive/Escritorio/verificacion-oaxaca/verificacion-oaxaca/CLAUDE.md) condensado a 6,440 caracteres (< 10k límite).
   - Historial histórico íntegro (197 KB) archivado en [`docs/HISTORIAL_DETALLADO_PROYECTO.md`](file:///c:/Users/LENOVO%20330s/OneDrive/Escritorio/verificacion-oaxaca/verificacion-oaxaca/docs/HISTORIAL_DETALLADO_PROYECTO.md).

5. **Merge de Upstream, Estación por URL y Matriz 2026-10-29 (`5bc31cd`, `c76435c`):**
   - **Merge `5bc31cd`:** integra `ec0794b`, `e71fdb2`, `9d6b14c` y `a3aeafd` de René: `scripts/respaldo.sh` y `restaurar.sh`, `README.md` de la raíz, `backend/app/bootstrap_prod.py` (datos de arranque de producción), rotación de logs en `docker-compose.prod.yml` y `?estacion=` en `session.js`. `.gitignore` conserva las exclusiones de ambos lados; las secciones nuevas de `CLAUDE.md` de René pasaron a `docs/HISTORIAL_DETALLADO_PROYECTO.md`. Los scripts `respaldo.sh`/`restaurar.sh` conviven con `backup_db.*`/`restore_db.*` (decisión: no romper el flujo Linux de René ni el soporte PowerShell).
   - **Pruebas de `session.js` (`c76435c`):** 11 pruebas nuevas de `resolverDeviceIdentifier()`: `?estacion=` gana y se guarda en `localStorage`, lectura de lo guardado, respaldo a `VITE_DEVICE_IDENTIFIER` y al valor de ejemplo, y resiliencia si `localStorage` lanza. Cada caso reimporta el módulo porque el valor se calcula al cargarlo.
   - **Defecto conocido (de René, `session.js`):** si el equipo se abre con `?estacion=NOMBRE` y `localStorage.setItem` lanza (modo privado, cuota), la excepción salta el `return` y el identificador de la URL se descarta en silencio; el equipo se identifica con el valor de build o el de ejemplo. Documentado con 1 `it.fails` en `session.test.js` (quitar `.fails` al corregirlo).
   - **Suite Frontend: 390 pruebas en 11 suites al 100%.** Build limpio.
   - **Matriz de trazabilidad 2026-10-29:** sin HUs promovidas; HECHO se mantiene en 96 (337 SP / 83.0%). HU-016 ya estaba en HECHO (el catálogo INEGI nacional amplía su evidencia, no su criterio) y HU-083 sigue en PARCIAL (falta la detección real del error por el equipo, Fase 2). Se amplió la evidencia de ambas con pruebas de backend y Vitest.
   - **Prueba de humo `scripts/smoke_e2e_flujo.mjs`:** recorre Captura, Inspección, OBD, Prueba, Folio e Impresión hasta `IMPRESO` con fetch nativo. Validado contra un servidor simulado del contrato (equipo manual y simulador, y falla de impresión con código de salida 1 y sesiones cerradas); **aún no se ha ejecutado contra el backend real**. Uso en `scripts/README.md`, sección 4.

---

## 2. Estado Actual de la Arquitectura y Árbol de Archivos

### 2.1 Árbol de Directorios Relevante
```text
verificacion-oaxaca/
├── .github/
│   └── workflows/
│       └── ci.yml                         # Workflow CI (Python 3.12 pytest + Node 22 npm test/build)
├── backend/
│   ├── alembic/                           # Migraciones de BD (Alembic)
│   ├── app/
│   │   ├── api/routers/                   # Endpoints FastAPI (auth, captura, pruebas, impresion, folios, supervision, sync, estaciones)
│   │   ├── core/                          # Configuración, db async/sync, redis, seguridad
│   │   ├── models/                        # Modelos SQLAlchemy (enums, verificacion, vehiculo, prueba, sync_outbox, etc.)
│   │   ├── schemas/                       # Esquemas Pydantic v2
│   │   └── services/                      # Lógica pura (certificado, proyeccion_certificado, equipos, auth, parametros)
│   ├── tests/                             # 459 pruebas backend en pytest
│   ├── Dockerfile.prod                    # Imagen de producción uvicorn (un solo worker por sync outbox)
│   └── requirements.txt                   # FastAPI, SQLAlchemy[asyncio], Alembic, WeasyPrint, greenlet, etc.
├── frontend/
│   ├── nginx.conf                         # Proxy inverso para /api/ -> backend:8000 y SPA router
│   ├── Dockerfile.prod                    # Build multi-stage Node 22 -> Nginx 1.27-alpine
│   ├── src/
│   │   ├── api/client.js                  # Axios client con interceptor de sesión
│   │   ├── components/                    # ExpedienteHeader.vue, TopAppBar.vue, etc.
│   │   ├── stores/session.js              # Pinia store (estacion, sesion, errorTipo, usuarioDenegado, permisosAsignados)
│   │   ├── utils/                         # catalogos.js, estado.js, format.js
│   │   └── views/                         # LoginView.vue, CapturaView.vue, PruebaView.vue, ImpresionView.vue, SupervisorView.vue
│   ├── tests/                             # 11 suites Vitest (390 tests passing)
│   │   ├── setup.js                       # ResizeObserver polyfill para Vuetify
│   │   ├── session.test.js                # 25 tests del store de sesión (incluye ?estacion=; 1 it.fails)
│   │   ├── LoginView.test.js              # 19 tests de LoginView (incluye HU-005, HU-006, HU-007)
│   │   ├── CapturaView.test.js            # 18 tests de CapturaView
│   │   ├── PruebaView.test.js             # 78 tests de PruebaView (avisos warning/success y persistencia)
│   │   ├── SupervisorView.test.js         # 103 tests de SupervisorView
│   │   ├── AdministracionPanel.test.js    # 61 tests de AdministracionPanel (CRUD y navegación)
│   │   ├── ImpresionView.test.js          # 25 tests de ImpresionView (incluye HU-006 y limpieza de fallbacks)
│   │   ├── ExpedienteHeader.test.js       # 9 tests del header
│   │   ├── TopAppBar.test.js              # 15 tests de barra y sync (incluye HU-005, HU-006)
│   │   ├── format.test.js                 # 7 tests de format y catalogos
│   │   └── estado.test.js                 # 29 tests de utilería de estado
│   └── package.json                       # Vue 3, Vuetify 3, Pinia, Vitest 2.1, @vue/test-utils
├── docs/
│   ├── trazabilidad/                      # Matriz de trazabilidad oficial 110 HUs (.csv y .md)
│   ├── HISTORIAL_DETALLADO_PROYECTO.md    # Historial completo previo (197 KB)
│   ├── MANUAL_INSTALACION_Y_OPERACION.md  # Manual operativo y de instalación D6
│   └── PENDIENTES_2026-10-20.md           # Lista maestra de bloqueos B1-B11 (B1 RESUELTO) y supuestos S1-S12
├── scripts/
│   ├── backup_db.sh / restore_db.sh       # Scripts Bash de respaldo D4 (Linux)
│   ├── respaldo.sh / restaurar.sh         # Variante de respaldo y restauración (René)
│   ├── smoke_e2e_flujo.mjs                # Prueba de humo del ciclo vehicular (Node 18+)
│   ├── backup_db.ps1 / restore_db.ps1     # Scripts PowerShell de respaldo D4 (Windows)
│   └── README.md                          # Guía de respaldos y de la prueba de humo
├── docker-compose.yml                     # Compose de desarrollo local (db 5433, redis 6379)
├── docker-compose.prod.yml                # Compose de producción aislado (db, redis, backend, web)
├── .env.prod.example                      # Plantilla de variables de producción
├── RECHAZO.doc                            # Plantilla oficial Word de rechazo entregada por el cliente
├── CLAUDE.md                              # Guía técnica condensada (< 10k chars)
├── MEMORY.md                              # Bitácora técnica persistente de continuidad
└── research_log.md                        # Registro histórico detallado de experimentos y comandos
```

---

## 3. Decisiones Técnicas y Convenciones Clave

1. **File Ownership (Innegociable):**
   - **Míos (Sebas):** `ImpresionView.vue`, `ExpedienteHeader.vue`. Además: `frontend/tests/*`, `docs/*`, `scripts/*`.
   - **De René (NO TOCAR):** `backend/**`, `SupervisorView.vue`, `CapturaView.vue`, `PruebaView.vue`, `LoginView.vue`, `TopAppBar.vue`.
   - **Compartidos (coordinar):** `router/index.js`, `session.js`, `client.js`, `vuetify.js`, `main.css`.
2. **Convenciones de Shell y Git:**
   - PowerShell: **NUNCA usar `&&`**; comandos separados por `;` o uno por uno.
   - Git: siempre `--no-pager`. No hacer `git push` sin confirmación previa del usuario.
   - Auditoría previa a cada commit: `git --no-pager diff --cached --stat` (0 archivos de backend, 0 archivos `.md`).

---

## 4. Estado Actual (Working State) y Próximos Pasos (TODOs)

### 4.1 Qué está 100% probado y funcional
- **Backend:** 459 pruebas en pytest pasando al 100% (último recuento registrado; no se re-ejecutó el 2026-10-29). `_LAYOUT_RECHAZO` integrado, login 403 con `permisos_asignados`, docker prod, CI y datos de arranque de producción listos.
- **Frontend:** 390 pruebas en Vitest pasando al 100% (11 suites). `SupervisorView` (103), `PruebaView` (78), `AdministracionPanel` (61), `estado` (29), `ImpresionView` (25), `session` (25), `CapturaView` (19), `LoginView` (19), `TopAppBar` (15), `ExpedienteHeader` (9), `format` (7). 100% de componentes cubiertos. Queda 1 prueba `it.fails` (defecto de `session.js`, ver sección 1, punto 5).
- **Compilación:** `npm run build` genera 694 módulos limpios sin errores.

### 4.2 Siguientes Tareas Inmediatas

1. **Ejecutar `scripts/smoke_e2e_flujo.mjs` contra el backend real** (Postgres y Redis arriba, `python -m app.seed` aplicado) y ajustar lo que difiera del contrato simulado.
2. **Avisar a René** del defecto de `?estacion=` con `localStorage` bloqueado (quitar el `.fails` cuando lo corrija) y del nuevo `CLAUDE.md` condensado con el historial en `docs/HISTORIAL_DETALLADO_PROYECTO.md`.
3. **Acordar con René qué juego de scripts de respaldo queda** (`respaldo.sh`/`restaurar.sh` o `backup_db.*`/`restore_db.*`) y si `README.md` de la raíz y `docs/MANUAL_INSTALACION_Y_OPERACION.md` se unifican.
4. **Bloqueos B2-B11 de `docs/PENDIENTES_2026-10-20.md`:** dependen de terceros (hardware del proveedor, papel real, hosting). Las 10 HUs en PARCIAL se cierran con ellos, no con más código de interfaz.
5. **`git push`** de los commits locales solo con confirmación explícita.
