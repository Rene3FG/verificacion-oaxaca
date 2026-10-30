# Sistema Web de Verificación Vehicular de Oaxaca

Backend FastAPI + SQLAlchemy + Alembic (PostgreSQL 16, Redis) y frontend Vue 3 + Vuetify 3 + Pinia.
Una instalación atiende un verificentro con tres tipos de estación: **Captura**, **Prueba** e **Impresión**
(más el módulo de **Supervisión/Administración**).

## Instalación en producción

Requisitos: Docker con el plugin Compose. El TLS lo termina un proxy inverso delante (este compose publica HTTP).

```bash
cp .env.prod.example .env.prod        # editar: contraseña de Postgres, WEB_PORT, CENTRAL_SYNC_*
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

El backend aplica `alembic upgrade head` al arrancar. Usar **un solo worker** (el bucle de sincronización es por proceso).
El estado se revisa con `docker compose ... ps` (el contenedor del backend tiene healthcheck sobre `/health`, que nginx no expone).

### Variables de entorno principales

| Variable | Qué hace | Default |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Base de datos | cambiar la contraseña |
| `WEB_PORT` | Puerto HTTP publicado | 80 |
| `EQUIPO_GATEWAY_MODO` | `manual` (el operador captura lecturas). **Nunca `simulador` en producción** | manual |
| `CENTRAL_SYNC_URL` / `CENTRAL_SYNC_TOKEN` | Central de sincronización; vacío = cola local sin envío | vacío |
| `LOGIN_MAX_INTENTOS` / `LOGIN_BLOQUEO_MIN` | Bloqueo de login tras intentos fallidos (0 apaga) | 5 / 15 |
| `SESION_INACTIVIDAD_MIN` | Caducidad de sesión por inactividad (0 apaga) | 30 |

## Datos de arranque (primer supervisor)

En producción no corre ningún seed: sin este paso nadie puede iniciar sesión.

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -e BOOTSTRAP_PASSWORD='...' backend \
  python -m app.bootstrap_prod --centro reforma --lineas 2 --usuario admin --nombre "Administrador"
```

Crea parámetros, límites NOM-041/045, estaciones por línea (Captura y Prueba) más una de Impresión, y el supervisor
con permiso en todos los tipos de estación. Es idempotente y no cambia contraseñas existentes. El `device_identifier`
de cada estación es su nombre (p. ej. `CAPTURA-REFORMA-L1`); cada equipo se configura una sola vez abriendo
`http://servidor/?estacion=CAPTURA-REFORMA-L1` (se guarda en ese navegador; en desarrollo basta `VITE_DEVICE_IDENTIFIER`). Usuarios, permisos y lotes de folios se dan de alta después desde Administración.

## Respaldos (el sistema es el registro oficial de verificaciones)

```bash
scripts/respaldo.sh /var/respaldos/verificacion     # dump comprimido, conserva los últimos 14 (RETENCION=n)
scripts/restaurar.sh respaldos/verificacion_AAAAMMDD_HHMMSS.sql.gz   # DESTRUYE la base actual
```

Programar el respaldo con cron (diario 02:00):
`0 2 * * * cd /ruta/verificacion-oaxaca && scripts/respaldo.sh /var/respaldos/verificacion`.
Copiar los archivos fuera del servidor y **probar una restauración** en un ambiente aparte antes de depender de ellos.

## Desarrollo

```bash
docker compose up -d db redis                 # Postgres en 5433
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head && .venv/bin/python -m app.seed
.venv/bin/uvicorn app.main:app --reload       # :8000
.venv/bin/python -m pytest -q                 # usa la BD verificacion_test, no la de desarrollo
cd ../frontend && npm ci && npm run dev       # :5173
```

Usuarios de desarrollo (seed): `operador1`/`operador1`, `supervisor1`/`supervisor1`. **No existen en producción**:
los datos de arranque reales (usuarios, estaciones, centros, lotes de folios, límites) se cargan desde Administración.

## Más documentación

- `CLAUDE.md`: arquitectura, decisiones de producto y supuestos reversibles, sección por sección.
- `docs/PENDIENTES_2026-10-20.md`: lo que falta y quién lo desbloquea.
- `docs/trazabilidad/`: matriz HU → código → prueba.

## Operación

- **Logs:** Docker los rota solos (10 MB × 5 archivos por contenedor). Ver: `docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f backend`.
- **Reloj y zona horaria:** los certificados llevan fecha y hora. El servidor usa `America/Mexico_City` (variable `TZ` del backend); mantener el reloj del servidor sincronizado (NTP) y revisar que las estaciones muestren la misma hora.
