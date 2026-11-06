# Auditoría de seguridad y propuesta de mitigación (X1 a X7)

**Fecha:** 2026-11-04
**Base:** commit `f492a6f` (rama `frontend-impresion-central`)
**Estado:** propuesta. No se modificó código, configuración ni `docs/PENDIENTES_2026-10-20.md`.
**Alcance:** los siete puntos de la sección 3.3 de `PENDIENTES` (X1 a X7) y los hallazgos relacionados que surgieron al revisarlos.

---

## 1. Resumen ejecutivo

La sección 3.3 de `PENDIENTES` se escribió el 2026-10-20, antes de que se implementaran X1, X2 y X6. Su texto ya no describe el estado real. La auditoría contra el código actual da este panorama:

| Punto | Lo que dice `PENDIENTES` | Estado verificado hoy | Brechas pendientes |
|---|---|---|---|
| X1 Intentos de login | Sin límite ni bloqueo | **Implementado** (429 tras 5 fallos, 15 min, `Retry-After`, reinicio tras éxito) | 5 |
| X2 Caducidad de sesión | No caduca | **Implementado** (30 min de inactividad) | 6 |
| X3 TLS | Sin TLS | **Implementado el 2026-11-04 y validado con `nginx -t` en Docker el 2026-11-05**; faltan probarlo con un navegador y la CA en las estaciones | 2 (resueltas en configuración) |
| X4 CORS | Sin CORS | **Correcto por diseño** (mismo origen vía nginx) | 4 (endurecimiento) |
| X5 Credenciales y puertos | Credenciales por defecto y puertos abiertos | **Producción bien** (BD y Redis no se publican); desarrollo y ejemplos con huecos | 6 |
| X6 Política de contraseñas | Sin política | **Implementada** (bcrypt, composición, lista de comunes) | 4 (la lista de comunes es muy corta) |
| X7 Cobertura 403 | Revisión pendiente | **Autenticación completa** (71 de 74 rutas con guarda; las otras 3 son públicas a propósito); **pruebas de 403 incompletas** | 5 |

### Las cinco prioridades

1. **X3: TLS en el propio compose. Implementado el 2026-11-04 y validado con `nginx -t` en Docker el 2026-11-05** (ver X3); falta probarlo con un navegador. Antes de eso, las contraseñas (cuerpo del login) y el identificador de sesión viajaban en claro por la red del verificentro; era el único hallazgo que clasifiqué como alto.
2. **Rastro de auditoría de las acciones administrativas.** Crear usuarios, restablecer contraseñas, otorgar permisos, cambiar parámetros, registrar folios y editar equipos **no dejan ningún registro** (0 escrituras de bitácora en esos cinco routers).
3. **X1 + X6 juntos:** el bloqueo solo cuenta usuarios que existen y no hay límite por origen; y la política acepta `Password123`, `Oaxaca2026` o `Admin2026`. Combinados, favorecen el *password spraying*.
4. **X5: contraseña de relleno pública y `seed` sin guarda.** `.env.prod.example` trae una contraseña conocida que el compose no obliga a cambiar, y `python -m app.seed` crea un supervisor con contraseña pública sin comprobar el entorno.
5. **X7: una prueba que recorra todas las rutas** y falle si una queda sin guarda, más pruebas de 403 para las rutas que modifican datos (13 de 32 rutas de supervisor no tienen la suya).

### Criterio de severidad

- **Alta:** explotable por alguien con acceso a la red del verificentro y sin credenciales, con impacto en confidencialidad o integridad.
- **Media:** exige condiciones adicionales (un usuario válido, un error de operación) o afecta la disponibilidad o la trazabilidad.
- **Baja:** endurecimiento y defensa en profundidad.

---

## 2. Método y límites

**Qué hice:** lectura estática de `backend/app/**`, `frontend/src/api` y `frontend/src/stores/session.js`, `docker-compose*.yml`, `frontend/nginx.conf`, `backend/Dockerfile.prod`, `.env*.example`, `.gitignore` y `backend/tests/**`. Para X7 hice un barrido automático de las 74 rutas con `ast` (guarda de cada una) y lo crucé con las pruebas. Ejecuté únicamente la función pura `validar_politica_password` para probar ejemplos.

**Qué no hice:**
- No ejecuté la suite de Pytest ni pruebas dinámicas, y esto no es una prueba de penetración.
- No revisé dependencias en busca de vulnerabilidades conocidas (`requirements.txt` no fija versiones).
- El cruce de rutas con pruebas es una **cota inferior**: se le escapan las URLs guardadas en variables o en listas parametrizadas. Por eso verifiqué a mano las rutas que cito como sin prueba.
- Revisé el historial de Git solo en busca de archivos `.env`, `.pem`, `.key`, `.dump` o `.sql` agregados: solo aparecen los dos `.env.example`.

**Supuesto de despliegue:** un servidor local por verificentro, con operadores en la misma red y sin internet garantizado (HU-104). Varias severidades dependen de eso; si el servidor se compartiera entre centros, X7-b sube a alta.

---

## 3. Hallazgos y mitigaciones

### X1. Límite de intentos y bloqueo de login

**Estado actual** (`estaciones.py:148` `_segundos_de_bloqueo`, `:181` `iniciar_sesion`, `config.py:28`): tras `LOGIN_MAX_INTENTOS` (5) fallos de credenciales dentro de `LOGIN_BLOQUEO_MIN` (15) el usuario recibe 429 con `Retry-After`, aunque la contraseña ya sea correcta. Un login correcto reinicia la cuenta. Los intentos se cuentan en `access_events`. Hay pruebas (`test_login_se_bloquea_tras_intentos_fallidos`, `test_login_exitoso_reinicia_la_cuenta_de_fallos`). La contraseña se compara con bcrypt.

| ID | Sev. | Brecha | Evidencia |
|---|---|---|---|
| X1-a | Media | Solo se bloquea a usuarios **existentes**. Los intentos con un usuario inexistente se registran con `user_id = NULL` y nunca disparan nada, y no hay límite por IP ni por estación. Se pueden probar pocas contraseñas comunes contra muchos usuarios (*password spraying*) y adivinar nombres sin freno. | `estaciones.py:197` (solo `if usuario is not None`), `:216` |
| X1-b | Media | El bloqueo se puede usar como arma. Quien conozca un usuario (por ejemplo `supervisor1`) lo bloquea 15 min con 5 peticiones sin autenticarse, y puede repetirlo. Esto afecta también a los supervisores que son quienes destraban. | `estaciones.py:197-205` |
| X1-c | Baja | Se puede deducir qué usuarios existen: solo los reales llegan a recibir 429, y para un usuario inexistente no se ejecuta bcrypt, así que la respuesta es más rápida. | `estaciones.py:197`, `:208` (`usuario is not None and ...`) |
| X1-d | Baja | La comprobación y el registro del fallo no son atómicos. Peticiones simultáneas pasan todas la comprobación con menos de 5 fallos y exceden el límite (cada una paga un bcrypt). | `estaciones.py:197-228` |
| X1-e | Media | La bitácora de accesos no guarda un origen fiable. `ip_address` y `device_fingerprint` los manda el cliente en el cuerpo, el frontend **no los manda nunca** (siempre `NULL`) y el backend no lee `request.client`. Sin IP no se puede limitar por origen ni investigar un incidente. | `estaciones.py:136-142`, `:223`; `grep` en `frontend/src` sin coincidencias |

**Mitigación propuesta**

1. **Primera línea en nginx** (Sebas, con coordinación): limitar `POST /api/estaciones/login` por IP, por ejemplo `limit_req_zone $binary_remote_addr zone=login:10m rate=10r/m;` con `burst=5`. Cubre X1-a y X1-d sin tocar código.
2. **IP real y fiable** (René, backend): nginx envía `X-Real-IP $remote_addr` y sustituye `X-Forwarded-For` por `$remote_addr` (hoy usa `$proxy_add_x_forwarded_for`, que acepta lo que mande el cliente). El backend toma la IP de ahí y la guarda en `access_events`, ignorando el campo del cuerpo. Cubre X1-e.
3. **Bloquear por pareja (usuario, IP)** en lugar de solo por usuario, y añadir un contador por IP para fallos con usuarios inexistentes. Así un atacante en otra máquina ya no bloquea al usuario legítimo (X1-b) y el *spraying* tiene tope (X1-a). Con pocas estaciones por centro es práctico.
4. **Igualar tiempos:** si el usuario no existe, ejecutar `verify_password` contra un hash ficticio fijo. Cubre el canal de tiempo de X1-c.
5. **Serializar por usuario** (`pg_advisory_xact_lock(hash(username))`) alrededor de comprobación y registro, para X1-d.
6. Opcional: pasar de bloqueo fijo a retroceso progresivo (1, 5, 15 minutos).

**Pruebas a agregar:** usuario inexistente con 6 intentos (responde igual y se cuenta); bloqueo por (usuario, IP) sin afectar a otra IP; el límite por IP; que `ip_address` salga de la conexión y no del cuerpo.
**Esfuerzo:** medio (nginx 1 h; backend 1 a 2 días).

---

### X2. Caducidad de sesión por inactividad

**Estado actual** (`deps.py:52-95`): la sesión expira tras `SESION_INACTIVIDAD_MIN` (30) sin peticiones. `updated_at` marca la última actividad y se renueva como máximo una vez por minuto. Al expirar pasa a `expirada`. También se rechaza si el usuario o la estación están inactivos. Hay prueba (`test_sesion_expira_por_inactividad`). El identificador es un UUID4 (122 bits) y en el frontend vive solo en memoria, no en `localStorage`. No encontré que aparezca en las respuestas de supervisión ni en lo que se encola para el central.

| ID | Sev. | Brecha | Evidencia |
|---|---|---|---|
| X2-a | Media | **No hay vencimiento absoluto.** Una sesión con actividad continua nunca expira, y un identificador robado y usado a diario dura indefinidamente. | `deps.py:70-83` |
| X2-b | Media | **Revocar un permiso no corta la sesión abierta.** `get_current_session` no vuelve a validar `user_station_permissions`; solo mira que el usuario y la estación sigan activos. Al borrar o editar un permiso, el acceso se conserva mientras haya actividad. | `deps.py:85-95`; `permisos.py` (DELETE y PATCH no cierran sesiones) |
| X2-c | Baja | Restablecer la contraseña de un usuario **no cierra sus sesiones** (desactivarlo sí). Tras sospechar de un robo, cambiar la contraseña no expulsa al atacante. | `usuarios.py:80` frente a `:88-94` |
| X2-d | Baja | La expiración es perezosa: las filas vencidas siguen como `activa` hasta que llega una petición con ese identificador. Cualquier conteo de sesiones activas sobreestima. | `deps.py:70-83` |
| X2-e | Baja | Falla abierto si el usuario no existe: `usuario is not None and not usuario.is_active` deja pasar una sesión huérfana. `station_sessions.user_id` no tiene clave foránea. | `deps.py:92`; `models/workstation.py:37` |
| X2-f | Baja | El identificador no se rota al iniciar sesión ni al cambiar de privilegios (es el `id` de la fila). Con UUID4 es aceptable; se anota por completitud. | `models/workstation.py:34-51` |

**Mitigación propuesta (René, backend)**

1. **Vencimiento absoluto** configurable `SESION_DURACION_MAX_H` (por ejemplo 12 h, un turno; 0 lo apaga), evaluado en `get_current_session` junto a la inactividad. X2-a.
2. **Cerrar las sesiones del usuario afectado** al borrar o editar un permiso y al restablecer su contraseña, con la misma instrucción `UPDATE station_sessions ... status='cerrada'` que ya usa `actualizar_usuario` al desactivar. X2-b y X2-c. Alternativa más completa: revalidar el permiso en la misma ventana de 60 s que ya existe (`ACTIVIDAD_REFRESCO`).
3. **Barrido periódico** de sesiones vencidas, en el mismo `lifespan` donde corre la sincronización automática. X2-d.
4. **Fallar cerrado** si el usuario no existe (401). Obliga a ajustar las pruebas que crean sesiones con UUID inventados (`crear_sesion_activa`). X2-e.

**Pruebas a agregar:** sesión activa que supera el máximo absoluto; sesión que deja de servir tras `DELETE /api/permisos`; sesiones cerradas tras restablecer contraseña.
**Esfuerzo:** bajo a medio (1 a 2 días).

---

### X3. Tránsito de sesión y TLS en producción

**Estado actual:** `frontend/nginx.conf:2` escucha solo en el puerto 80, `docker-compose.prod.yml` publica `WEB_PORT` por HTTP y el comentario de ese archivo dice que "el TLS se termina delante (proxy inverso del verificentro o balanceador)". Ese proxy no existe en el repositorio ni lo describe el manual: el `README.md` repite que "el compose publica HTTP" y `docs/MANUAL_INSTALACION_Y_OPERACION.md` no trata TLS (solo menciona HTTPS para la sincronización con el central).

| ID | Sev. | Brecha |
|---|---|---|
| X3-a | **Alta** | **Sin TLS en la red del verificentro.** Viajan en claro la contraseña (cuerpo de `POST /api/estaciones/login`) y el `X-Session-Id` de todas las peticiones. Cualquier equipo conectado a esa red puede capturarlos, y con un identificador de sesión robado se opera como ese usuario. |
| X3-b | Baja | Sin HSTS ni redirección 80 a 443, porque no hay 443. |

**Mitigación propuesta**

Terminar TLS en el **mismo nginx** del compose, para que el despliegue no dependa de un proxy ajeno. Dos escenarios, según dónde corra:

- **Servidor local en el verificentro** (offline, el caso base): certificado emitido por una **CA interna** del proyecto o autofirmado, con la CA instalada en las estaciones. No requiere internet ni dominio.
- **VPS con dominio** (la opción que ahora plantea el hosting del cliente): certificado público (por ejemplo Let's Encrypt), con renovación automática.

Esquema de `nginx.conf` (ilustrativo, no probado):

```nginx
server { listen 80; server_name _; return 301 https://$host$request_uri; }

server {
    listen 443 ssl;
    http2 on;
    server_name _;
    ssl_certificate     /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    # HSTS solo cuando el certificado sea de confianza para las estaciones:
    # add_header Strict-Transport-Security "max-age=31536000" always;
    ...
}
```

En el compose: publicar `443` además de `80`, montar los certificados como volumen de solo lectura y documentar la generación y distribución de la CA en el manual (D6). El certificado y la llave no se versionan (añadir `certs/` a `.gitignore`).

**Pruebas a agregar:** verificación manual con `curl -k` y `openssl s_client`; un chequeo en el script de humo de que `http://` redirige a `https://`.
**Esfuerzo:** medio (1 a 2 días, más la decisión de qué certificado usar). **Dueño:** Sebas (nginx, compose y manual), con visto bueno de René.

**Estado de aplicación (2026-11-04):** implementado según lo propuesto para la red local, con las decisiones tomadas:
- `scripts/generar_certificados.sh`: CA local propia y certificado de servidor firmado por ella (ECDSA P-256, nombres alternativos obligatorios, 825 días). La llave de la CA queda en una carpeta aparte (`certs/ca/`) para que **nunca se monte en el contenedor**; solo `certs/server/` llega a nginx.
- `frontend/nginx.conf`: puerto 443 con TLS 1.2 y 1.3, y puerto 80 que solo redirige (y deja pasar el desafío ACME para el VPS). HSTS queda **comentado a propósito** hasta que la renovación de certificados sea rutina, porque con una CA propia un certificado vencido dejaría a las estaciones sin poder saltar el aviso.
- `docker-compose.prod.yml`: publica 443 y monta los certificados en solo lectura con `create_host_path: false`, de modo que `up` falla con un error claro si faltan en lugar de dejar a nginx reiniciándose.
- Manual (sección 3.3): generación, instalación de la CA en Windows, Firefox y Linux, renovación y problemas frecuentes. El manual traía además una verificación errónea (`/api/health` no existe) que se corrigió.

**Cómo se verificó:** el generador, en Windows (OpenSSL 3.2) y en Linux (WSL2, OpenSSL 3.0); y un **handshake TLS real** con un servidor y clientes de prueba: conecta con TLS 1.3 con la CA instalada, rechaza un nombre que no está en el certificado, desconfía si la estación no tiene la CA y rechaza TLS 1.1. El compose se validó con `docker compose config`. La configuración de nginx y los certificados montados fueron **validados con `nginx -t` en Docker (`nginx:1.27-alpine`) el 2026-11-05**, resultando exitoso (`syntax is ok / test is successful`).

**Cambio de comportamiento a tener presente:** `docker compose up` ya no arranca sin certificados. Quien despliegue debe ejecutar antes `scripts/generar_certificados.sh`.

**Pendiente de X3:** probar con un navegador real, instalar la CA en las estaciones cliente, el procedimiento con Let's Encrypt en el VPS (sin probar; falta montar `/var/www/certbot` si se usa `--webroot`) y decidir cuándo activar HSTS.

---

### X4. CORS y proxy inverso

**Estado actual:** no hay `CORSMiddleware`. El frontend y la API comparten origen a través de nginx (`location /api/`), por lo que **no hace falta CORS y no tenerlo es lo correcto**: una política abierta sería peor. En producción el backend no publica puertos (`docker-compose.prod.yml` no declara `ports` en `backend`). `/docs` y `/openapi.json` no pasan por nginx, que solo enruta `/api/`.

| ID | Sev. | Brecha | Evidencia |
|---|---|---|---|
| X4-a | Media | **Sin cabeceras de seguridad** en nginx: ni `Content-Security-Policy`, ni `X-Content-Type-Options`, ni `X-Frame-Options` o `frame-ancestors` (la interfaz se puede incrustar en otro sitio), ni `Referrer-Policy`. | `frontend/nginx.conf` completo |
| X4-b | Baja | `X-Forwarded-For` usa `$proxy_add_x_forwarded_for`, que conserva el valor que mande el cliente (ver X1-e). | `nginx.conf:11` |
| X4-c | Baja | Sin `server_tokens off`: se publica la versión de nginx. | `nginx.conf` |
| X4-d | Baja | En desarrollo `docker-compose.yml` publica el backend en `8000`, y ahí `/docs` queda abierto. Si alguien reutilizara ese compose en producción, la documentación interactiva sería accesible sin autenticar. | `docker-compose.yml:28` |

**Mitigación propuesta**

1. **Mantener sin CORS** en producción. Si algún día el frontend se sirviera desde otro origen, usar una lista blanca explícita y nunca `*` junto con credenciales. Dejarlo escrito en `PENDIENTES` para que nadie lo "arregle" abriendo CORS.
2. **Cabeceras de seguridad en nginx** (X4-a), `server_tokens off` (X4-c) y `X-Real-IP` más `X-Forwarded-For $remote_addr` (X4-b), ilustrativo:

```nginx
server_tokens off;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "no-referrer" always;
add_header Content-Security-Policy "default-src 'self'; frame-ancestors 'none'" always;
```

   Dos advertencias de nginx: `add_header` dentro de un `location` **reemplaza** el de nivel superior (el `location /assets/` ya usa `add_header`, por lo que hay que repetirlas ahí), y la CSP debe probarse con la interfaz de Vuetify antes de activarse (puede pedir `style-src 'unsafe-inline'`).
3. **Apagar `/docs`, `/redoc` y `/openapi.json` en producción** mediante una variable de entorno (por ejemplo `APP_ENV=production` que fije `docs_url=None`). Cubre X4-d (René).

**Esfuerzo:** bajo (medio día).

---

### X5. Credenciales por defecto y aislamiento de puertos

**Estado actual:** en **producción** el compose no publica Postgres ni Redis (solo la red interna), las credenciales vienen de variables y `.env.prod` está ignorado por Git. Se confirmó que solo los dos `.env.example` se han versionado alguna vez. El backend corre como usuario no root (`Dockerfile.prod`). En **desarrollo** `docker-compose.yml` usa `verificacion/verificacion` y publica Postgres en `5433` y Redis en `6379` en todas las interfaces.

| ID | Sev. | Brecha | Evidencia |
|---|---|---|---|
| X5-a | Media | `.env.prod.example` trae una contraseña de relleno **pública** (`CAMBIAR_contraseña_larga_y_unica`) y el compose no obliga a cambiarla: usa `${POSTGRES_PASSWORD}` sin comprobar. Un despliegue que copie el ejemplo sin editarlo queda con una contraseña conocida. | `.env.prod.example:3`; `docker-compose.prod.yml:20` |
| X5-b | Media | **`python -m app.seed` no comprueba el entorno** y crea `operador1/operador1` y `supervisor1/supervisor1` (este último con permiso de supervisor). Ejecutarlo en producción por error dejaría un supervisor con contraseña pública. La política X6 las rechazaría por la API, pero el seed las inserta directo. | `seed.py:26`, `:32` |
| X5-c | Media | **`.gitignore` no cubre `backups/` ni `*.dump`.** Los scripts de PowerShell escriben por defecto en `.\backups`, y esos archivos contienen propietario, domicilio y placas. Solo `respaldos/` (de los scripts de René) está ignorado; se comprobó con `git check-ignore`. | `.gitignore`; `scripts/README.md` |
| X5-d | Baja | En desarrollo, Redis sin contraseña y Postgres publicados a toda la red local. | `docker-compose.yml:9`, `:21` |
| X5-e | Baja | La aplicación se conecta con el mismo usuario con el que se crea la base (superusuario del contenedor). Por mínimo privilegio debería usar un rol sin `SUPERUSER` ni `CREATEDB`. | `docker-compose.prod.yml:18-21`, `:42-43` |
| X5-f | Baja | `config.py` trae por defecto `verificacion:verificacion@localhost`. En producción fallaría por no alcanzar la base, pero conviene que la variable sea obligatoria. | `core/config.py:7-8` |

**Mitigación propuesta**

1. **Exigir los secretos en el compose** (X5-a): `${POSTGRES_PASSWORD:?definir en .env.prod}`, y que el backend rechace el arranque si `APP_ENV=production` y la contraseña contiene `CAMBIAR` o es `verificacion`. Cambiar el ejemplo por un marcador que no sea una contraseña válida.
2. **Guarda de entorno en `seed.py`** (X5-b): negarse a correr con `APP_ENV=production`, o exigir `--forzar` explícito. René.
3. **`.gitignore`:** agregar `backups/`, `*.dump`, `*.sql.gz`, `certs/` (X5-c). Es un cambio de una línea y evita el incidente más caro de este grupo. Sebas.
4. Bajar el riesgo en desarrollo (X5-d): publicar `127.0.0.1:5433:5432` y `127.0.0.1:6379:6379`.
5. Rol de aplicación con privilegios mínimos (X5-e), creado por `bootstrap_prod`. René.

**Esfuerzo:** bajo (medio día), salvo el rol de BD (medio día más).

---

### X6. Política de contraseñas

**Estado actual** (`services/auth.py`, `schemas/usuario.py`): bcrypt con el costo por defecto de la librería (12 rondas). Largo de 8 a 100 caracteres y máximo 72 bytes (límite de bcrypt), al menos una letra y un número, no igual al usuario, al menos 4 caracteres distintos y una lista de **16** contraseñas comunes. Se aplica al crear y al restablecer. Hay pruebas, incluida la de más de 72 bytes (422 y no 500). No hay caducidad ni cambio forzado.

Resultado de probar la función de validación:

| Contraseña | Resultado |
|---|---|
| `Password123`, `Oaxaca2026`, `Abcd1234`, `Verificentro1`, `12345678a`, `Operador2026`, `Admin2026` | **Aceptadas** |
| `Qwerty123`, `Verificacion1`, `aaaa1111` | Rechazadas |

| ID | Sev. | Brecha |
|---|---|---|
| X6-a | Media | La lista de comunes es demasiado corta y solo coincide con la cadena completa en minúsculas. Contraseñas triviales y previsibles (nombre del estado más año, usuario más número) pasan. Junto con X1-a hace viable el *spraying*. |
| X6-b | Media | **El supervisor fija la contraseña de otros y por tanto la conoce.** No existe un endpoint para que el propio usuario la cambie ni un indicador de "cambiar al primer inicio". |
| X6-c | Baja | Los usuarios distinguen mayúsculas (`Admin` y `admin` son cuentas distintas): riesgo de cuentas con nombre parecido. |
| X6-d | Baja | No hay re-hash cuando se sube el costo de bcrypt ni historial de contraseñas. |

**Mitigación propuesta (René, backend)**

1. **Ampliar la lista de comunes** (X6-a) con un diccionario de unas miles de entradas empaquetado en el repositorio, y rechazar también contraseñas que **contengan** el usuario, el nombre del centro, "oaxaca" o "verificacion". Es la medida de mayor efecto: la guía NIST SP 800-63B prefiere comparar con listas de contraseñas conocidas antes que imponer reglas de composición.
2. **`POST /api/usuarios/me/password`** que exija la contraseña actual (X6-b), y una columna `must_change_password` que se active al crear o restablecer, para que el supervisor deje de conocer la contraseña definitiva.
3. **No imponer caducidad periódica** (la misma guía la desaconseja salvo sospecha de compromiso). Sí cambiar al restablecer y cerrar sesiones (X2-c).
4. Normalizar el usuario a minúsculas y garantizar unicidad sin distinguir mayúsculas (X6-c).

**Pruebas a agregar:** casos de la tabla (deben rechazarse), contraseña que contiene el usuario, cambio propio con y sin contraseña actual correcta, `must_change_password`.
**Esfuerzo:** medio (2 a 3 días).

---

### X7. Cobertura de permisos y respuestas 403

**Mapa de rutas** (barrido automático, 74 rutas):

| Guarda | Rutas |
|---|---|
| `requiere_supervisor` | 32 |
| `requiere_estacion(PRUEBA)` | 15 |
| `requiere_estacion(IMPRESION)` | 9 |
| Solo sesión (`get_current_session`) | 8 (`catalogos` ×3, `logout`, `GET /expedientes`, `GET /expedientes/{id}`, `sync/estado`, `sync/expediente/{id}`) |
| `requiere_estacion(CAPTURA)` | 5 |
| `requiere_estacion(CAPTURA, PRUEBA)` | 2 |
| **Sin guarda** | **3: `POST /api/estaciones/login`, `GET /api/estaciones/{device_identifier}`, `GET /health`** (públicas a propósito) |

**Lo que está bien:** ninguna ruta de negocio queda sin autenticar. Los listados y el detalle de expedientes acotan por centro y línea **de la sesión**, no por lo que mande el cliente (`expedientes.py`: si se pide otro centro o línea responde 403, y si se omiten se acota por defecto). Las rutas de `supervision` filtran por `session.center_id` y `auditoria` limita la página a 500.

| ID | Sev. | Brecha | Evidencia |
|---|---|---|---|
| X7-a | Media | **Pruebas de 403 incompletas.** Hay una por router, casi siempre del `GET` de listado, pero no para las rutas que **modifican** datos. De las 32 rutas de supervisor, 13 no tienen la suya: `usuarios` PATCH, `permisos` POST, PATCH y DELETE, `parametros` PATCH, `estaciones` PATCH, `equipos` GET tipos, POST y PATCH, `folios/inventario`, `pruebas/limites-emision` GET, prórroga de semestre y bitácora (solo prueba de otro centro). De estación faltan, entre otras, `obd/solicitar` y `obd/resultado`, `pruebas/cola`, `configuracion`, `interrumpir` y `reintentar`, `siox/captura-manual`, `inspeccion/checklist` y `impresion/resultados` e `imprimir-resultados`. (`pruebas/equipo/*` tienen una prueba de 403 por línea ajena, pero no por tipo de estación.) No es una vulnerabilidad hoy: todas usan la misma dependencia. Es riesgo de regresión silenciosa. | Lectura de `backend/tests/**` |
| X7-b | Baja | **Alcance por centro incompleto en rutas de supervisor.** `usuarios`, `permisos`, `parametros`, `equipos`, `folios` y `límites` son globales, y `POST /api/permisos` acepta cualquier `center_id` y `can_supervise=true`. Un supervisor del centro A podría otorgar permisos o restablecer contraseñas que afectan al centro B. Confirmado el 2026-11-04: **un servidor por verificentro**, por lo que el riesgo es bajo; solo sería alto si el servidor se compartiera. | `permisos.py:36-63`; `usuarios.py` |
| X7-c | Media | **Las acciones administrativas no dejan rastro.** `usuarios`, `permisos`, `parametros`, `equipos` y `folios` tienen 0 escrituras en `EventLog` o `AccessEvent`. No queda registrado quién creó un usuario, restableció una contraseña, otorgó un permiso de supervisor, cambió un parámetro (por ejemplo `certificado_rechazo_dias_vigencia`) o registró un lote de folios. | `grep` en los cinco routers |
| X7-d | Baja | `GET /api/estaciones/{device_identifier}` es público y devuelve todo `WorkstationRead` (incluye `capacidad_dinamometro_kg`, `is_centralized`, `allowed_line_ids` y el `id` que el login necesita). Los identificadores son predecibles (`CAPTURA-REFORMA-L1`). | `estaciones.py:119`; `schemas/estacion.py:9-21` |
| X7-e | Baja | `POST /api/permisos` acepta un `user_id` que no existe: la tabla no tiene clave foránea hacia `cat_usuarios`. | `models/workstation.py:56`; `permisos.py:36` |

**Mitigación propuesta**

1. **Prueba que recorra todas las rutas** (X7-a), la medida estructural más rentable. Itera `app.routes`, llama a cada una sin `X-Session-Id` y exige 401, salvo una lista blanca explícita de las 3 públicas. Falla en cuanto alguien agregue una ruta sin guarda. Una segunda prueba arma una sesión de la estación equivocada y exige 403 para cada ruta con `requiere_estacion`, y otra con una sesión sin permiso de supervisor para cada ruta de supervisor. Esquema ilustrativo:

```python
PUBLICAS = {("POST", "/api/estaciones/login"),
            ("GET", "/api/estaciones/{device_identifier}"),
            ("GET", "/health")}

@pytest.mark.parametrize("metodo,ruta", rutas_de_la_app(excluir=PUBLICAS))
async def test_toda_ruta_exige_sesion(client, metodo, ruta):
    resp = await client.request(metodo, ruta_con_ids_falsos(ruta))
    assert resp.status_code == 401
```

2. **Denegar por defecto:** poner la dependencia de sesión a nivel de `include_router` para todos los routers salvo `estaciones` (y exentar ahí el login), de modo que una ruta nueva nazca protegida aunque se olvide la guarda.
3. **Auditoría administrativa** (X7-c): registrar en `EventLog` (o una tabla `audit_admin`) quién, cuándo y qué cambió en `usuarios` (alta, restablecer contraseña, activar y desactivar), `permisos` (alta, cambio, baja), `parametros`, `equipos` y `folios/lotes`. Sin guardar contraseñas ni valores secretos, solo el hecho y los campos afectados. Hoy esas acciones no están en la bitácora de auditoría que ve el supervisor.
4. **Decidir el alcance por centro** (X7-b): confirmar que cada servidor atiende un solo centro y, si es así, anotarlo como supuesto y validar `center_id` del permiso contra el de la sesión del supervisor. Si no, acotar `usuarios`, `permisos` y `parametros` por centro.
5. **Reducir lo que devuelve la detección de estación** (X7-d): solo `id`, `name`, `station_type`, `center_id`, `line_id` y `allowed_line_ids`, y limitarla por IP en nginx (X1).
6. **Validar que el usuario exista** al otorgar un permiso (X7-e), y valorar la clave foránea con migración.

**Esfuerzo:** medio (2 a 4 días; la prueba de recorrido de rutas, medio día).

---

## 4. Plan priorizado

| Fase | Contenido | Dueño | Esfuerzo |
|---|---|---|---|
| **A. Inmediata** (1 a 2 días, bajo riesgo). **Ops aplicado el 2026-11-04, ver sección 7** | `.gitignore` (`backups/`, `*.dump`, `*.sql.gz`, `certs/`); `${POSTGRES_PASSWORD:?}` y marcador en el ejemplo; nginx con cabeceras, `server_tokens off`, `limit_req` al login y `X-Real-IP`; desarrollo con puertos en `127.0.0.1`; ampliar la lista de contraseñas comunes; guarda de entorno en `seed.py`; apagar `/docs` en producción | Sebas (gitignore, compose, nginx, manual); René (backend) | Bajo |
| **B. Corta** (3 a 5 días). **TLS en nginx: aplicado el 2026-11-04 (ver X3)** | IP real y bloqueo por (usuario, IP); vencimiento absoluto; cerrar sesiones al cambiar permisos o restablecer contraseña; auditoría administrativa; pruebas de recorrido de rutas y de 403 de las rutas que modifican datos; reducir `WorkstationRead` público | René (backend) y Sebas (pruebas, nginx y documentación) | Medio |
| **C. Con decisión previa** | Cambio de contraseña por el propio usuario y `must_change_password`; alcance por centro; rol de BD de mínimo privilegio; barrido de sesiones vencidas; normalizar usuarios a minúsculas | René, tras decidir el modelo de despliegue | Medio |

Archivos que son de René (`backend/**`) los listo como propuesta para que él decida y los implemente. De mi lado (Sebas) quedan `.gitignore`, `docker-compose*.yml`, `frontend/nginx.conf`, `scripts/`, `docs/` y las pruebas de `frontend/tests/`.

---

## 5. Decisiones tomadas (2026-11-04)

| Tema | Decisión | Consecuencia para la implementación |
|---|---|---|
| Alcance de cada servidor | **Un servidor local autónomo por verificentro**, con Postgres y Redis locales (operación sin internet, B4) que sincroniza al central por `sync_outbox`. | X7-b baja a severidad baja. Se mantiene la recomendación de validar el `center_id` de los permisos contra el de la sesión. |
| Certificado TLS | **Red local del verificentro:** certificado interno o autofirmado, o CA local, en nginx. **VPS en la nube:** certificado público (Let's Encrypt) con el dominio oficial. | Hay que preparar los dos escenarios en nginx y documentar cómo se genera e instala la CA en las estaciones (D6). |
| Desbloqueo de usuarios | Un **operador** bloqueado lo destraba el **supervisor del centro**, o se destraba solo a los 15 min. Un **supervisor** bloqueado se destraba con **soporte o un script técnico**. | El **script de soporte ya existe** (`scripts/desbloquear_usuario.sh` y `.ps1`, 2026-11-04), pensado sobre todo para un supervisor bloqueado. **Sigue sin existir la vía por API** para que el supervisor destrabe a un operador: falta `POST /api/usuarios/{id}/desbloquear` (backend), que además debería dejar un evento explícito en lugar de anotar el motivo de los intentos. |
| Auditoría administrativa | En la tabla **`EventLog`** (`modulo="administracion"`, `evento="usuario_creado"`, etc.), para mantener una sola bitácora transaccional. | **No se puede hacer sin cambios en el backend:** `EventLog.verificacion_id` es obligatorio y clave foránea (`nullable=False`), y tres sitios asumen un expediente: el serializador de sincronización (`_serializar_event_log` hace `str(event.verificacion_id)` y enviaría `"None"` al central), la consulta de auditoría de supervisión (une con `Verificacion`, así que **descartaría en silencio** los eventos sin expediente) y el filtro por centro. Requiere: migración para `verificacion_id` nullable, ajustar el serializador, usar `LEFT JOIN` en la auditoría y guardar el centro en el evento (columna o `detalle_json`) para poder acotarlo. Es trabajo de René. |
| ¿Se acepta que el supervisor conozca las contraseñas iniciales? | **Sin responder.** | Mientras no se decida, `must_change_password` (X6-b) sigue siendo recomendable. |

## 6. Texto sugerido para actualizar la sección 3.3 de `PENDIENTES`

No lo apliqué; queda como propuesta:

| # | Estado propuesto |
|---|---|
| X1 | ~~Sin límite de intentos~~ **RESUELTO 2026-10-21** (commit `4db2ed0`: 429 tras 5 fallos, 15 min). **Quedan** brechas de endurecimiento: IP real y límite por origen (ver `AUDITORIA_SEGURIDAD_X1_X7.md`) |
| X2 | ~~La sesión no caduca~~ **RESUELTO 2026-10-21** (commit `4db2ed0`: 30 min de inactividad). **Quedan** vencimiento absoluto y cierre de sesión al revocar permisos |
| X3 | ~~Sin TLS~~ **IMPLEMENTADO 2026-11-04 / VALIDADO CON DOCKER 2026-11-05:** nginx termina TLS en el 443 y el 80 redirige; certificados con `scripts/generar_certificados.sh`; sintaxis y carga de certificados verificada con `nginx -t` en Docker exitosamente |
| X4 | ~~Sin CORS~~ **RESUELTO por diseño** (mismo origen vía nginx; no agregar CORS). **Quedan** cabeceras de seguridad en nginx |
| X5 | **Parcial:** producción no publica BD ni Redis; faltan exigir los secretos, guarda del `seed` e ignorar `backups/` |
| X6 | ~~Sin política de contraseñas~~ **RESUELTO 2026-10-21** (commit `f96eb1c`: bcrypt, composición). **Quedan** ampliar la lista de comunes y el cambio por el propio usuario |
| X7 | **Parcial:** autenticación completa en las 74 rutas; faltan pruebas de 403 en rutas que modifican datos, auditoría administrativa y decidir el alcance por centro |

---

## 7. Estado de la Fase A (aplicada el 2026-11-04 en archivos de ops)

Se aplicó solo lo que cae en archivos de ops y documentación. Lo de `backend/**` sigue como propuesta para René.

| Medida | Cambio | Cómo se verificó |
|---|---|---|
| X5-c | `.gitignore`: `backups/`, `*.dump`, `*.sql.gz`, `certs/` | `git check-ignore` |
| X5-a | `docker-compose.prod.yml` exige `POSTGRES_PASSWORD` (`${POSTGRES_PASSWORD:?...}`); `.env.prod.example` ya no trae contraseña de relleno; el manual y el `README.md` lo indican (el manual traía otra contraseña de ejemplo) | `docker compose config` sin la variable, con ella vacía y con ella definida: falla con un mensaje claro en los dos primeros casos y funciona en el tercero |
| X1 (primera línea), X1-e, X4-b | `frontend/nginx.conf`: `limit_req` de 30 peticiones por minuto por IP (ráfaga de 10) en `POST /api/estaciones/login`, con respuesta 429 en JSON con `detail`; `X-Real-IP` y `X-Forwarded-For $remote_addr` en lugar de aceptar el del cliente | Revisión estructural y **validado con `nginx -t` en Docker (`nginx:1.27-alpine`) el 2026-11-05**. |
| X4-a, X4-c | `frontend/security-headers.conf` (`nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy`, `Permissions-Policy`) incluido en el server y en cada `location` con `add_header`; `server_tokens off` | Igual que la fila anterior |
| X4-a (CSP) | La `Content-Security-Policy` se publica en **modo solo reporte** (`...-Report-Only`) | No bloquea nada; se probó el contenido del frontend compilado (sin scripts en línea ni recursos externos), pero no en un navegador |

**Pendiente de comprobar antes de desplegar (con Docker encendido):**

1. `docker run --rm -v "<ruta>/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" -v "<ruta>/frontend/security-headers.conf:/etc/nginx/snippets/security-headers.conf:ro" nginx:1.27-alpine nginx -t`. El `upstream` `backend` no resuelve fuera de Compose; en ese caso, validar con el compose levantado: `docker compose ... exec web nginx -t`.
2. Abrir el sistema en un navegador y revisar la consola: login, las cinco vistas y la **vista previa del certificado** (abre un PDF como `blob:`). Si no hay avisos de CSP, cambiar `Content-Security-Policy-Report-Only` por `Content-Security-Policy`.
3. Comprobar que el 429 del login se ve como un mensaje legible y no como un error de permisos.
4. Si todas las estaciones de un centro salen por una misma IP (NAT o proxy), el límite de 30 por minuto se compartirá entre ellas; subir `rate` y `burst` si se nota al iniciar turno.

**Sin aplicar de la Fase A:** puertos de desarrollo en `127.0.0.1` (X5-d), guarda de entorno del `seed`, ampliar la lista de comunes y apagar `/docs` en producción (backend).

---

## Anexo A. Rutas sin prueba de 403 (verificadas a mano)

**Supervisor (13):** `PATCH /api/usuarios/{id}`; `POST`, `PATCH` y `DELETE /api/permisos`; `PATCH /api/parametros/{clave}`; `PATCH /api/estaciones/{id}`; `GET /api/equipos/tipos`, `POST /api/equipos`, `PATCH /api/equipos/{id}`; `GET /api/folios/inventario`; `GET /api/pruebas/limites-emision`; `POST /api/supervision/semestre/prorroga`; `GET /api/supervision/expedientes/{id}/bitacora` (solo prueba de otro centro).

**Estación:** `POST /api/obd/solicitar/{id}` y `/resultado/{id}`; `GET /api/pruebas/cola`; `GET /api/pruebas/configuracion/{id}`; `POST /api/pruebas/interrumpir/{id}` y `/reintentar/{id}`; `POST /api/siox/captura-manual/{id}`; `GET /api/inspeccion/checklist`; `GET /api/impresion/resultados/{id}` y `POST /api/impresion/imprimir-resultados/{id}`.

Las pruebas parametrizadas de `test_impresion.py` ya cubren `vista-previa`, `marcar-danado` y `cerrar`. Las rutas `pruebas/equipo/estado`, `equipo/iniciar` y `equipo/corrida` tienen una prueba de 403 por línea ajena (`test_iniciar_lectura_exige_prueba_en_proceso_y_linea_propia`), pero no por tipo de estación; se omiten de esta lista.

## Anexo B. Pruebas de seguridad que ya existen

Bloqueo y reinicio de login (`test_login.py`), expiración por inactividad (`test_estaciones.py`), política de contraseñas, más de 72 bytes y restablecimiento (`test_usuarios.py`), `401` sin sesión y con identificador que no es UUID (`test_colas_y_lineas.py`), restricción de estación (`test_estacion_guard.py` y las de cada router), alcance por línea y por centro (`test_colas_y_lineas.py`, `test_reasignacion_linea.py`, `test_supervision.py`).
