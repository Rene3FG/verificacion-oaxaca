# Checklist de Puesta en Marcha en Sitio — Verificentro (Fase 4)

**Fecha:** 19 de noviembre de 2026  
**Referencias:** `docs/MANUAL_INSTALACION_Y_OPERACION.md` (D6), `README.md`, `scripts/README.md` y `docs/PENDIENTES_2026-10-20.md`.

Este checklist resume los pasos verificables para la **primera instalación en vivo** de un verificentro usando el camino estándar de producción (TLS en Nginx + rol de mínimo privilegio `verificacion_app` + `APP_ENV=production`).

---

## 1. Servidor local, red y reloj (D8)

- [ ] Servidor Linux (Ubuntu Server 22.04/24.04 LTS o Debian 12) con Docker Engine v24+, Docker Compose v2+, `openssl` y `git`.
- [ ] IP fija asignada en la LAN del verificentro (p. ej. `192.168.1.100`); si se usa `verificentro.local`, resolución confirmada (DNS del router, mDNS o `hosts`).
- [ ] Reloj sincronizado con NTP y zona horaria `America/Mexico_City` verificada (`date`) en el servidor y en todas las estaciones.
- [ ] Repositorio clonado en `/opt/verificacion-oaxaca` con permisos de ejecución en scripts (`chmod +x scripts/*.sh`).
- [ ] Archivo `.env.prod` creado (`cp .env.prod.example .env.prod && chmod 600 .env.prod`) con:
  - [ ] `POSTGRES_PASSWORD` larga y única (generada con `openssl rand -base64 24`).
  - [ ] `APP_DB_USER=verificacion_app` y `APP_DB_PASSWORD` (16+ caracteres, solo letras y números).
  - [ ] `EQUIPO_GATEWAY_MODO=manual` (**nunca** `simulador` en producción).
  - [ ] `CENTRAL_SYNC_URL` y `CENTRAL_SYNC_TOKEN` configurados (o vacíos si opera en modo local).

---

## 2. Certificados TLS y CA local (X3)

- [ ] Generados la CA local y el certificado del servidor con el nombre e IP fija reales del centro:
  ```bash
  scripts/generar_certificados.sh --hosts "verificentro.local,<IP_FIJA>"
  ```
  *(Si el despliegue es en un VPS con dominio público, usar Let's Encrypt según sección 3.3 punto 4 del manual).*
- [ ] Anotada la **huella SHA-256 de la CA** (impresa por el script) para validarla al instalar en cada estación.
- [ ] Anotada la fecha de vencimiento del certificado del servidor (`openssl x509 -in certs/server/server.crt -noout -enddate`, vigencia 825 días) y agendada su renovación con 60 días de margen.
- [ ] Llave privada `certs/ca/ca.key` resguardada **fuera del servidor** (USB cifrada o gestor de secretos).

---

## 3. Primera instalación estándar con `verificacion_app` (X5-e, X4-d)

Definir la variable común para todos los comandos del stack:

```bash
COMPOSE="docker compose -f docker-compose.prod.yml -f docker-compose.minimo-privilegio.yml --env-file .env.prod"
```

- [ ] Validada la sintaxis y presencia de variables obligatorias:
  ```bash
  $COMPOSE config -q
  ```
- [ ] Ejecutadas las migraciones iniciales (`db` levanta sano y aplica `alembic upgrade head`):
  ```bash
  $COMPOSE run --rm --build migrate
  ```
- [ ] Creado el rol `verificacion_app` con `scripts/sql/minimo_privilegio.sql` (con la misma `APP_DB_PASSWORD` de `.env.prod`; agregar `\set inmutables 1` antes del `cat` para volver de solo escritura `event_log` y `access_events`):
  ```bash
  read -rsp "Contraseña APP_DB_PASSWORD: " APP_DB_PASSWORD; echo
  { printf '\\set app_user verificacion_app\n\\set app_password %s\n\\set inmutables 1\n' "'$APP_DB_PASSWORD'"; \
    cat scripts/sql/minimo_privilegio.sql; } \
  | $COMPOSE exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -'
  ```
  Confirmado el mensaje: `OK: rol verificacion_app creado o actualizado con privilegios mínimos.`
- [ ] Stack levantado en producción:
  ```bash
  $COMPOSE up -d --build
  ```
- [ ] Todos los servicios en estado correcto (`$COMPOSE ps`: `db`, `redis`, `backend`, `web` en `Up`/`healthy`; `migrate` en `Exited (0)`).
- [ ] Confirmado que `verificacion_app` no tiene privilegios de administración (`rolsuper`, `rolcreatedb`, `rolcreaterole` todos en `f`):
  ```bash
  echo "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = 'verificacion_app';" \
  | $COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
  ```
- [ ] Confirmado HTTPS, redirección 80→443 y apagado de `/docs` (`X4-d`):
  - [ ] `curl -I http://localhost/` devuelve `301` hacia `https://`.
  - [ ] `curl --cacert certs/ca/ca.crt -I https://localhost/` devuelve `HTTP/2 200`.
  - [ ] `curl --cacert certs/ca/ca.crt -I https://localhost/api/docs` y `/api/openapi.json` devuelven `404`.

---

## 4. Datos de arranque y alta operativa (D5)

- [ ] Cargados parámetros, límites NOM-041/NOM-045, estaciones base y primer supervisor con `bootstrap_prod`:
  ```bash
  $COMPOSE exec -e BOOTSTRAP_PASSWORD='<contraseña_temporal_fuerte>' backend \
    python -m app.bootstrap_prod --centro <centro> --lineas <N> --usuario <admin> --nombre "<Nombre>"
  ```
- [ ] Primer inicio de sesión del supervisor completado con cambio obligatorio de contraseña (`must_change_password`, `X6-b`).
- [ ] Dado de alta al menos un **segundo supervisor** (para contingencias de desbloqueo `X1`).
- [ ] Dados de alta los operadores reales con su **`clave_tecnico`** (campo `001` del certificado) y asignados sus permisos por estación y línea.
- [ ] Registrados los equipos físicos de cada línea en **Administración → Equipos** (`cat_equipos`, `F4`) y configurada `capacidad_dinamometro_kg` por estación de Prueba.
- [ ] Cargados los lotes iniciales reales de folios en **Administración → Folios** (Particular, Doble Cero, Intensivo y Rechazo según corresponda).

---

## 5. Estaciones cliente en piso (X3)

Repetir en cada estación (Captura, Prueba, Impresión Central y Supervisión):

- [ ] Copiado **únicamente** `certs/ca/ca.crt` (nunca `ca.key`) al equipo cliente.
- [ ] Instalada la CA comparando la huella anotada en el bloque 2:
  - **Windows (PowerShell como Administrador):**
    ```powershell
    .\scripts\instalar_ca.ps1 -CaCert .\ca.crt -HuellaEsperada "<SHA-256>"
    ```
    Reiniciar Chrome o Edge tras la instalación.
  - **Linux:**
    ```bash
    sudo scripts/instalar_ca.sh --ca ./ca.crt --huella "<SHA-256>"
    scripts/instalar_ca.sh --nss --ca ./ca.crt --huella "<SHA-256>"
    ```
- [ ] Abierto `https://<IP_O_HOST>/?estacion=<DEVICE_IDENTIFIER>` una sola vez (p. ej. `CAPTURA-REFORMA-L1`, `PRUEBA-REFORMA-L1`, `IMPRESION-REFORMA-01`) para fijar la estación en el navegador.
- [ ] Comprobado candado HTTPS sin advertencias, detección en verde (*Configurada*) y hora correcta en la barra superior (`TopAppBar`).

---

## 6. Impresoras y papelería oficial (B9 / Q9)

- [ ] Conectada y probada la impresora dedicada para papel valorado oficial y la impresora auxiliar de papel bond blanco (`HU-074`).
- [ ] Verificada sobre papel real la alineación de coordenadas; si hay desfase milimétrico, ajustar `certificado_offset_x_mm` y `certificado_offset_y_mm` en **Administración → Parámetros**.
- [ ] Confirmado el uso correcto de las plantillas físicas vigentes para aprobados y rechazos antes de iniciar atención ciudadana.

---

## 7. Respaldos diarios (D4) y preparación de actualizaciones (D10)

- [ ] Ejecutado un primer respaldo manual (`scripts/respaldo.sh /var/respaldos/verificacion`) y verificada su restauración de prueba en `verificacion_prueba` (manual sección `7.2`).
- [ ] Programado `cron` diario a las 02:00:
  ```cron
  0 2 * * * cd /opt/verificacion-oaxaca && scripts/respaldo.sh /var/respaldos/verificacion
  ```
- [ ] Configurada copia periódica de `/var/respaldos/verificacion` **fuera del servidor** (NAS, disco externo o almacenamiento remoto).
- [ ] Antes de la primera actualización entre versiones en producción, ensayar el procedimiento completo `D10` (manual sección `8`) sobre una copia de un respaldo real.

> **Regla de seguridad en producción:** nunca ejecutar `python -m app.seed`, `scripts/smoke_e2e_flujo.mjs`, `scripts/smoke_e2e_ui.mjs` ni `scripts/smoke_carga_concurrencia.mjs` contra el servidor en vivo (crean expedientes de prueba y consumen folios reales).
