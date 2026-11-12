# Verificación Vehicular Oaxaca — Guía del Proyecto (CLAUDE.md)

Sistema de control y certificación de emisiones vehiculares del Estado de Oaxaca.
- **Backend:** FastAPI (Python 3.12), SQLAlchemy 2 (async), PostgreSQL 16, Redis 7, WeasyPrint.
- **Frontend:** Vue 3, Vuetify 3, Pinia, Vue Router, Vite 6, Vitest 2.
- **Infraestructura:** Docker Compose, Nginx (Reverse Proxy & SPA), GitHub Actions CI.
- **Repo:** `Rene3FG/verificacion-oaxaca` | Rama activa de Sebas: `frontend-impresion-central` | Rama base: `etapa1-y-siox`.

---

## 1. Reglas Críticas y Propiedad de Archivos

1. **File Ownership Estricto:**
   - **Míos (Sebas):** `frontend/src/views/ImpresionView.vue` y `frontend/src/components/ExpedienteHeader.vue`. Además: pruebas unitarias en `frontend/tests/`, documentación en `docs/` y scripts en `scripts/`.
   - **De René (NO TOCAR):** Toda la carpeta `backend/**` (estrictamente solo lectura vía `read_file` o git; no modificar, stagear ni comitear), `SupervisorView.vue`, `CapturaView.vue`, `PruebaView.vue`, `LoginView.vue`, `TopAppBar.vue`.
   - **Compartidos (coordinar antes de editar):** `frontend/src/router/index.js`, `frontend/src/stores/session.js`, `frontend/src/api/client.js`, `frontend/src/plugins/vuetify.js`, `frontend/src/styles/main.css`.
2. **Entorno de Consola (Windows PowerShell):**
   - **NUNCA usar `&&`** para encadenar comandos (incompatible con PowerShell 5.1). Ejecutar comandos uno por uno o separados por `;`.
   - Ejecutar Git siempre con `--no-pager` (ej. `git --no-pager status`, `git --no-pager diff`).
   - Cero `git push` sin confirmación explícita previa del usuario.
   - Antes de cada commit, auditar con `git --no-pager diff --cached --stat` que no haya archivos de `backend/` incluidos accidentalmente.
3. **Idioma:** Todas las respuestas y explicaciones técnicas deben ser en español.

---

## 2. Comandos Clave

```powershell
# Pruebas de Frontend (Vitest: 11 suites, 402 tests pasando al 100%)
npm --prefix frontend test

# Compilación de Producción de Frontend (0 errores, 695 módulos)
npm --prefix frontend run build

# Prueba de humo del ciclo vehicular completo (requiere backend, Postgres y Redis arriba)
node scripts/smoke_e2e_flujo.mjs

# Pruebas de Backend (Pytest: 643 tests pasando al 100%, según René)
# Requiere contenedores Postgres/Redis arriba y DLLs de WeasyPrint en PATH
$env:WEASYPRINT_DLL_DIRECTORIES = "C:\msys64\ucrt64\bin;C:\msys64\mingw64\bin"
cd backend; .venv\Scripts\activate; python -m pytest -q

# Despliegue de Producción con Docker
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build

# Scripts de Respaldo y Restauración de Base de Datos (D4)
.\scripts\backup_db.ps1
.\scripts\restore_db.ps1 -BackupFile .\backups\archivo.dump
```

---

## 3. Arquitectura y Estructura del Sistema

- **Objeto Central:** `Verificacion` (Expediente). Ninguna operación vehicular se ejecuta sin expediente creado.
- **Transiciones de Estado:** `backend/app/services/state_machine.py`. Los cambios de estado son atómicos y registran eventos inmutables en `event_log`.
- **Identidad y Sesión:** `backend/app/api/deps.py` resuelve `SessionContext` desde el header `X-Session-Id`. Control de acceso por rol y estación (`requiere_estacion`). En 403, devuelve `permisos_asignados` (HU-007).
- **Resiliencia Offline (HU-104):** Operación ininterrumpida sin conexión sobre el servidor local de verificentro; transacciones en cola `sync_outbox` firmadas con SHA-256 enviadas al sistema central al restablecer el servicio.
- **Sobreimpresión de Certificados:** Formato A4 vertical con 3 talones idénticos (`app.services.certificado`). Se sobreimprimen datos por coordenadas sobre papel preimpreso oficial. Soporta `_LAYOUT_PARTICULAR`, `_LAYOUT_INTENSIVO` y `_LAYOUT_RECHAZO`. Márgenes calibrables en `cat_parametros_sistema`.

---

## 4. Estado Actual (Working State)

- **Backend:** 643/643 pruebas aprobadas (reporte de René 2026-11-09; migraciones `c8d2e6f1a3b7`, `d9e3f7a2b4c8` y `e1f4a8c2d5b9`, head `e1f4a8c2d5b9`).
  - Seguridad X1 (bloqueo 429 tras 5 fallos), X2 (timeout 30 min inactividad), X6 (complejidad de contraseñas).
  - Endurecimiento X1/X2/X4/X5/X6 (2026-11-04): tope de fallos por IP (`LOGIN_MAX_INTENTOS_IP`) y bcrypt contra hash ficticio (X1-a/c), IP desde `X-Real-IP` (X1-e), vida máxima de sesión `SESION_DURACION_MAX_H` y cierre de sesiones al cambiar permisos o contraseña (X2-a/b/c), `/docs` apagado con `APP_ENV=production` (X4-d), seeds bloqueados en producción (X5-b), contraseñas con palabras conocidas/leetspeak rechazadas (X6-a). Cerrados el 2026-11-09: X1-d, X2-e, X6-b (cambio de contraseña propio y `must_change_password`), X6-c (usuarios sin distinguir mayúsculas) y desbloqueo por supervisor. X2-d cerrado (barrido periódico, `services/sesiones_barrido.py`, `SESION_BARRIDO_INTERVALO_S`). Pendientes: X1-b (evaluado por Sebas 2026-11-11: aceptable en LAN, obligatorio antes de VPS) y X5-e (rol de BD de mínimo privilegio: probado 2026-11-11 contra Postgres real con smoke E2E, sin aplicar en producción; ver manual 3.6). Detalle en `docs/RESPUESTA_RENE_2026-11-09.md`.
  - X7-c CERRADO: auditoría de acciones administrativas en `event_log` (usuarios, permisos, parámetros, equipos, folios) vía `app/services/auditoria_admin.py`; eventos sin expediente solo con `modulo = 'administracion'`, no se encolan a `sync_outbox`.
  - Campo 001 RESUELTO: `clave_tecnico` en `cat_usuarios` (editable en `AdministracionPanel.vue`) y congelado como `technician_id` en la proyección (`expediente_impresion_central.py`). Imprime la clave del técnico de emisiones o del técnico que rechazó la inspección visual (o su `username` de respaldo).
  - Incidencias F1/F2 (`ERROR_INTEGRACION` y reintento explícito), F9 (lotes de sync visibles) y F4 (`cat_equipos` y resolución por estación).
  - Despliegue D1–D3 (Dockerfiles prod + Nginx) y CI D9 (`.github/workflows/ci.yml`).
  - Bloqueo B1 / HU-070 RESUELTO: layout `_LAYOUT_RECHAZO` integrado en `certificado.py` con `fecha_limite` y parámetro configurable `certificado_rechazo_dias_vigencia`.
  - HU-007 RESUELTO: `LoginView.vue` renderiza `permisos_asignados` en acceso denegado (Estado B).
  - Operaciones D4–D8: `scripts/respaldo.sh`/`restaurar.sh` (Linux), `backup_db.ps1`/`restore_db.ps1` (PowerShell; se retiraron los `.sh` duplicados el 2026-11-10), `python -m app.bootstrap_prod` (datos de arranque), rotación de logs en `docker-compose.prod.yml`, `README.md`. Puertos de desarrollo acotados a `127.0.0.1` (X5-d). La estación del equipo se fija con `?estacion=NOMBRE` en la URL (guardado en `localStorage`). Detalle en `docs/HISTORIAL_DETALLADO_PROYECTO.md`.
  - NOM-047 Opción A RESUELTO: Inspección visual en la caseta de Captura (`CapturaView.vue` con `InspeccionVisualCard.vue`), rechazo directo sin emisiones ante puntos en Malo; retirada de `PruebaView.vue` (2026-11-10).
- **Frontend:** 402/402 pruebas aprobadas en Vitest (11 suites: `session`, `TopAppBar`, `ExpedienteHeader`, `format`, `estado`, `ImpresionView`, `LoginView`, `CapturaView`, `PruebaView`, `SupervisorView`, `AdministracionPanel`; 100% de componentes cubiertos).
- **Build de producción:** 695 módulos compilados limpiamente en Vite (0 errores, 10.34s).

---

## 5. Índice de Documentación y Referencias (`docs/`)

Para consultar detalles específicos sin sobrecargar el contexto de la sesión activa:

| Archivo | Contenido |
|---|---|
| [`CLAUDE_HANDOFF.md`](file:///c:/Users/LENOVO%20330s/OneDrive/Escritorio/verificacion-oaxaca/verificacion-oaxaca/CLAUDE_HANDOFF.md) | **Handoff técnico reciente**, delta de cambios, variables `.env` y siguiente tarea prioritaria. |
| [`docs/HISTORIAL_DETALLADO_PROYECTO.md`](file:///c:/Users/LENOVO%20330s/OneDrive/Escritorio/verificacion-oaxaca/verificacion-oaxaca/docs/HISTORIAL_DETALLADO_PROYECTO.md) | **Historial histórico completo** de todas las sesiones de trabajo previas (agosto a octubre 2026, 197 KB). |
| [`docs/MANUAL_INSTALACION_Y_OPERACION.md`](file:///c:/Users/LENOVO%20330s/OneDrive/Escritorio/verificacion-oaxaca/verificacion-oaxaca/docs/MANUAL_INSTALACION_Y_OPERACION.md) | **Manual de instalación y operación (D6)** para servidores de verificentro, Nginx, Compose y estaciones. |
| [`docs/PENDIENTES_2026-10-20.md`](file:///c:/Users/LENOVO%20330s/OneDrive/Escritorio/verificacion-oaxaca/verificacion-oaxaca/docs/PENDIENTES_2026-10-20.md) | Lista de bloqueos externos (B1-B11) y supuestos de negocio reversibles (S1-S12). |
| [`docs/trazabilidad/trazabilidad_hu_2026-10-20.md`](file:///c:/Users/LENOVO%20330s/OneDrive/Escritorio/verificacion-oaxaca/verificacion-oaxaca/docs/trazabilidad/trazabilidad_hu_2026-10-20.md) | Matriz oficial de trazabilidad de las 110 Historias de Usuario (406 SP). |
| [`scripts/README.md`](file:///c:/Users/LENOVO%20330s/OneDrive/Escritorio/verificacion-oaxaca/verificacion-oaxaca/scripts/README.md) | Guía de uso de scripts de respaldo y restauración de PostgreSQL (D4). |
| [`MEMORY.md`](file:///c:/Users/LENOVO%20330s/OneDrive/Escritorio/verificacion-oaxaca/verificacion-oaxaca/MEMORY.md) | Bitácora técnica persistente de continuidad y estado de git. |
