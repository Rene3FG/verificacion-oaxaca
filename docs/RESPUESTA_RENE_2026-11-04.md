# Respuesta de René a los pendientes del 2026-11-04

Respuesta al reporte de Sebas del 4 de noviembre (sección "Coordinación con René") y a la parte de backend de `docs/AUDITORIA_SEGURIDAD_X1_X7.md`.

**Verificación:** backend 519/519 en Pytest (antes 473; +46 pruebas nuevas). Frontend 401/401 en Vitest (antes 397; +4). Build de Vite limpio (694 módulos). Las dos migraciones nuevas suben y bajan sin error.

---

## 1. Resuelto

### Campo 001: `clave_tecnico` en `cat_usuarios`

- Migración `c8d2e6f1a3b7`: columna `clave_tecnico` `VARCHAR(20)`, opcional y única (varios usuarios sin clave están permitidos).
- API de usuarios: se captura en el alta y la edición. Se normaliza a mayúsculas sin espacios. Solo admite letras, números y guiones. Una clave repetida responde 409. En `PATCH`, `null` o `""` la quita y omitir el campo la deja igual.
- `AdministracionPanel.vue`: campo "Clave de técnico (opcional)" en el diálogo y columna en la tabla. Solo se envía si cambió.
- Pruebas: `backend/tests/test_clave_tecnico.py` (6) y 3 nuevas en `frontend/tests/AdministracionPanel.test.js`. Se ajustaron 2 pruebas que comparaban la forma exacta del formulario.

**Lo que NO se hizo a propósito:** imprimir la clave en el certificado (pasos 3 a 5 de la sección 5 de la propuesta NOM-047). Depende de dos preguntas abiertas para el cliente: si el ID del técnico es una clave nueva o su usuario, y qué técnico va cuando la inspección visual y la prueba las hacen personas distintas. También falta decidir la opción (a) respaldo con el parámetro o (b) 409. Hoy el certificado sigue imprimiendo `certificado_numero_equipo`.

### X7-c: auditoría de acciones administrativas

- Migración `d9e3f7a2b4c8`:
  - `event_log.verificacion_id` pasa a nullable.
  - Se agrega `event_log.centro_id`, con backfill desde el expediente.
  - Un CHECK (`ck_event_log_expediente_o_admin`) solo permite eventos sin expediente cuando `modulo = 'administracion'`. Un evento operativo huérfano sigue siendo imposible.
  - Índice `(centro_id, created_at)`.
- `app/services/auditoria_admin.py`: un solo punto de escritura (`registrar_evento_admin`). Nunca guarda contraseñas ni hashes y va en la misma transacción que el cambio, así que si el cambio falla el evento tampoco queda.
- Eventos registrados:

  | Router | Eventos |
  |---|---|
  | Usuarios | `usuario_creado`, `usuario_editado` (con la lista de campos), `usuario_password_restablecida`, `usuario_activado`, `usuario_desactivado` |
  | Permisos | `permiso_otorgado`, `permiso_modificado` (antes y después; no se registra si no hubo cambio real), `permiso_revocado` |
  | Parámetros | `parametro_modificado` (antes y después) |
  | Equipos | `equipo_registrado`, `equipo_modificado` |
  | Folios | `lote_folios_registrado` |

- Los tres puntos que señalaste en la sección 7 de la auditoría quedaron cubiertos:
  1. **Serializador de sync:** manda `null`, no `"None"`, e incluye `centro_id`.
  2. **`GET /api/supervision/auditoria`:** usa `LEFT JOIN` al expediente. El centro se toma con `COALESCE(expediente.centro_id, evento.centro_id)`.
  3. **`AuditoriaRead`:** `verificacion_id` y `placa` ahora son opcionales.
- Los eventos administrativos **no** se encolan a `sync_outbox`. Es consistente con la decisión de agosto: usuarios, permisos y parámetros se administran solo con conexión.
- `SupervisorView.vue`: `"administracion"` se agregó al filtro de módulo, y la placa vacía se muestra como "—".
- Pruebas: `backend/tests/test_auditoria_admin.py` (12) y 1 nueva en `frontend/tests/SupervisorView.test.js`.

### Endurecimiento de backend (auditoría X1 a X6)

| ID | Cambio |
|---|---|
| X1-a | Tope de fallos por IP (`LOGIN_MAX_INTENTOS_IP`, 20 por defecto, en la misma ventana de 15 min). Cuenta también los intentos con usuarios inexistentes, que antes nunca bloqueaban. Frena el *password spraying*. |
| X1-c | Si el usuario no existe, bcrypt se ejecuta igual contra un hash ficticio. La respuesta ya no delata qué usuarios existen. |
| X1-e | La IP de `access_events` y `station_sessions` sale de `X-Real-IP` (que nginx ya fija con `$remote_addr`) o del socket. El campo `ip_address` del cuerpo se acepta por compatibilidad pero se ignora. |
| X2-a | Vida máxima de sesión `SESION_DURACION_MAX_H` (12 h por defecto; 0 la apaga). |
| X2-b | Modificar (con cambio real) o revocar un permiso cierra las sesiones abiertas de ese usuario. |
| X2-c | Restablecer la contraseña cierra las sesiones de ese usuario. En X2-b y X2-c la sesión de quien hace el cambio se respeta. |
| X4-d | Con `APP_ENV=production` se apagan `/docs`, `/redoc` y `/openapi.json`. |
| X5-b | `app.seed` y `app.seed_demo` se niegan a correr con `APP_ENV=production` (salvo `--forzar`). |
| X6-a | Se rechaza una palabra conocida con números o símbolos alrededor, incluido el leetspeak (`Password123`, `Oaxaca2026`, `Admin2026`, `P4ssw0rd2026`, etc.). También se rechazan contraseñas que **contienen** "oaxaca", "verificacion", "verificentro" o el propio usuario. Las 7 que la auditoría vio aceptadas ahora se rechazan. |

Pruebas: `backend/tests/test_endurecimiento_x1_x6.py` (28).

**Toqué un archivo tuyo:** `docker-compose.prod.yml`, solo en el bloque `environment` del backend. Agregué `APP_ENV: production`, `LOGIN_MAX_INTENTOS_IP` y `SESION_DURACION_MAX_H`. Revísalo y, si prefieres, documéntalo en el manual.

---

## 2. Sigue pendiente de mi lado

- **Decisión NOM-047, Opción A o B.** No la tomé en este cambio. Hay que alinear antes con Luis la pregunta 1 de la sección 7 de la propuesta.
- **X1-b:** bloqueo por pareja (usuario, IP) en lugar de solo por usuario. Cambia el comportamiento que hoy cubren las pruebas de X1. Lo dejo para cuando revisemos juntos.
- **X1-d:** serializar la comprobación y el registro del fallo con `pg_advisory_xact_lock`. Con el tope de nginx el riesgo práctico es bajo.
- **X2-d:** barrido periódico de sesiones vencidas.
- **X2-e:** fallar cerrado si la sesión es de un usuario inexistente. Obliga a cambiar `crear_sesion_activa` en las pruebas.
- **X5-e:** rol de base de datos de mínimo privilegio.
- **X6-b:** cambio de contraseña por el propio usuario y `must_change_password`.
- **X6-c:** usuarios sin distinguir mayúsculas.

## 3. Para ti

- **Antes de `docker compose up`:** correr `scripts/generar_certificados.sh` y definir `POSTGRES_PASSWORD`. Enterado, ya lo tengo en mi flujo.
- **Prueba de humo E2E:** `smoke_e2e_flujo.mjs` solo inicia sesión con los usuarios del seed, y el login no aplica la política, así que no le afecta. Lo que sí cambia: `bootstrap_prod` ahora valida la contraseña inicial con la política nueva y contra el nombre de usuario. Una contraseña tipo `Admin2026` ya no pasa.
- **Hosting:** de acuerdo con tu conclusión. El hosting compartido no corre Docker, Postgres ni Celery, así que el VPS no es opcional.
