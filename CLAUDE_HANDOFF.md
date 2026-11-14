# Handoff Técnico de Arquitectura: Verificación Vehicular Oaxaca

**De:** Antigravity (AI Pair Programmer)  
**Para:** Claude (AI Assistant) & Sebas  
**Fecha de corte:** 13 de noviembre de 2026 (Semana 8 — Viernes)  
**Rama activa:** `frontend-impresion-central`, sobre `ce3a9fc` (en paridad previa con René en `f60fc9c`: Q8 lint en CI, X5-e, Q3 403 por estación, NOM-047 Opción A en ambos lados `a8d708b`, barrido X2-d `b9cf70b` y retiro de `backend/.venv` `fe5348e`). Este corte añade las pruebas de chip de sincronización para `HU-105`/`HU-110` en `ExpedienteHeader.test.js` (406/406 Vitest), la matriz `trazabilidad_hu_2026-11-13` y el ensayo completo de rollback D10 en `qa-oaxaca` incluyendo levantamiento posterior y `HTTPS 200`.  
**Estado upstream:** `origin/etapa1-y-siox` integrado en la rama; sin commits nuevos de René pendientes de integrar al momento del corte.  

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
   - **Prueba de humo `scripts/smoke_e2e_flujo.mjs`:** recorre Captura, Inspección, OBD, Prueba, Folio e Impresión hasta `IMPRESO` con fetch nativo. Validado contra un servidor simulado del contrato (equipo manual y simulador, y falla de impresión con código de salida 1 y sesiones cerradas); **ejecutado contra el backend real en Docker el 2026-11-05 (resultado reportado por el equipo): 17 de 17 pasos, expediente en `IMPRESO` y PDF generado**. Recorre la API, no las pantallas. Uso en `scripts/README.md`, sección 4.

6. **F4/F9 de René, matriz 2026-10-30 y propuesta NOM-047:**
   - **Merge `7d36cdc`:** F9 hace visible el contador `sincronizando` durante el envío por lotes (HU-104); F4 agrega el catálogo `cat_equipos` y el equipo resuelto por el servidor al guardar el resultado (HU-042, HU-102), con administración en `SupervisorView.vue`. `SupervisorView.test.js` pasó de 103 a 110 pruebas. **Suite Frontend: 397 pruebas en 11 suites al 100%.**
   - **Matriz de trazabilidad 2026-10-30:** HU-042, HU-101, HU-102 y HU-103 pasan a HECHO. HECHO sube a 100 HUs (358 SP, 88,2%); PARCIAL baja a 6 HUs (30 SP, 7,4%); DESFASADA_SHEET se mantiene en 4. HU-101 y HU-103 se promovieron porque `PENDIENTES` las une con HU-102 en el bloqueo B4, que el cliente respondió; esa promoción depende de la respuesta reportada y `PENDIENTES` todavía lista B4 como abierto. Matiz de HU-042: el equipo se fija al guardar el resultado, no al configurar la prueba. Las 24 citas nuevas de archivos y pruebas se verificaron contra el disco.
   - **Propuesta `docs/PROPUESTA_FLUJO_INSPECCION_VISUAL_NOM047.md`:** el rechazo directo por inspección visual y el OBD antes de la prueba **ya existen** en la máquina de estados; lo que cambia es la estación que registra la inspección visual (hoy Prueba, el cliente indica Captura) y el campo 001 del certificado (hoy parámetro fijo, el cliente indica ID del técnico, lo que requiere una clave por usuario). Recomienda mover la estación sin tocar los estados (Opción A). Sin código modificado y pendiente de coordinar con René.

7. **Auditoría de seguridad X1–X7, Fase A y script de desbloqueo (2026-11-04):**
   - **Auditoría:** `docs/AUDITORIA_SEGURIDAD_X1_X7.md` (evidencia por archivo y línea, brechas con severidad, mitigaciones y plan). La sección 3.3 de `PENDIENTES` se actualizó: X1, X2 y X6 ya estaban implementados (2026-10-21), X4 es correcto por diseño, **X3 (sin TLS) es el único hallazgo alto**, y X5 y X7 quedan parciales. Hallazgos que conviene recordar: 71 de 74 rutas con guarda (3 públicas a propósito), pero solo 19 de 32 rutas de supervisor con prueba de 403; la política de contraseñas acepta `Password123`; las acciones administrativas no dejan rastro.
   - **Fase A aplicada en ops:** `.gitignore` (`backups/`, `*.dump`, `*.sql.gz`, `certs/`); `POSTGRES_PASSWORD` obligatoria en `docker-compose.prod.yml` (validado con `docker compose config`) y sin contraseña de relleno en `.env.prod.example`, manual y `README.md`; nginx con límite de login de 30 peticiones por minuto por IP (el 429 devuelve JSON con `detail`), cabeceras de seguridad, `server_tokens off` y `X-Real-IP`. **La CSP está en modo enforcing desde el 2026-11-09** (auditada y validada en Chrome con las 5 vistas: login, captura, prueba, impresión, supervisor y vista previa de PDF blob, con 0 violaciones de CSP; visualización del 429 en login comprobada con una respuesta simulada). `nginx -t` se ejecutó en Docker el 2026-11-05 y pasó (con controles negativos que fallan como deben).
   - **Decisiones de arquitectura:** un servidor local autónomo por verificentro; TLS con certificado interno, autofirmado o CA local en la LAN y público (Let's Encrypt) en el VPS; auditoría administrativa en `EventLog`, lo cual **exige** que René haga nullable `verificacion_id` (o cree una tabla `admin_event_logs`) y ajuste el serializador de sincronización y la auditoría de supervisión.
   - **`scripts/desbloquear_usuario.sh` y `.ps1`:** desbloquean a un usuario bloqueado por intentos fallidos (sobre todo supervisores). No borran intentos ni inventan logins: anotan "(desbloqueado por soporte)" en el motivo. Probados con un `docker` simulado (validación, confirmación con `SI` exacto, simulación, SQL ASCII y sin el usuario dentro del texto); René probó el `.sh` (con `--simular` y real) contra un PostgreSQL 16 real el 2026-11-11, y el equipo el `.ps1` el 2026-11-12 en Windows contra Postgres real (5 fallos con 429, `-Simular` sin modificar nada y la ejecución real liberó al usuario). Uso en `scripts/README.md`, sección 5.
   - **Matriz 2026-11-04:** 101 HUs en HECHO (363 SP, 89,4%), 5 en PARCIAL (HU-041, 043, 044, 046 y 083, todas de equipos físicos, Fase 2) y 4 en DESFASADA_SHEET. HU-024 se cerró por decisión del equipo (el rechazo entra a `PENDIENTE_DE_IMPRESION_RECHAZO`).

8. **TLS en nginx, X3 (2026-11-04):**
   - **Implementado:** `scripts/generar_certificados.sh` (CA local y certificado de servidor, ECDSA P-256, 825 días; la llave de la CA queda en `certs/ca/` y nunca se monta); `frontend/nginx.conf` con HTTPS en el 443 (TLS 1.2 y 1.3) y el 80 solo redirigiendo; `docker-compose.prod.yml` publica `WEB_TLS_PORT` y monta `certs/server` en solo lectura (si faltan los certificados, `up` falla con un error claro). Manual: sección 3.3 (instalación de la CA en Windows, Firefox y Linux, renovación y problemas). HSTS queda comentado a propósito.
   - **Verificado:** el generador en Windows (OpenSSL 3.2) y Linux (WSL2, OpenSSL 3.0) y un handshake TLS real (TLS 1.3 con la CA instalada; rechaza nombre ajeno al certificado, estación sin la CA y TLS 1.1); el compose con `docker compose config`. `nginx -t` pasó en Docker el 2026-11-05, y con el nginx real levantado solo se comprobaron la redirección 80 a 443, las cabeceras, `server_tokens off` y el 429 en JSON del límite de login. Verificado además el 2026-11-12 con el nginx real con TLS (proyecto aislado `qa-oaxaca`, reportado por el equipo): redirección 301 a HTTPS, HTTP 200 validando `certs/ca/ca.crt` (en Windows `curl.exe` necesita `--ssl-no-revoke`, porque la CA no tiene CRL), CSP sin violaciones en las 5 vistas y en la vista previa del PDF, y el 429 real de nginx legible en `LoginView`. Esas pruebas usaron Chrome con `--ignore-certificate-errors`. El **2026-11-13** se cerró también la prueba con confianza real de CA en Windows: tras instalarla en `LocalMachine\Root` con `scripts/instalar_ca.ps1 -HuellaEsperada`, `curl.exe --ssl-no-revoke` sin `--cacert` devolvió `HTTP 200` y `scripts/smoke_e2e_ui.mjs` completó los **11/11 pasos** (`29.5 s`) contra `https://localhost` sin `--ignore-certificate-errors`.
   - **Cambio de comportamiento:** `docker compose up` ya no arranca sin certificados; hay que ejecutar antes el generador. El manual traía además una verificación errónea (`/api/health` no existe) que se corrigió.
   - **Valores definidos con el equipo (2026-11-04):** `scripts/generar_certificados.sh --hosts "verificentro.local,192.168.1.100"` (el script acepta `--hosts` con lista separada por comas; la IP se cambia por la que asigne el router de cada centro; `localhost` y `127.0.0.1` van siempre). Los nombres `.local` solo resuelven si la red lo permite (mDNS, DNS del router o `hosts`); si no, las estaciones abren por la IP, que también está en el certificado. Staging en la nube (`stg-analizador.verificacionoaxaca.com`): certificado público (Let's Encrypt), no la CA local.


9. **Cierre de NOM-047 y seguridad operativa (2026-11-09 al 2026-11-11):**
   - **NOM-047 Opción A, cerrada de ambos lados.** Frontend (`5e69677`): se retiró de `PruebaView.vue` el estado `INSPECCION_VISUAL_PENDIENTE` y el checklist duplicado; la inspección vive en `CapturaView.vue` con `InspeccionVisualCard.vue`. Backend (`a8d708b`): `inspeccion.py` solo acepta Captura y Prueba recibe 403. Campo 001: se imprime la `clave_tecnico` del técnico de la prueba o del rechazo, y si no la tiene, su `username`.
   - **CSP en modo enforcing** (`8102f46`): probada en Chrome con las vistas con sesión y la vista previa del PDF (el equipo reportó 0 violaciones); el 429 se vio bien con una respuesta simulada y, el 2026-11-12, con el 429 real de nginx con TLS.
   - **Operaciones:** puertos de desarrollo en `127.0.0.1` (X5-d), un solo juego de scripts de respaldo por plataforma (`respaldo.sh`/`restaurar.sh` en Linux, `backup_db.ps1`/`restore_db.ps1` en Windows; los formatos `.sql.gz` y `.dump` no son intercambiables; retención por defecto de 14 respaldos) y **rol de BD de mínimo privilegio preparado y sin aplicar en producción** (X5-e: `scripts/sql/minimo_privilegio.sql`, `docker-compose.minimo-privilegio.yml`, manual 3.6). René lo probó el 2026-11-11 contra PostgreSQL 16 real: el rol no puede `TRUNCATE`, `DROP`, `ALTER`, `CREATE TABLE`, `CREATE ROLE` ni leer `alembic_version`, y el smoke E2E de API pasó 17/17 con el backend conectado como ese rol, también con `inmutables=1`. El Compose combinado con TLS (servicio `migrate`) se levantó completo el 2026-11-12 en un proyecto aislado (`qa-oaxaca`, reportado por el equipo): migraciones hasta `e1f4a8c2d5b9`, backend `healthy` con `verificacion_app`, `bootstrap_prod` (40 límites NOM-041, 4 NOM-045, estaciones y supervisor) y smoke E2E de API 17/17 contra `https://localhost` con `inmutables=1`.
   - **X1-b evaluado (2026-11-11): mitigado, no cerrado.** El límite de nginx y el tope por IP no impiden bloquear a un usuario (bastan 5 fallos); lo que lo mitiga es la expiración a los 15 min, el botón *Desbloquear* del supervisor, el script de soporte y la IP real en `access_events`. Es un riesgo de disponibilidad: aceptable en la LAN con condiciones, y a implementar (bloqueo por usuario e IP) antes de exponer el sistema a internet. Aceptado por Sebas y el equipo de frontend para la LAN el 2026-11-11 (falta ratificarlo con René); el bloqueo por usuario e IP es requisito obligatorio antes de publicar en un VPS. Detalle en la auditoría.
   - **Instaladores de la CA para estaciones:** `scripts/instalar_ca.ps1` (Windows, `certutil`) y `scripts/instalar_ca.sh` (Linux, y `--nss` para Chrome/Chromium): validan que sea una CA vigente, comparan la huella SHA-256 y son repetibles. En Windows quedó probado el **2026-11-13** en `LocalMachine\Root` real (`Thumbprint 09AE3823FB741CD9230A70AD0D462C06AE2A21A4`) junto con `smoke_e2e_ui.mjs` (11/11 en `29.5 s` sobre `https://localhost` sin `--ignore-certificate-errors`); la versión de Linux sigue probada solo con comandos simulados (pendiente en Linux real y en las estaciones definitivas del verificentro). Uso en `scripts/README.md`, sección 7.
   - **Backend (reporte de René):** 643 pruebas aprobadas el 2026-11-09 más `test_rutas_protegidas.py` (66 casos de 403 por tipo de estación, Q3). No se re-ejecutó el backend aquí. Barrido de sesiones vencidas (X2-d) y R2 (`--workers 1`) documentado.

   - **Q8 resuelto (René, `18ebe0a`):** `ruff` en el backend (`backend/ruff.toml`) y `eslint` en el frontend (`frontend/eslint.config.js`, `npm run lint`), ambos en CI antes de las pruebas; frontend verificado con `npm run lint` (0 errores, 0 warnings) y Vitest en 406/406 al 2026-11-13 (11 suites). Tras un `git pull` hay que correr `npm --prefix frontend install` para tener el linter.
   - **D10 documentado y ensayado en ambiente aislado (2026-11-13):** el manual (secciones 7 y 8) trae el procedimiento de actualización del stack conservando datos (respaldo previo verificado, migraciones, verificación posterior y rollback restaurando el respaldo) y la sección 7 se alineó con `respaldo.sh` y `restaurar.sh`. En `qa-oaxaca` se completó el ensayo de 8.4 tras ejecutar `smoke_e2e_flujo.mjs` (17/17): respaldo `--no-owner`, restauración temporal, rollback con reaplicación de `minimo_privilegio.sql`, `up -d --wait`, `HTTPS 200`, API 200 y conteos intactos (`2` verificaciones, `5` folios, `58` filas de `sync_outbox`, `1` usuario). **Falta** ensayarlo sobre una copia de un respaldo de producción real.
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
│   ├── tests/                             # 643 pruebas backend en pytest (reporte de René, 2026-11-09; más las de Q3)
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
│   ├── tests/                             # 11 suites Vitest (406 tests passing)
│   │   ├── setup.js                       # ResizeObserver polyfill para Vuetify
│   │   ├── session.test.js                # 25 tests del store de sesión (incluye ?estacion=; 0 it.fails)
│   │   ├── LoginView.test.js              # 19 tests de LoginView (incluye HU-005, HU-006, HU-007)
│   │   ├── CapturaView.test.js            # 18 tests de CapturaView
│   │   ├── PruebaView.test.js             # 78 tests de PruebaView (avisos warning/success y persistencia)
│   │   ├── SupervisorView.test.js         # 103 tests de SupervisorView
│   │   ├── AdministracionPanel.test.js    # 61 tests de AdministracionPanel (CRUD y navegación)
│   │   ├── ImpresionView.test.js          # 25 tests de ImpresionView (incluye HU-006 y limpieza de fallbacks)
│   │   ├── ExpedienteHeader.test.js       # 13 tests del header (incluye HU-020, HU-037, HU-105 y HU-110)
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
│   ├── respaldo.sh / restaurar.sh         # Respaldo y restauración en Linux (producción, .sql.gz)
│   ├── smoke_e2e_flujo.mjs                # Prueba de humo del ciclo vehicular (Node 18+)
│   ├── smoke_carga_concurrencia.mjs       # Prueba Q4 de carga multi-línea, folios SKIP LOCKED, idempotencia y PDF concurrente
│   ├── sql/minimo_privilegio.sql          # Rol de BD de mínimo privilegio (X5-e), opcional y sin aplicar
│   ├── desbloquear_usuario.sh / .ps1      # Soporte: desbloquea usuarios bloqueados por intentos fallidos
│   ├── backup_db.ps1 / restore_db.ps1     # Respaldo y restauración en Windows (desarrollo, .dump)
│   └── README.md                          # Guía de respaldos y de la prueba de humo
├── docker-compose.yml                     # Compose de desarrollo local (db 5433, redis 6379, solo en 127.0.0.1)
├── docker-compose.prod.yml                # Compose de producción aislado (db, redis, backend, web)
├── docker-compose.minimo-privilegio.yml   # Override OPCIONAL: migraciones con el dueño y backend con rol de BD limitado (X5-e)
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
- **Backend:** 643 pruebas en Pytest (recuento de René del 2026-11-09, más las de Q3 de `f326084`; no se re-ejecutó aquí). Head de migraciones `e1f4a8c2d5b9`.
- **Frontend:** 406 pruebas en Vitest pasando al 100% (11 suites), re-verificadas el 2026-11-13 con el cierre de `HU-105` y `HU-110` en `ExpedienteHeader.test.js` (Vitest 406/406 en 11 suites, `eslint` limpio y build de 695 módulos). 100% de componentes cubiertos y 0 pruebas `it.fails`.
- **Compilación:** `npm run build` genera 695 módulos limpios sin errores.
- **Lint (Q8):** `npm run lint` en el frontend y `ruff` en el backend corren en CI; el equipo reportó el frontend con 0 errores y 0 warnings.
- **E2E y Carga (Q2 / Q4):** `scripts/smoke_e2e_flujo.mjs` (API, 17 pasos), `scripts/smoke_e2e_ui.mjs` (interfaz, 11 pasos) y `scripts/smoke_carga_concurrencia.mjs` (carga y concurrencia Q4) corridos en verde. El de carga validó el 2026-11-13 en `qa-oaxaca` (TLS + `verificacion_app` + `inmutables=1`) 12 expedientes en paralelo entre L1 y L2 (`9.69 s`), ráfaga atómica de 12 folios sobre lote de 10 (`1.52 s`, 10 únicos + 2 `409`), idempotencia `6×` (`504 ms`, 1 folio consumido) y 11 vistas previas PDF + 11 impresiones simultáneas (`28.0 s` / `25.8 s`, 0 `5xx` y 0 deadlocks). Note: WeasyPrint con `--workers 1` promedia ~20 s en ráfagas simultáneas de 11 PDFs. El smoke API de 17 pasos pasó también contra el backend real con mínimo privilegio (17/17).
- **Normativa NOM-047:** B4 cerrado (operación sin internet), inspección visual en Captura antes de cerrar la captura (Opción A), rechazo directo sin emisiones, OBD antes de la prueba y campo 001 = ID del usuario. **Sin confirmar:** si las plantillas son las mismas para aprobados y rechazados (choca con `_LAYOUT_RECHAZO`, ver sección 6 de la propuesta).

### 4.2 Siguientes Tareas Inmediatas

1. **Decisiones de seguridad:** ratificar con René la aceptación de X1-b en la LAN (el bloqueo por usuario e IP es obligatorio antes del VPS; ver auditoría) y decidir si se adopta el rol de BD de mínimo privilegio (X5-e) en producción.
2. **Ensayo completo de D10:** el respaldo (`--no-owner`, 111 013 bytes tras correr `smoke_e2e_flujo.mjs` 17/17), la restauración de prueba en `verificacion_prueba`, el rollback de 8.4 con `minimo_privilegio.sql` (`PUBLIC CONNECT` volvió de `t` a `f`) y el levantamiento posterior (`up -d --wait`, `migrate` en 0, `backend` `healthy`, `HTTPS 200`, API 200 y conteos intactos) ya quedaron comprobados en el proyecto aislado `qa-oaxaca` (2026-11-13); **falta** ensayar la actualización completa sobre una copia de un respaldo de producción real. El Compose de mínimo privilegio, el desbloqueo `.ps1`, la CSP y el 429 con nginx real ya están probados.
3. **Operar TLS (X3):** la instalación en `LocalMachine\Root` de Windows (`scripts/instalar_ca.ps1 -HuellaEsperada`) y `scripts/smoke_e2e_ui.mjs` (`11/11` pasos en `29.5 s` sin `--ignore-certificate-errors`) ya quedaron probados el 2026-11-13; falta instalar la CA en las estaciones definitivas del verificentro (con `scripts/instalar_ca.ps1` o `.sh` comparando huella), anotar el vencimiento del certificado (825 días; renovar con 60 días de margen), decidir cuándo activar HSTS y probar Let's Encrypt en el VPS (falta montar `/var/www/certbot` si se usa `--webroot`).
4. **Confirmaciones del cliente:** qué plantilla física imprime un rechazo visual y uno por emisiones (choca con `_LAYOUT_RECHAZO`; B1, B9 y S5) y si basta el `username` como respaldo del campo 001 cuando el técnico no tiene `clave_tecnico`.
5. **Bloqueos que siguen abiertos** en `PENDIENTES`: B10(a), B2, B3, B5 (hosting: el cliente entregó una ficha de hosting compartido incompatible; se requiere un VPS Linux, que Don Rubén tiene en revisión), B9 (papel real) y los demás de terceros. Las 5 HUs en PARCIAL se cierran con el hardware del proveedor, no con más código de interfaz.
6. **`git push`** de commits locales solo con confirmación explícita.
