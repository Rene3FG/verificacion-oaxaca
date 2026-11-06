# Lo que falta para terminar el sistema (corte 2026-10-20)

Commit base `4717b87` + pruebas de frontend. 445 pruebas de backend y 60 de frontend en verde.

## Fuentes revisadas

| Fuente | Fecha / estado | Qué aportó |
|---|---|---|
| Google Sheet "HU verificacion" (110 HU) | Última edición 2026-08-04 (verificado hoy en Drive, sin cambios) | Criterios de aceptación; base de `docs/trazabilidad/trazabilidad_hu_2026-10-20.*` |
| `CLAUDE.md` del repo (2 901 líneas, 60+ secciones) | Al día hasta 2026-10-19 | Cada "Pendiente real", supuestos reversibles y bugs conocidos |
| Plan hasta terminar (2026-10-01), Avances y bloqueos (09-30, 10-05, 10-08), Plan 3 semanas Sebas (09-28) | `~/Descargas` | Bloqueos B1–B5, preguntas Q1–Q12, fases 2–4 |
| Auditoría de cobertura del Sheet y de seguridad de Impresión (Sebas, 10-14), auditoría de errores y reintentos (Figma `#66:2950`) | `~/Descargas` | Cobertura reportada por Sebas, 3 discrepancias Sheet/realidad |
| Figma (extracción 08-24 y lista de frames 09-28) | **No se ha releído el canvas desde el 09-28** | Frames y contratos; el canvas no se puede leer como texto |
| Código | Hoy | `grep` de TODO/NotImplementedError, Dockerfile, compose, `main.py`, `deps.py`, login |

Límite: no volví a abrir el Figma ni corrí el sistema en Chrome para esta lista.

## 0. Una discrepancia entre fuentes que hay que resolver primero

La auditoría de Sebas (10-14) dice **94.5 % cubierto (104 de 110 HU, 348 de 367 SP)**. La matriz verificada (esta, por prueba citada) da **HECHO 86 de 110 (313 de 406 SP)** y **0 HU en SIN_EVIDENCIA**. No se contradicen del todo: Sebas cuenta como "cubierta" una HU que existe en código y UI aunque no tenga prueba automatizada; la matriz exige prueba o lo marca PARCIAL / SOLO_FRONTEND. Además usa 367 SP en vez de 406. **Antes de presentar un porcentaje al cliente hay que acordar una sola definición de "hecho".** Recomendación: la de la matriz (la que se puede defender con una prueba).

## 1. Bloqueado por terceros (no se puede avanzar solos)

| # | Qué falta | Quién | Qué desbloquea | HU / área |
|---|---|---|---|---|
| B1 | ~~Plantilla Word del certificado de RECHAZO y fecha límite~~ **RESUELTO 2026-10-22** (`RECHAZO.doc` recibida; layout `_LAYOUT_RECHAZO`, fecha límite = fin + 30 días, a confirmar con el cliente). Queda abierto: variante diésel y calibración contra papel real **Respuesta del cliente 2026-10-30:** las plantillas oficiales (Particular, Intensivo, Doble Cero) son las mismas para aprobados y rechazados e imprimen los valores obtenidos y la potencia por norma. **Por aclarar:** choca con `_LAYOUT_RECHAZO` (de `RECHAZO.doc`, sin holograma y con fecha límite); ver sección 6 de la propuesta de NOM-047 | Cliente | Certificado de rechazo correcto | HU-070, Etapa 9 |
| B2 | **Protocolo real de los equipos** (dinamómetro, analizador, opacímetro), puerto/URL por línea, secciones 03+ del Equipment Integration Contract | Proveedor / Luis | Reemplazar `SimuladorGateway` por el adaptador real | HU-041, 042, 043, 044, 046, 083 |
| B3 | **Sistema central de sincronización**: URL, autenticación, contrato. Hoy el cliente HTTP es un contrato **asumido** (upsert por id, `Idempotency-Key`) | Cliente / Luis | `enviar_uno_a_central` real; Etapa 12 completa | HU-101, 102, 103, 107 |
| B4 | ~~**Alcance de "sin internet"**: qué debe poder hacerse offline y qué no~~ **RESUELTO 2026-10-30**: respuesta del cliente (Luis, NOM-047): todo el proceso debe poder realizarse sin internet (captura manual sin consulta SIOX, prueba de gasolina o diésel e impresión de resultados). Cierra HU-101, 102 y 103 | Luis | Cerrar HU-101/102/103 | HU-101, 102, 103 |
| B5 | **Hosting y ambientes** (el cliente retuvo la tarea desde 2026-08-14). **Actualización 2026-11-03:** el cliente entregó la ficha técnica de Hostinger Cloud compartido (cPanel, PHP 7.0–8.5, MySQL), incompatible con la arquitectura (FastAPI, PostgreSQL 16, Redis y Docker); se requiere migrar a un VPS Linux (KVM) con Docker. **Actualización 2026-11-06:** Don Rubén confirmó que la migración a VPS está en revisión por su parte | Cliente | Despliegue; no existe ningún ambiente de producción | Entrega |
| B6 | **Reescribir en el Sheet las Etapas 8 y 12** ("sistema externo de folios" → "inventario local por lotes"; ~10 HU). Rubén y el cliente ya lo confirmaron | Luis | Que el QA mida contra criterios vigentes; 4 HU quedan DESFASADA_SHEET | HU-064, 065, 066, 068, 069, 070, 085, 086, 103, 106 |
| B7 | ~~**Q1: ¿inspección visual y OBD/SBD son de Captura o de Prueba?** Sheet y Figma dicen Captura; el código, Prueba (decisión 2026-08-07). Mover código solo tras su respuesta~~ **ACLARADO 2026-10-30 / RATIFICADO 2026-11-06** (Don Rubén): en el sistema actual la inspección visual (Bueno/Malo) está integrada dentro del módulo de captura de datos como último paso; una vez terminada la captura, si aprueba la inspección visual continúa con las demás pruebas (OBD cuando aplique y emisiones gasolina/diésel); si no aprueba es rechazo directo. Ratifica la Opción A de `docs/PROPUESTA_FLUJO_INSPECCION_VISUAL_NOM047.md`, pendiente solo del visto bueno formal de Luis | Luis | Mover la inspección visual a Captura (Opción A de la propuesta) | Etapas 3 y 4 |
| B8 | **Folio de reimpresión**: Q2 "Folio duplicado" (¿placeholder?) y Q3 "Nuevo folio" (¿campo manual o automático?). Hoy es automático | Luis | Cerrar reimpresión | Supervisión / Reimpresión |
| B9 | **Papelería real**: hoja de prueba impresa sobre el papel real para calibrar `certificado_offset_x/y_mm`; plantillas de Doble Cero y Rechazo si existen. **Respuesta del cliente 2026-10-30:** las plantillas de Particular, Intensivo y Doble Cero son las mismas oficiales para aprobados y rechazados. Sigue abierta la hoja de prueba sobre papel real y la discrepancia con `_LAYOUT_RECHAZO` (ver B1) | Cliente | Layout de sobreimpresión validado en papel | Etapa 9 |
| B10 | **Dudas del certificado abiertas** (10-12): (a) su sistema imprimió 7.8 en fase 5024 de una Tucson 2016 de 4 cilindros y la Tabla 1 da 11.4–14.1; ~~(b) el "001" cae en la fila Técnico, ¿es el técnico?~~ **(b) RESUELTO OFICIALMENTE 2026-11-06** (Don Rubén): el campo 001 hace referencia al Identificador del usuario del sistema. En certificados aprobatorios se imprime el ID del técnico que realizó la prueba de emisiones; en certificados de rechazo se imprime el ID del técnico que emitió el rechazo (en inspección visual o al término de la prueba de emisiones). **(a) sigue abierto** | Cliente | Potencia correcta y campo Técnico especificado | `potencia_dinamometro.py`, `certificado.py` |
| B11 | **Aprobación del PR #1** (rama `etapa1-y-siox` → `main`, más de 107 commits) y revisión formal | Luis | `main` hoy no se usa; está 1 commit detrás de origin | Entrega |

## 2. Supuestos reversibles que alguien debe confirmar o cambiar

El código funciona con estas decisiones tomadas "por defecto"; cada una vive en un solo lugar.

| # | Supuesto | Dónde cambiarlo |
|---|---|---|
| S1 | NOx y Factor Lambda solo se evalúan si el equipo los reporta; si exceden, rechazan | `evaluacion_prueba.PARAMETROS_OPCIONALES_GASOLINA` |
| S2 | Dilución CO+CO2 fuera de 13 %–16,5 % invalida la muestra (409 "repetir"), no rechaza | `MuestraInvalida` en `evaluacion_prueba` |
| S3 | El folio no va dentro del snapshot de proyección (SCHEMA literal) | `proyeccion_certificado.py` |
| S4 | "Nuevo folio" en reimpresión es automático | `impresion.py` / `folios.py` |
| S5 | Layout por método: diésel → Intensivo, todo lo demás → Particular. **Nota 2026-10-30:** el cliente indica que Particular, Intensivo y Doble Cero son las plantillas oficiales para aprobados y rechazados; revisar este supuesto junto con `_LAYOUT_RECHAZO` (ver B1) | `LAYOUT_VERSION_POR_METODO` |
| S6 | Gasolina propone dinámica por defecto; `gasolina_permite_cambio_estatica` | `cat_parametros_sistema` |
| S7 | Checklist NOM-045 se persiste como evidencia | Sección 2026-10-01 de CLAUDE.md |
| S8 | Sin rol Superadmin global: alta de lotes de folios y de centros va con `requiere_supervisor` | `requiere_supervisor` |
| S9 | Propietario = razón social completa (no se captura nombre y apellidos por separado) | Mapeo de marcadores del certificado |
| S10 | `<Mpio.>` y `<Estado>` salen como claves INEGI; solo existe catálogo de Oaxaca | `catalogo_inegi.py` |
| S11 | Valores válidos de "Tipo de verificación": Ordinaria / Extemporánea / Voluntaria / Reposición (Q9 nunca se respondió formalmente) | Enum de tipo de verificación |
| S12 | Prórroga única vigente para todo el sistema, no por centro | Servicio de semestre y prórroga |

## 3. Pendiente que **sí podemos hacer** sin esperar a nadie

### 3.1 Funcional

| # | Tarea | Detalle | HU |
|---|---|---|---|
| F1 | ~~**`ERROR_INTEGRACION` en prueba**~~ **HECHO 2026-10-21**: el error de comunicación o falla del equipo transiciona el expediente a `ERROR_INTEGRACION`, guarda detalle técnico/operativo y permite reintento explícito (`backend/app/api/routers/pruebas.py`, commit `53593dc`) | HU-054 |
| F2 | ~~**Incidencias de equipo en "Errores y reintentos"**~~ **HECHO 2026-10-21**: todo error de equipo crea una incidencia abierta visible en Supervisión (`backend/app/api/routers/supervision.py`, commit `53593dc`) | HU-083, Supervisión |
| F3 | ~~**Historial de incidencias**~~ **HECHO 2026-10-28**: filtro de incidencias abiertas vs resueltas derivado de la bitácora (`GET /supervision/incidencias?estado=abiertas|resueltas|todas`), con selector en `SupervisorView.vue` (commit `fe69352`) | Supervisión |
| F4 | ~~`equipo_id` real en `ResultadoPrueba`~~ **HECHO 2026-10-30**: catálogo `cat_equipos` (Administración › Equipos); el servidor resuelve el equipo por estación+método (analizador/opacímetro/escáner OBD), valida el que mande el cliente (422) y deja NULL si la línea no tiene un único equipo activo de ese tipo | HU-042, 102 |
| F5 | **Calibración periódica como bloqueo** | El contrato no la detalla; preguntar a Luis o al proveedor antes de construir | HU-041/044 |
| F6 | ~~Fila "Rol asignado" en acceso denegado~~ **HECHO 2026-10-22**: el 403 devuelve `permisos_asignados` y la pantalla lista las estaciones asignadas | HU-007 |
| F7 | **Pausar prueba** | No se hizo "porque sin equipo no hay nada que pausar"; se reevalúa con el adaptador real | HU-045 |
| F8 | ~~**HU-024: crear el `PrintJob` de rechazo al rechazar**~~ **RESUELTO 2026-11-04**: aclarado y cerrado en trazabilidad. Al rechazar en inspección visual el expediente transiciona a `PENDIENTE_DE_IMPRESION_RECHAZO`, ingresando a la cola de rechazo de Impresión Central; el `PrintJob` y su snapshot inmutable se generan al imprimir con folio asignado (contrato de proyección) | HU-024 |
| F9 | ~~Contador "sincronizando" siempre en 0~~ **HECHO 2026-10-30**: el lote se marca `SYNCING` y se confirma antes de enviar; cada fila confirma al terminar; las omitidas por corte vuelven a su estado; una `SYNCING` huérfana (>`SYNC_SYNCING_CADUCIDAD_S`, 900 s) vuelve a ser candidata | HU-104 |
| F10 | ~~Rango de lotes sin tope~~ **YA ESTABA HECHO** (`MAX_FOLIOS_POR_LOTE` = 10 000, desde 2026-09-22, con prueba en `test_folios.py`); esta lista estaba desactualizada | Folios |
| F11 | ~~**Catálogo de municipios fuera de Oaxaca**~~ **HECHO 2026-10-28**: catálogo INEGI nacional de las 32 entidades federativas (`backend/app/data/municipios_mexico.json`, 2 478 municipios) integrado en `catalogos.py`, `CapturaView.vue` y `PruebaView.vue` (commit `d276d5e`) | HU-016 |

### 3.2 Robustez de datos / sincronización

| # | Hallazgo | Riesgo |
|---|---|---|
| R1 | Un snapshot viejo reintentado después de uno nuevo podría sobrescribir el estado en el central si éste aplica "última llegada gana" | Hay que fijar en el contrato (B3) que resuelva por `created_at` del cuerpo |
| R2 | Con varios workers de uvicorn hay un bucle de sync automático por proceso | Envío duplicado inofensivo (idempotente); aun así, documentar "un solo worker" en el manual |
| R3 | `procesar_pendientes` mantiene la transacción abierta hasta 50 × 10 s con el central caído | Bloqueos largos; ya se mitigó con `SKIP LOCKED` y corte del lote, conviene vigilarlo en carga real |
| R4 | `PATCH` de vehículo ahora es 409 desde `IMPRESO`; antes se permitía en cualquier punto | Confirmar con el cliente que corregir datos con el papel impreso va por reimpresión supervisada |

### 3.3 Seguridad (cosas que **no encontré** en el código)

Auditoría completa del 2026-11-04 en `docs/AUDITORIA_SEGURIDAD_X1_X7.md` (evidencia por archivo y línea, brechas, mitigaciones y plan). El texto original de estos puntos se escribió el 2026-10-20, antes de implementar X1, X2 y X6; abajo el estado actual.

| # | Hallazgo | Por qué importa |
|---|---|---|
| X1 | ~~**Sin límite de intentos de login ni bloqueo de cuenta**~~ **RESUELTO 2026-10-21** (commit `4db2ed0`: 429 tras 5 fallos, bloqueo de 15 min). **Aplicado 2026-11-04** en nginx un límite de 30 peticiones por minuto por IP al login. **Quedan (backend):** IP real en la bitácora de accesos, bloqueo por (usuario, IP), igualar tiempos de respuesta y el endpoint de desbloqueo para supervisores (`POST /api/usuarios/{id}/desbloquear`). Desde 2026-11-04 hay un script de soporte: `scripts/desbloquear_usuario.*` | Fuerza bruta de contraseñas contra `POST /estaciones/login` |
| X2 | ~~**La sesión no caduca por inactividad**~~ **RESUELTO 2026-10-21** (commit `4db2ed0`: 30 min de inactividad). **Quedan (backend):** vencimiento absoluto de la sesión y cerrar sesiones al revocar permisos o restablecer la contraseña | Una estación abandonada queda abierta indefinidamente |
| X3 | ~~**El identificador de sesión (UUID) viaja en un encabezado sin TLS configurado**~~ **RESUELTO 2026-11-04 / VALIDADO 2026-11-05:** nginx termina TLS en el puerto 443 (TLS 1.2 y 1.3) y el 80 solo redirige; certificados con `scripts/generar_certificados.sh` (CA local para la red del verificentro; Let's Encrypt previsto para el VPS). Los certificados se validaron con handshake TLS en Windows y Linux, y la sintaxis de nginx con certificados montados fue validada exitosamente en Docker (`nginx: configuration file /etc/nginx/nginx.conf test is successful`). **Falta:** probar con un navegador e instalar la CA en las estaciones físicas | Sin HTTPS, cualquier equipo en la red lo puede capturar |
| X4 | ~~**No hay configuración de CORS**~~ **RESUELTO por diseño** (frontend y API comparten origen vía nginx; no agregar CORS). **Aplicado 2026-11-04:** cabeceras de seguridad y `server_tokens off` en nginx; la CSP queda en modo solo reporte hasta probarla en un navegador. Falta apagar `/docs` en producción (backend) | Hoy funciona porque Vite hace proxy en desarrollo; en producción exige que el frontend y la API compartan origen (proxy inverso) |
| X5 | **PARCIAL.** Producción no publica Postgres ni Redis. **Aplicado 2026-11-04:** `POSTGRES_PASSWORD` obligatoria en el compose, ejemplo sin contraseña de relleno, y `backups/`, `*.dump`, `*.sql.gz` y `certs/` ignorados por Git. **Quedan:** guarda de entorno del `seed` (crea `supervisor1` con contraseña pública), puertos de desarrollo en `127.0.0.1` y rol de BD de mínimo privilegio | Deben cambiarse y cerrarse antes de producción |
| X6 | ~~**Sin política de contraseñas ni rotación**~~ **RESUELTO 2026-10-21** (commit `f96eb1c`: bcrypt, letra y número, no igual al usuario, lista de comunes). **Quedan (backend):** ampliar la lista de comunes (hoy acepta `Password123` y `Oaxaca2026`), cambio de contraseña por el propio usuario y `must_change_password` | Cuentas con contraseñas triviales |
| X7 | **PARCIAL.** Las 74 rutas tienen autenticación (3 públicas a propósito) y los listados acotan por centro y línea de la sesión. **Quedan:** pruebas de 403 en 13 rutas de supervisor y varias de estación, y auditoría de acciones administrativas en `EventLog` (requiere migración de `verificacion_id` a nullable). Alcance por centro: baja prioridad (un servidor por verificentro) | Los otros routers (obd, pruebas, folios, supervisión, usuarios, parámetros) tienen la auditoría de rutas del 10-13 pero no pruebas 403 exhaustivas |

### 3.4 Despliegue y operación

| # | Falta |
|---|---|
| D1 | ~~**Imagen de producción**: el `Dockerfile` arranca con `--reload` y `docker-compose.yml` monta el código como volumen~~ **RESUELTO 2026-10-21** (`backend/Dockerfile.prod`, `frontend/Dockerfile.prod`, commit `3ed5c2b`: imágenes de producción sin montaje de volumen ni `--reload`; el frontend se construye en dos etapas) |
| D2 | ~~**Servir el frontend**: no hay Dockerfile ni servidor para `frontend/dist`; hay que decidir nginx (o similar) con proxy a `/api`~~ **RESUELTO 2026-10-21** (`frontend/nginx.conf`, commit `3ed5c2b`: nginx sirve el frontend compilado y hace proxy de `/api` al backend) |
| D3 | ~~**Compose / script de producción** con variables de entorno distintas, secretos fuera del repo, `restart: unless-stopped`~~ **RESUELTO 2026-10-21** (`docker-compose.prod.yml`, `.env.prod.example`, commit `3ed5c2b`: arranque productivo con `restart: unless-stopped`) |
| D4 | ~~**Respaldos de PostgreSQL** (política, frecuencia, restauración probada). El sistema es el registro oficial de verificaciones~~ **RESUELTO 2026-10-29** (`respaldo.sh` y `backup_db.ps1`, commits `08f8618` y `ec0794b`: scripts en bash y powershell con compresión, retención y prueba de restauración) |
| D5 | **Datos de arranque** del cliente: usuarios reales, estaciones, centros, líneas, lotes de folios, límites de emisión, parámetros. Hoy hay un `seed_demo`. **PARCIAL 2026-10-29**: herramienta lista (`python -m app.bootstrap_prod`, commit `9d6b14c`: carga idempotente de parámetros, límites NOM-041/045, estaciones por línea y el primer supervisor); faltan los datos reales del cliente (lotes de folios y usuarios operativos, que se dan de alta desde Administración) |
| D6 | ~~**Manual de instalación y de operación** (Fase 4) y las variables de entorno documentadas; no existe README en el repo~~ **RESUELTO 2026-10-29** (`docs/MANUAL_INSTALACION_Y_OPERACION.md` y `README.md`, commits `5e2ac29` y `ec0794b`) |
| D7 | **Monitoreo y bitácora de aplicación**: `/health` existe, pero no hay alertas ni rotación de logs. **PARCIAL 2026-10-29**: rotación de logs resuelta (`docker-compose.prod.yml`, commit `a3aeafd`: `json-file` con `max-size` 10m y `max-file` 5 en los 4 servicios); siguen sin hacerse las alertas y el monitoreo externo |
| D8 | ~~**Reloj y zona horaria** de los equipos de cada verificentro (los certificados llevan fecha y hora; ya hubo un desfase de 6 h en otro proyecto, vigilar aquí)~~ **RESUELTO 2026-10-29** en lo que depende del sistema (`docker-compose.prod.yml` y `README.md`, commit `a3aeafd`: `TZ=America/Mexico_City` en el backend y nota de operación para mantener el reloj sincronizado con NTP). Queda a cargo del cliente verificar el reloj de cada verificentro |
| D9 | ~~**CI**: no hay `.github/workflows`; las 445 + 60 pruebas solo corren a mano~~ **RESUELTO 2026-10-21** (`.github/workflows/ci.yml`, commit `3ed5c2b`: en cada push y pull request corre `pytest` contra Postgres, y `npm test` y `npm run build` del frontend) |
| D10 | **Migraciones en un ambiente nuevo**: se probó desde cero en la BD de pruebas, pero no un plan de actualización con datos reales entre versiones |

### 3.5 Pruebas y calidad

| # | Falta |
|---|---|
| Q1 | ~~Pruebas de frontend: hoy hay 60 (estado, sesión, TopAppBar, ExpedienteHeader). **Faltan** las vistas grandes: `ImpresionView` (1 053 líneas), `PruebaView`, `CapturaView`, `SupervisorView`~~ **RESUELTO 2026-10-23** (las cuatro vistas con suite: `ImpresionView` el 10-21, `CapturaView` el 10-22, `PruebaView` y `SupervisorView` el 10-23). Después se sumó `AdministracionPanel` (10-28): hoy hay 397 pruebas en 11 suites de Vitest y todos los componentes y vistas están cubiertos |
| Q2 | Pruebas de extremo a extremo (Puppeteer): se han hecho a mano contra uvicorn pero no están guardadas como suite repetible. **PARCIAL 2026-11-05:** el ciclo vehicular completo **por API** quedó automatizado y es repetible (`scripts/smoke_e2e_flujo.mjs`, Node.js 18+, 17 pasos de Captura a Impresión Central; validado contra el backend real en Docker con estado final `IMPRESO` y PDF generado con WeasyPrint). **Sigue abierto** un E2E de interfaz con navegador (el sentido original de esta fila): el script no recorre las pantallas |
| Q3 | Cobertura 403 por router: completa en `impresion.py`; `obd`, `pruebas`, `folios` tienen guards probados (09-30) pero no todas las combinaciones |
| Q4 | Pruebas de carga y concurrencia realistas (varias estaciones simultáneas, folios atómicos bajo carga) |
| Q5 | **UAT de las 41 pantallas contra el Figma**, con lista de diferencias (Fase 4). El Figma no se relee desde el 09-28 |
| Q6 | ~~HU en SOLO_FRONTEND sin prueba: HU-005, 006, 050, 058, 059, 060~~ **RESUELTO 2026-10-27** (categoría `SOLO_FRONTEND` erradicada, 0 HUs; HU-005 y HU-006 con las pruebas de `27f2a5a`) |
| Q7 | ~~HU PARCIAL por criterio ambiguo o sin prueba: HU-007, 037, HU-024~~ **RESUELTO 2026-11-04** (HU-007 resuelto 10-22, HU-037 resuelto 10-27, HU-024 cerrado 11-04: el rechazo ingresa a la cola de rechazo y el PrintJob se genera con folio asignado). 0 HUs ambiguas pendientes en software |
| Q8 | Linter / formateador (ni `ruff` ni `eslint` configurados) |
| Q9 | Ejecutar el plan de impresión **en papel real** con la impresora del cliente (B9) |

## 4. Resumen por área

| Área | Estado | Qué impide el 100 % |
|---|---|---|
| Captura / SIOX | Completa; resiliente a SIOX caído | Cerrado (F11 resuelto con catálogo INEGI nacional) |
| Inspección visual / OBD | Completa en código | B7 (¿Captura o Prueba?) |
| Prueba / equipos | Completa **contra el simulador** | B2 (adaptador real), F5 (calibración) |
| Impresión / folios | Completa; filtros y bitácora cerrados | B1, B8, B9, B10 |
| Supervisión / auditoría | Completa (F2 y F3 resueltos) | Ninguno pendiente en Fase 1 |
| Administración | Completa (usuarios, estaciones, parámetros, folios, límites) | S8 (Superadmin) |
| Sincronización | Cola local, reintentos, indicador "sin internet" listos | B3, B4, R1 |
| Seguridad | Autorización por estación/línea sólida | X1–X7 |
| Despliegue | **Casi completo (7/10 resueltos, 2 parciales)** | D5 (datos reales del cliente), D7 (alertas y monitoreo externo), D10 (plan de actualización entre versiones) y B5 |
| Documentación | CLAUDE.md muy completo; matriz, manual y esta lista | B6 |

## 5. Orden sugerido

1. **Esta semana, sin dependencias**: X1 y X2 (intentos de login y caducidad de sesión), F1 (`ERROR_INTEGRACION`), D1–D3 (imagen y servidor de producción), D9 (CI con las 505 pruebas).
2. **Enviar a Luis y al cliente en un solo mensaje**: B1, B2, B3, B4, B6, B7, B8, B9, B10 y los supuestos S1–S12 (para que digan "sí" o "cambiar").
3. **Con Sebas**: Q1/Q5 (pruebas de las vistas grandes y UAT contra el Figma), acordar la definición de "hecho" (sección 0).
4. **Cuando lleguen B2/B3**: adaptador real de equipos, cliente central, R1.
5. **Antes de entregar**: D4–D8 (respaldos, datos de arranque, manual, monitoreo), revisión de seguridad completa (X7).
