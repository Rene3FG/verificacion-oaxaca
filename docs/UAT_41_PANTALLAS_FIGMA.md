# UAT de las 41 Pantallas contra Figma y Lista de Diferencias (`Q5`)

**Fecha de consolidación:** 17 de noviembre de 2026  
**Rama / commit base:** `frontend-impresion-central` (`256b211`)  
**Archivo de diseño de referencia:** `Verificentros Oaxaca — Design System & Product UI` (`q34UUG34BxX8sWpaHmuqFq`, sección `03 — Product UI` y `04 — Flows & Handoff`)

---

## 1. Alcance, Fuentes y Límite Transparente

Este documento consolida el **Recorrido de Aceptación (UAT) de las 41 pantallas (`Q5`)** cruzando las especificaciones extraídas de Figma contra la implementación real al `2026-11-17` y su evidencia de pruebas automatizadas (`406/406` en Vitest y `11/11` en `scripts/smoke_e2e_ui.mjs` sobre HTTPS/TLS).

- **Fuentes de diseño utilizadas:**
  - Extracción literal de Dev Mode del `2026-08-24` e índice de frames de `03 — Product UI` verificado el `2026-09-28`.
  - Auditorías 1:1 con recortes en alta resolución (`36` capturas `figma_*.png`):
    - Acceso y Screen Flow Index (`2026-09-21`, frame `#105:4340` y `#95:3875`–`#98:3925`).
    - Captura (`2026-09-22`, frames `#31:97`–`#50:2115`).
    - Prueba en Fosa (`2026-09-23`, frames `#53:2232`–`#58:2609` y `#239:4554`–`#239:4838`).
    - Supervisión y Administración (`2026-09-24` y `2026-10-12`, frames `#65:2900`, `#66:2950`, `#72:3200`).
    - Impresión Central (`2026-09-28`, frames `y=7380` y `y=14480`).
  - Documentos de cierre y alineación de producto: `Verificacion Vehicular Oaxaca - Plan hasta terminar 2026-10-01.pdf` y `docs/PROPUESTA_FLUJO_INSPECCION_VISUAL_NOM047.md`.
- **Límite actual (`Requested`):** al `2026-11-17`, el acceso en vivo al enlace de Figma permanece en espera de aprobación (`Requested`). Por ello, esta matriz certifica todas las pantallas contra los frames documentados hasta el `2026-09-28`; al concederse el acceso, únicamente restará confirmar visualmente si diseño agregó o editó algún frame después de esa fecha.

---

## 2. Resumen Cuantitativo (41 / 41 Pantallas Cubiertas)

| Clasificación UAT | Conteo | Porcentaje | Significado operativo |
|---|---:|---:|---|
| **Alineada (sin brechas bloqueantes)** | **30** | **73.2 %** | Paridad visual, de estados y de tokens (`Sección 13`), con pruebas en Vitest/E2E. |
| **Diferencia ergonómica / arquitectónica aceptada** | **8** | **19.5 %** | Cambio deliberado de producto/arquitectura documentado (ver sección 5), funcional de extremo a extremo. |
| **Completa en simulador; pendiente hardware físico (`B2`)** | **3** | **7.3 %** | UI, estados y `EquipmentGateway` completos contra `SimuladorGateway` + captura manual; espera protocolo real de equipos. |
| **Total analizado** | **41** | **100.0 %** | `0` pantallas faltantes por construir en Fase 1. |

---

## 3. Matriz UAT Detallada (Pantallas 1 a 41)

### 3.1 Acceso y Errores (Pantallas 1–5)

| # | Frame en Figma (`03 — Product UI`) | Vista / Componente en Código | Estado UAT | Evidencia Automatizada | Diferencia / Observación |
|---:|---|---|---|---|---|
| 1 | Acceso / Login — Captura L1 (`#95:3875`) | `LoginView.vue` + `TopAppBar.vue` | Alineada | `LoginView.test.js` (23), `smoke_e2e_ui.mjs` (paso 3–4) | Detección de estación con chip verde *Configurada*, `TopAppBar` limpio sin chips de sesión, `?estacion=NOMBRE` en URL. |
| 2 | Acceso / Login — Prueba L1 (`#96:3886`) | `LoginView.vue` + `TopAppBar.vue` | Alineada | `LoginView.test.js`, `smoke_e2e_ui.mjs` (paso 6) | Mismo patrón; muestra metadata real de centro, línea y tipo `Prueba`. |
| 3 | Acceso / Login — Impresión Central (`#96:3927`) | `LoginView.vue` + `TopAppBar.vue` | Alineada | `LoginView.test.js`, `smoke_e2e_ui.mjs` (paso 1, 8) | Líneas múltiples (`allowed_line_ids`) y etiquetas flotadas `persistent-placeholder`. |
| 4 | Acceso / Error — Estación no configurada (`#98:3908`) | `LoginView.vue` (Estado A, 404/red) | Alineada | `LoginView.test.js` | Título *"No es posible iniciar sesión"*, guía *"Qué debe configurarse"* y botón *"Reintentar detección"*. |
| 5 | Acceso / Error — Sin permiso (`#98:3925`) | `LoginView.vue` (Estado B, 403) | Alineada | `LoginView.test.js` (HU-007) | Tarjeta de contexto con usuario, estación, fila **Estaciones asignadas** (`permisos_asignados`) y botón *"Cambiar usuario"*. *(Adicional pos-Figma: Estado D `must_change_password` para X6-b).* |

### 3.2 Estación de Captura (Pantallas 6–18)

| # | Frame en Figma (`03 — Product UI`) | Vista / Componente en Código | Estado UAT | Evidencia Automatizada | Diferencia / Observación |
|---:|---|---|---|---|---|
| 6 | Captura / Registro — Default (`#31:97`) | `CapturaView.vue` | **Diferencia aceptada** | `CapturaView.test.js` (24), `smoke_e2e_ui.mjs` (paso 4–5) | Funcionalidad y catálogos nacionales INEGI completos (`municipios_mexico.json`); usa layout de **1 columna** apilada en escritorio y guardados por bloque en vez de 2 columnas. |
| 7 | Captura / Registro — SIOX consultando (`#41:245`–`#41:1286`) | `CapturaView.vue` | Alineada | `CapturaView.test.js` | Estado de consulta activa con indicador de progreso y manejo de reintentos. |
| 8 | Captura / Registro — SIOX datos encontrados | `CapturaView.vue` | Alineada | `CapturaView.test.js` | Precarga vehículo/propietario y conserva historial de consulta SIOX. |
| 9 | Captura / Registro — SIOX sin datos (captura manual) | `CapturaView.vue` | Alineada | `CapturaView.test.js`, `smoke_e2e_flujo.mjs` | Habilita `POST /api/siox/captura-manual/{id}` para operar sin internet (`B4` / `HU-101`). |
| 10 | Captura / Registro — SIOX error / conflicto | `CapturaView.vue` | Alineada | `CapturaView.test.js` | Recuperación ante falla de red / timeout y conflicto `HTTP 409`. |
| 11 | Captura / Registro — Datos importados / normalizados | `CapturaView.vue` | Alineada | `CapturaView.test.js` | Guardias de validación de placa (`HU-010`), combustible obligatorio y normalización. |
| 12 | Captura / Inspección visual — Pendiente (`#36:1301`, `#44:1263`) | `CapturaView.vue` + `InspeccionVisualCard.vue` | Alineada | `CapturaView.test.js`, `smoke_e2e_flujo.mjs` | Reintegrada en caseta (`NOM-047 Opción A`, `5e69677`/`a8d708b`): 8 puntos con toggle *Bueno / Malo / No aplica*. |
| 13 | Captura / Inspección visual — Aprobada (`#46:1428`) | `CapturaView.vue` + `InspeccionVisualCard.vue` | Alineada | `CapturaView.test.js`, `smoke_e2e_flujo.mjs` | Transiciona a `INSPECCION_VISUAL_APROBADA` y avisa paso a la estación de Prueba. |
| 14 | Captura / Inspección visual — Rechazada (`#46:1623`) | `CapturaView.vue` + `InspeccionVisualCard.vue` | Alineada | `CapturaView.test.js` | Cualquier reactivo en *Malo* dispara banner ámbar, observaciones y rechazo directo (`PENDIENTE_DE_IMPRESION_RECHAZO`) omitiendo emisiones. |
| 15 | Captura / OBD-SBD — Evaluar / Pendiente (`#41:1700`, `#47:1758`) | `PruebaView.vue` | **Diferencia aceptada** | `PruebaView.test.js` (67), `smoke_e2e_flujo.mjs` | En el verificentro el escáner OBD/SBD conecta en fosa: vive en `PruebaView.vue` inmediatamente antes de gases, ratificado por Don Rubén (`B7`). |
| 16 | Captura / OBD-SBD — Sin comunicación / No aplica (`#49:1877`) | `PruebaView.vue` | **Diferencia aceptada** | `PruebaView.test.js` | Mismo traslado arquitectónico caseta → fosa; soporta `EXENTO` y `SIN_COMUNICACION` con motivo normativo. |
| 17 | Captura / OBD-SBD — Resultado recibido (`#49:2022`) | `PruebaView.vue` | **Diferencia aceptada** | `PruebaView.test.js`, `smoke_e2e_flujo.mjs` | Mismo traslado caseta → fosa; persiste en `resultados_obd_sbd` (`HU-032`). |
| 18 | Captura / Enviar a Prueba — Listo para Prueba L1 (`#50:2115`) | `CapturaView.vue` | **Diferencia aceptada** | `smoke_e2e_flujo.mjs`, `smoke_e2e_ui.mjs` | El despacho a Línea ocurre automáticamente al registrar la inspección visual aprobada con aviso de éxito, sin paso manual redundante de 4 tarjetas resumen. |

### 3.3 Estación de Prueba en Fosa (Pantallas 19–25)

| # | Frame en Figma (`03 — Product UI`) | Vista / Componente en Código | Estado UAT | Evidencia Automatizada | Diferencia / Observación |
|---:|---|---|---|---|---|
| 19 | Prueba / Cola de Prueba — Línea 1 (`#53:2232`) | `PruebaView.vue` | **Diferencia aceptada** | `PruebaView.test.js`, `smoke_e2e_ui.mjs` (paso 7) | Se presenta en `<v-list>` con estado normalizado (`textoEstado`) y botón de refresco en vez de tabla multicampo con columna previa de combustible/OBD. |
| 20 | Prueba / Dinámica gasolina — Esperando valores | `PruebaView.vue` | **Pendiente hardware (`B2`)** | `PruebaView.test.js` | Máquina de estados y polling (`DESCONECTADO` → `CALIBRANDO` → `LECTURA_RECIBIDA`) probados contra `SimuladorGateway`. |
| 21 | Prueba / Dinámica gasolina — Valores recibidos | `PruebaView.vue` | **Pendiente hardware (`B2`)** | `PruebaView.test.js`, `smoke_e2e_flujo.mjs` | Muestra lecturas del gateway (con candado `test_run_id` en servidor) y captura manual por fases Ralentí/Crucero (NOM-041). *(Adicional útil pos-Figma: acordeón de corrección de datos en fosa).* |
| 22 | Prueba / Dinámica gasolina — Resultado aprobado | `PruebaView.vue` | Alineada | `PruebaView.test.js` | Evaluado por el servidor contra `cat_limites_emision`; banner verde (`avisoTipo`) y envío a Impresión Central. |
| 23 | Prueba / Dinámica gasolina — Resultado rechazado | `PruebaView.vue` | Alineada | `PruebaView.test.js` | Banner ámbar (`warning`) visible al cerrar el expediente (`cerrarExpediente(true)`). |
| 24 | Prueba / Opacidad diésel — Preparación NOM-045 (`#239:4554`) | `PruebaView.vue` | Alineada | `PruebaView.test.js` | Exige marcar los 6 puntos de seguridad antes de habilitar la prueba; el backend valida `422` y persiste en `event_log`. |
| 25 | Prueba / Opacidad diésel — Valores y resultado (`#239:4838`) | `PruebaView.vue` | **Pendiente hardware (`B2`)** | `PruebaView.test.js` | Sondeo con simulador + captura manual estratificada por PBV (NOM-045) listos en espera del opacímetro real. |

### 3.4 Impresión Central (Pantallas 26–33)

| # | Frame en Figma (`03 — Product UI`) | Vista / Componente en Código | Estado UAT | Evidencia Automatizada | Diferencia / Observación |
|---:|---|---|---|---|---|
| 26 | Impresión / Cola Central | `ImpresionView.vue` | Alineada | `ImpresionView.test.js` (25), `smoke_e2e_ui.mjs` (paso 9) | Buscador por placa/folio/NIV (`HU-056`), filtros por estado (`HU-058`/`059`/`090`), línea y chip de certificado sugerido (`HU-053`). |
| 27 | Impresión / Expediente — Pendiente de folio | `ImpresionView.vue` + `ExpedienteHeader.vue` | Alineada | `ImpresionView.test.js`, `ExpedienteHeader.test.js` (13) | Incluye selector obligatorio `tipo_verificacion` (N2) si no viene de SIOX y chip de sincronización (`HU-105`/`110`). |
| 28 | Impresión / Expediente — Folio solicitado (`x=3100, y=14480`) | `ImpresionView.vue` | Alineada | `ImpresionView.test.js`, `smoke_carga_concurrencia.mjs` | Asignación atómica (`SKIP LOCKED`), idempotente ante reintentos simultáneos (`6/6 HTTP 200`, 1 folio consumido). |
| 29 | Impresión / Expediente — Folio asignado (`x=1540, y=7380`) | `ImpresionView.vue` | Alineada | `ImpresionView.test.js`, `smoke_e2e_flujo.mjs` | Vista previa PDF WeasyPrint en `blob:` sin violaciones CSP y paquete documental (`HU-072`/`074`, N3). Calibración en papel real pendiente de `B9`/`Q9`. |
| 30 | Impresión / Expediente — Error de folio (`x=4660, y=14480`) | `ImpresionView.vue` | Alineada | `ImpresionView.test.js`, `smoke_carga_concurrencia.mjs` | Banner rojo *"No se puede generar vista previa"*, bloqueo del botón de vista previa y reintento ante lote agotado (`HTTP 409`). |
| 31 | Impresión / Expediente — Error de impresora (`x=3100, y=7380`) | `ImpresionView.vue` | Alineada | `ImpresionView.test.js` | Título *"Error de impresora"*, banner rojo tonal con folio vigente y guard `reintentoRequiereSupervisor`. |
| 32 | Impresión / Expediente — Pendiente de cierre (`x=4660, y=7380`) | `ImpresionView.vue` | Alineada | `ImpresionView.test.js`, `smoke_e2e_flujo.mjs` | Título *"Salida enviada a impresora"*, banner verde *"Impresión completada"* y botón primario guinda *"Cerrar expediente"*. |
| 33 | Impresión / Expediente — Cerrado | `ImpresionView.vue` | Alineada | `ImpresionView.test.js`, `smoke_e2e_flujo.mjs` | Estado `CERRADO_APROBADO` / `CERRADO_RECHAZADO`, bloqueado contra mutaciones ordinarias (`HU-096`) y salida de cola. |

### 3.5 Supervisión y Administración (Pantallas 34–41)

| # | Frame en Figma (`03 — Product UI`) | Vista / Componente en Código | Estado UAT | Evidencia Automatizada | Diferencia / Observación |
|---:|---|---|---|---|---|
| 34 | Supervisión / Monitor general (`#72:3200`) | `SupervisorView.vue` (tab `monitor`) | Alineada | `SupervisorView.test.js` (111), `smoke_e2e_ui.mjs` (paso 11) | KPIs, tabla de expedientes en curso por línea, estado normalizado y acceso a modal de bitácora `<v-timeline>`. |
| 35 | Supervisión / Errores y reintentos (`#66:2950`) | `SupervisorView.vue` (tab `errores`) | Alineada | `SupervisorView.test.js`, `smoke_e2e_ui.mjs` (paso 11) | Resuelta la brecha de `2026-10-12`: muestra incidencias operativas (`F1`/`F2`/`F3`) con filtro `abiertas|resueltas|todas`, reintento supervisado y bloque `sync_outbox`. |
| 36 | Supervisión / Auditoría de eventos | `SupervisorView.vue` (tab `auditoria`) | Alineada | `SupervisorView.test.js`, `smoke_e2e_ui.mjs` (paso 11) | Cumple `N4`: filtros por fecha, usuario, placa y módulo, paginación y control de condición de carrera en consultas rápidas. |
| 37 | Supervisión / Reasignación (Permitida y Bloqueada, `#65:2900`) | `SupervisorView.vue` (`<v-dialog>` modal) | **Diferencia aceptada** | `SupervisorView.test.js` | Reasignación (`HU-114`) y motivo obligatorio implementados en diálogo modal sobre Monitor en vez de pantalla completa separada con los 3 checks estáticos; la regla se exige en backend (`409`). |
| 38 | Supervisión / Expediente cerrado — Acciones especiales y Reimpresión | `SupervisorView.vue` (tab `reimpresion`) | **Diferencia aceptada** | `SupervisorView.test.js`, `smoke_e2e_ui.mjs` (paso 11) | Canje por daño físico (`DAÑADO`) y corrección de tipo post-impresión operativos. El nuevo folio se asigna **automáticamente** desde inventario (`Q3`/`S4`, sin campo manual) y no se implementa *"Folio duplicado"* por ser un frame sin terminar en Figma. |
| 39 | Administración / Usuarios, Roles y permisos | `SupervisorView.vue` + `AdministracionPanel.vue` | Alineada | `AdministracionPanel.test.js` (67), `smoke_e2e_ui.mjs` (paso 11) | CRUD usuarios (con `clave_tecnico`, desbloqueo `POST /api/usuarios/:id/desbloquear` y badge de cambio de contraseña) + matriz de permisos por estación. Sin rol Superadmin global (`S8`: `requiere_supervisor`). |
| 40 | Administración / Estaciones | `AdministracionPanel.vue` | Alineada | `AdministracionPanel.test.js`, `session.test.js` (25) | Alta/edición de estaciones, `capacidad_dinamometro_kg` y selección por URL (`?estacion=NOMBRE`). |
| 41 | Administración / Parámetros, Catálogos, Equipos y Semestre | `AdministracionPanel.vue` | Alineada | `AdministracionPanel.test.js`, `SupervisorView.test.js` | Parámetros del sistema, catálogo `cat_equipos` (`F4`), límites NOM-041/045, lotes de folios (tope 10 000) y periodo/prórroga semestral. |

---

## 4. Brechas Históricas de Figma ya Cerradas (Sep–Nov 2026)

Para evitar falsos pendientes al revisar auditorías anteriores (`2026-09-21` a `2026-10-12`), quedan confirmadas como **ya resueltas e integradas**:
1. **`LoginView` Estados A, B y D (`2beb0ba`, `3ecbc54`):** Estación no configurada con reintento, Acceso denegado `403` con fila *Estaciones asignadas* (`HU-007`) y Cambio obligatorio de contraseña (`X6-b`).
2. **`NOM-047 Opción A` (`5e69677`, `a8d708b`):** Inspección visual de 8 puntos reintegrada en `CapturaView.vue` (`InspeccionVisualCard.vue`) con rechazo directo y bloqueo `403` en Prueba.
3. **`NOM-045` Diésel (`efde994`):** Checklist obligatorio de 6 puntos antes de opacidad con persistencia en `event_log`.
4. **Hitos `N1`–`N4` (`RECHAZO.doc` + `tipo_verificacion` + paquete documental `HU-072/074` + pestaña `Auditoría`):** Implementados y cubiertos por pruebas.
5. **Bandeja `Errores y reintentos` (`53593dc`, `fe69352`, `F1`/`F2`/`F3`):** Integrada en `SupervisorView.vue` con filtros `abiertas|resueltas|todas`.
6. **Catálogo `cat_equipos` (`8632769`, `F4`):** Administración y resolución por estación + método.
7. **Tokens institucionales `Sección 13`:** Aplicados de forma transversal en vistas, modales y diálogos (`#9D2449`, `#7A1C49`, Inter auto-hospedada, `.rounded-institucional-lg`, `.elevation-institucional-0`).

---

## 5. Lista Consolidada de Diferencias Vigentes (No Bloqueantes para Fase 1)

1. **Inspección OBD/SBD en fosa (`PruebaView.vue`) en vez de caseta (`CapturaView.vue`)** *(pantallas 15–17, decisión `B7`)*.
2. **Paso "Enviar a Prueba" implícito al confirmar inspección visual aprobada** *(pantalla 18)*.
3. **Formulario de Registro en Captura en 1 columna y guardado separado vehículo/propietario** *(pantalla 6, funcional pero candidato a mejora visual pos-entrega si el cliente lo pide)*.
4. **Cola de Prueba en `<v-list>` con estado normalizado** en vez de tabla multicampo *(pantalla 19)*.
5. **Reasignación de línea en `<v-dialog>` modal** en vez de vista dedicada con 3 checks visuales previos; la regla la garantiza el backend con `409` *(pantalla 37)*.
6. **Reimpresión con folio automático** desde inventario local (`Q3`/`S4`), omitiendo campo manual y el frame inconcluso *"Folio duplicado"* *(pantalla 38)*.
7. **Telemetría en vivo de analizador/dinamómetro y opacímetro** cubierta hoy con `SimuladorGateway` + captura manual hasta recibir protocolos del proveedor *(pantallas 20, 21 y 25; bloqueo `B2`)*.
8. **Mejora de seguridad y operación añadida sobre Figma:** Estado D (`must_change_password`), acordeón de corrección de datos en fosa (`PruebaView.vue`), chip de sincronización (`ExpedienteHeader.vue`), chip offline (`TopAppBar.vue`) y selector obligatorio de `tipo_verificacion` (`ImpresionView.vue`).

---

## 6. Checklist para Cierre Definitivo de `Q5` cuando se Apruebe Figma

Cuando se apruebe el acceso en `q34UUG34BxX8sWpaHmuqFq`:
- [ ] Revisar en Figma el historial de versiones / comentarios posterior al `2026-09-28`.
- [ ] Si hay frames nuevos o editados, anotar el delta en esta matriz.
- [ ] Confirmar con diseño/cliente (junto a `B1`/`B8`/`B9`) si las 8 diferencias ergonómicas y de flujo de la sección 5 quedan aprobadas definitivamente tal como operan.
