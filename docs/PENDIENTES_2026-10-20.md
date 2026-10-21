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
| B1 | **Plantilla Word del certificado de RECHAZO** y regla de la **fecha límite para la siguiente verificación**. Hoy el rechazo sale en el layout Particular | Cliente | Certificado de rechazo correcto | HU-070, Etapa 9 |
| B2 | **Protocolo real de los equipos** (dinamómetro, analizador, opacímetro), puerto/URL por línea, secciones 03+ del Equipment Integration Contract | Proveedor / Luis | Reemplazar `SimuladorGateway` por el adaptador real | HU-041, 042, 043, 044, 046, 083 |
| B3 | **Sistema central de sincronización**: URL, autenticación, contrato. Hoy el cliente HTTP es un contrato **asumido** (upsert por id, `Idempotency-Key`) | Cliente / Luis | `enviar_uno_a_central` real; Etapa 12 completa | HU-101, 102, 103, 107 |
| B4 | **Alcance de "sin internet"**: qué debe poder hacerse offline y qué no | Luis | Cerrar HU-101/102/103 | HU-101, 102, 103 |
| B5 | **Hosting y ambientes** (el cliente retuvo la tarea desde 2026-08-14) | Cliente | Despliegue; no existe ningún ambiente de producción | Entrega |
| B6 | **Reescribir en el Sheet las Etapas 8 y 12** ("sistema externo de folios" → "inventario local por lotes"; ~10 HU). Rubén y el cliente ya lo confirmaron | Luis | Que el QA mida contra criterios vigentes; 4 HU quedan DESFASADA_SHEET | HU-064, 065, 066, 068, 069, 070, 085, 086, 103, 106 |
| B7 | **Q1: ¿inspección visual y OBD/SBD son de Captura o de Prueba?** Sheet y Figma dicen Captura; el código, Prueba (decisión 2026-08-07). Mover código solo tras su respuesta | Luis | Posible reubicación de ~15 HU | Etapas 3 y 4 |
| B8 | **Folio de reimpresión**: Q2 "Folio duplicado" (¿placeholder?) y Q3 "Nuevo folio" (¿campo manual o automático?). Hoy es automático | Luis | Cerrar reimpresión | Supervisión / Reimpresión |
| B9 | **Papelería real**: hoja de prueba impresa sobre el papel real para calibrar `certificado_offset_x/y_mm`; plantillas de Doble Cero y Rechazo si existen | Cliente | Layout de sobreimpresión validado en papel | Etapa 9 |
| B10 | **Dudas del certificado abiertas** (10-12): (a) su sistema imprimió 7.8 en fase 5024 de una Tucson 2016 de 4 cilindros y la Tabla 1 da 11.4–14.1; (b) el "001" cae en la fila Técnico, ¿es el técnico? | Cliente | Potencia y campo Técnico correctos | `potencia_dinamometro.py`, `certificado_numero_equipo` |
| B11 | **Aprobación del PR #1** (rama `etapa1-y-siox` → `main`, más de 107 commits) y revisión formal | Luis | `main` hoy no se usa; está 1 commit detrás de origin | Entrega |

## 2. Supuestos reversibles que alguien debe confirmar o cambiar

El código funciona con estas decisiones tomadas "por defecto"; cada una vive en un solo lugar.

| # | Supuesto | Dónde cambiarlo |
|---|---|---|
| S1 | NOx y Factor Lambda solo se evalúan si el equipo los reporta; si exceden, rechazan | `evaluacion_prueba.PARAMETROS_OPCIONALES_GASOLINA` |
| S2 | Dilución CO+CO2 fuera de 13 %–16,5 % invalida la muestra (409 "repetir"), no rechaza | `MuestraInvalida` en `evaluacion_prueba` |
| S3 | El folio no va dentro del snapshot de proyección (SCHEMA literal) | `proyeccion_certificado.py` |
| S4 | "Nuevo folio" en reimpresión es automático | `impresion.py` / `folios.py` |
| S5 | Layout por método: diésel → Intensivo, todo lo demás → Particular | `LAYOUT_VERSION_POR_METODO` |
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
| F1 | **`ERROR_INTEGRACION` en prueba** | Ningún endpoint lo asigna. HU-054 pide guardar el estado de error con mensaje técnico y operativo y posibilidad de reintento; hoy solo existe la interrupción con motivo | HU-054 |
| F2 | **Incidencias de equipo en "Errores y reintentos"** | Un error de equipo se registra al interrumpir pero no queda abierto como incidencia | HU-083, Supervisión |
| F3 | **Historial de incidencias** | No hay tabla: "abierta" se deriva del estado. Por eso falta el filtro "Estado: abiertos / resueltos" del Figma | Supervisión |
| F4 | **`equipo_id` real en `ResultadoPrueba`** | Hoy "equipo" es la estación | HU-042, 102 |
| F5 | **Calibración periódica como bloqueo** | El contrato no la detalla; preguntar a Luis o al proveedor antes de construir | HU-041/044 |
| F6 | **Fila "Rol asignado" en acceso denegado** | Requiere que el 403 devuelva los permisos | HU-007 |
| F7 | **Pausar prueba** | No se hizo "porque sin equipo no hay nada que pausar"; se reevalúa con el adaptador real | HU-045 |
| F8 | **HU-024: crear el `PrintJob` de rechazo al rechazar** | El texto del Sheet lo pide al rechazar; hoy se crea al imprimir. Decidir si se cambia el código o el texto | HU-024 |
| F9 | **Contador "sincronizando" siempre en 0** | La fila `SYNCING` nunca es visible porque se confirma al final del lote | HU-104 |
| F10 | **Rango de lotes de folios sin tope** | Un supervisor puede registrar un rango arbitrariamente grande | Folios |
| F11 | **Catálogo de municipios fuera de Oaxaca** | Solo hay 570 municipios de Oaxaca | HU-016 |

### 3.2 Robustez de datos / sincronización

| # | Hallazgo | Riesgo |
|---|---|---|
| R1 | Un snapshot viejo reintentado después de uno nuevo podría sobrescribir el estado en el central si éste aplica "última llegada gana" | Hay que fijar en el contrato (B3) que resuelva por `created_at` del cuerpo |
| R2 | Con varios workers de uvicorn hay un bucle de sync automático por proceso | Envío duplicado inofensivo (idempotente); aun así, documentar "un solo worker" en el manual |
| R3 | `procesar_pendientes` mantiene la transacción abierta hasta 50 × 10 s con el central caído | Bloqueos largos; ya se mitigó con `SKIP LOCKED` y corte del lote, conviene vigilarlo en carga real |
| R4 | `PATCH` de vehículo ahora es 409 desde `IMPRESO`; antes se permitía en cualquier punto | Confirmar con el cliente que corregir datos con el papel impreso va por reimpresión supervisada |

### 3.3 Seguridad (cosas que **no encontré** en el código)

Verificado con `grep` en `main.py`, `deps.py`, `estaciones.py` y `services/auth.py`.

| # | Hallazgo | Por qué importa |
|---|---|---|
| X1 | **Sin límite de intentos de login ni bloqueo de cuenta** | Fuerza bruta de contraseñas contra `POST /estaciones/login` |
| X2 | **La sesión no caduca por inactividad**: sigue "activa" hasta cerrar sesión explícita o desactivar al usuario | Una estación abandonada queda abierta indefinidamente |
| X3 | **El identificador de sesión (UUID) viaja en un encabezado sin TLS configurado** | Sin HTTPS, cualquier equipo en la red lo puede capturar |
| X4 | **No hay configuración de CORS** | Hoy funciona porque Vite hace proxy en desarrollo; en producción exige que el frontend y la API compartan origen (proxy inverso) |
| X5 | **Credenciales por defecto** en `docker-compose.yml` (`verificacion` / `verificacion`) y Redis y Postgres expuestos a la red local | Deben cambiarse y cerrarse antes de producción |
| X6 | **Sin política de contraseñas ni rotación** (no encontré validación de complejidad) | Cuentas con contraseñas triviales |
| X7 | Revisión de seguridad completa prevista para la Fase 4 y aún no hecha; la auditoría de Sebas solo cubrió `impresion.py` (10 endpoints) | Los otros routers (obd, pruebas, folios, supervisión, usuarios, parámetros) tienen la auditoría de rutas del 10-13 pero no pruebas 403 exhaustivas |

### 3.4 Despliegue y operación (hoy no existe nada de esto)

| # | Falta |
|---|---|
| D1 | **Imagen de producción**: el `Dockerfile` arranca con `--reload` y `docker-compose.yml` monta el código como volumen |
| D2 | **Servir el frontend**: no hay Dockerfile ni servidor para `frontend/dist`; hay que decidir nginx (o similar) con proxy a `/api` |
| D3 | **Compose / script de producción** con variables de entorno distintas, secretos fuera del repo, `restart: unless-stopped` |
| D4 | **Respaldos de PostgreSQL** (política, frecuencia, restauración probada). El sistema es el registro oficial de verificaciones |
| D5 | **Datos de arranque** del cliente: usuarios reales, estaciones, centros, líneas, lotes de folios, límites de emisión, parámetros. Hoy hay un `seed_demo` |
| D6 | **Manual de instalación y de operación** (Fase 4) y las variables de entorno documentadas; no existe README en el repo |
| D7 | **Monitoreo y bitácora de aplicación**: `/health` existe, pero no hay alertas ni rotación de logs |
| D8 | **Reloj y zona horaria** de los equipos de cada verificentro (los certificados llevan fecha y hora; ya hubo un desfase de 6 h en otro proyecto, vigilar aquí) |
| D9 | **CI**: no hay `.github/workflows`; las 445 + 60 pruebas solo corren a mano |
| D10 | **Migraciones en un ambiente nuevo**: se probó desde cero en la BD de pruebas, pero no un plan de actualización con datos reales entre versiones |

### 3.5 Pruebas y calidad

| # | Falta |
|---|---|
| Q1 | Pruebas de frontend: hoy hay 60 (estado, sesión, TopAppBar, ExpedienteHeader). **Faltan** las vistas grandes: `ImpresionView` (1 053 líneas), `PruebaView`, `CapturaView`, `SupervisorView` |
| Q2 | Pruebas de extremo a extremo (Puppeteer): se han hecho a mano contra uvicorn pero no están guardadas como suite repetible |
| Q3 | Cobertura 403 por router: completa en `impresion.py`; `obd`, `pruebas`, `folios` tienen guards probados (09-30) pero no todas las combinaciones |
| Q4 | Pruebas de carga y concurrencia realistas (varias estaciones simultáneas, folios atómicos bajo carga) |
| Q5 | **UAT de las 41 pantallas contra el Figma**, con lista de diferencias (Fase 4). El Figma no se relee desde el 09-28 |
| Q6 | HU en SOLO_FRONTEND sin prueba: HU-005, 006, 050, 058, 059, 060 |
| Q7 | HU PARCIAL por criterio ambiguo o sin prueba: HU-007 (texto en pantalla), 037 (OBD/visual en el header), 024 |
| Q8 | Linter / formateador (ni `ruff` ni `eslint` configurados) |
| Q9 | Ejecutar el plan de impresión **en papel real** con la impresora del cliente (B9) |

## 4. Resumen por área

| Área | Estado | Qué impide el 100 % |
|---|---|---|
| Captura / SIOX | Completa; resiliente a SIOX caído | Solo catálogos fuera de Oaxaca (F11) |
| Inspección visual / OBD | Completa en código | B7 (¿Captura o Prueba?) |
| Prueba / equipos | Completa **contra el simulador** | B2 (adaptador real), F4, F5 |
| Impresión / folios | Completa; filtros y bitácora cerrados | B1, B8, B9, B10 |
| Supervisión / auditoría | Completa en Fase 1 | F2, F3 |
| Administración | Completa (usuarios, estaciones, parámetros, folios, límites) | S8 (Superadmin) |
| Sincronización | Cola local, reintentos, indicador "sin internet" listos | B3, B4, R1 |
| Seguridad | Autorización por estación/línea sólida | X1–X7 |
| Despliegue | **Nada listo** | D1–D10, B5 |
| Documentación | CLAUDE.md muy completo; matriz y esta lista | D6, B6 |

## 5. Orden sugerido

1. **Esta semana, sin dependencias**: X1 y X2 (intentos de login y caducidad de sesión), F1 (`ERROR_INTEGRACION`), D1–D3 (imagen y servidor de producción), D9 (CI con las 505 pruebas).
2. **Enviar a Luis y al cliente en un solo mensaje**: B1, B2, B3, B4, B6, B7, B8, B9, B10 y los supuestos S1–S12 (para que digan "sí" o "cambiar").
3. **Con Sebas**: Q1/Q5 (pruebas de las vistas grandes y UAT contra el Figma), acordar la definición de "hecho" (sección 0).
4. **Cuando lleguen B2/B3**: adaptador real de equipos, cliente central, R1.
5. **Antes de entregar**: D4–D8 (respaldos, datos de arranque, manual, monitoreo), revisión de seguridad completa (X7).
