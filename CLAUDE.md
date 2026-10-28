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
# Pruebas de Frontend (Vitest: 10 suites, 315 tests pasando al 100%)
npm --prefix frontend test

# Compilación de Producción de Frontend (0 errores, 694 módulos)
npm --prefix frontend run build

# Pruebas de Backend (Pytest: 459 tests pasando al 100%)
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

- **Backend:** 459/459 pruebas aprobadas. 
  - Seguridad X1 (bloqueo 429 tras 5 fallos), X2 (timeout 30 min inactividad), X6 (complejidad de contraseñas).
  - Incidencias F1/F2 (`ERROR_INTEGRACION` y reintento explícito).
  - Despliegue D1–D3 (Dockerfiles prod + Nginx) y CI D9 (`.github/workflows/ci.yml`).
  - Bloqueo B1 / HU-070 RESUELTO: layout `_LAYOUT_RECHAZO` integrado en `certificado.py` con `fecha_limite` y parámetro configurable `certificado_rechazo_dias_vigencia`.
  - HU-007 RESUELTO: `LoginView.vue` renderiza `permisos_asignados` en acceso denegado (Estado B).
- **Frontend:** 315/315 pruebas aprobadas en Vitest (10 suites: `session`, `TopAppBar`, `ExpedienteHeader`, `format`, `estado`, `ImpresionView`, `LoginView`, `CapturaView`, `PruebaView`, `SupervisorView`; Q1 cerrado, fallbacks de ImpresionView limpiados).
- **Build de producción:** 694 módulos compilados limpiamente en Vite (0 errores).

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
