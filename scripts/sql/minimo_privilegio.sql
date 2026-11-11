-- =============================================================================
-- Rol de base de datos de mínimo privilegio para la aplicación (PENDIENTES X5-e)
-- =============================================================================
-- Hoy el backend se conecta con POSTGRES_USER, que es superusuario del
-- contenedor: una inyección SQL o una ejecución de código en la aplicación
-- alcanzaría toda la instancia (crear roles, leer otras bases, borrar tablas).
-- Este script crea un rol SOLO para el tiempo de ejecución, que puede leer y
-- escribir los datos pero no cambiar el esquema ni administrar la base.
--
-- NO SE APLICA SOLO. Es opcional y se ejecuta a mano, una vez por base, después
-- de que las migraciones hayan corrido al menos una vez (ver
-- docs/MANUAL_INSTALACION_Y_OPERACION.md, sección "Rol de base de datos de
-- mínimo privilegio"). Es idempotente: se puede repetir (también rota la
-- contraseña del rol).
--
-- Debe ejecutarse con el MISMO rol que corre las migraciones (POSTGRES_USER),
-- porque ALTER DEFAULT PRIVILEGES solo cubre los objetos que cree ese rol. Así,
-- las tablas que agreguen migraciones futuras quedan accesibles sin repetir esto.
--
-- Uso (la contraseña NO va en el archivo; ver el manual para pasarla sin dejarla
-- en el historial del shell):
--   psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
--        -v app_user=verificacion_app -v app_password='<contraseña>' \
--        -f scripts/sql/minimo_privilegio.sql
--
-- Variables:
--   app_user      Nombre del rol de la aplicación (obligatoria).
--   app_password  Su contraseña (obligatoria, mínimo 16 caracteres).
--   inmutables    OPCIONAL. Si se define (-v inmutables=1), además quita UPDATE y
--                 DELETE sobre event_log y access_events, que son bitácoras que
--                 solo se escriben. Probar primero con la suite completa.
-- =============================================================================

\set ON_ERROR_STOP on

\if :{?app_user}
\else
  \echo 'ERROR: falta -v app_user=<nombre del rol>'
  SELECT 1/0;
\endif
\if :{?app_password}
\else
  \echo 'ERROR: falta -v app_password=<contraseña>'
  SELECT 1/0;
\endif

-- La contraseña debe tener al menos 16 caracteres.
SELECT length(:'app_password') >= 16 AS password_ok \gset
\if :password_ok
\else
  \echo 'ERROR: app_password debe tener al menos 16 caracteres'
  SELECT 1/0;
\endif

-- El rol de la aplicación no puede ser el que ejecuta este script.
SELECT :'app_user' <> current_user AS distinto_ok \gset
\if :distinto_ok
\else
  \echo 'ERROR: app_user no puede ser el mismo rol que ejecuta el script (POSTGRES_USER)'
  SELECT 1/0;
\endif

\echo 'Aplicando rol de mínimo privilegio en la base' :DBNAME 'para el rol' :app_user

BEGIN;

-- 1. El rol: puede iniciar sesión y nada más. Sin superusuario, sin crear bases
--    ni roles, sin replicación y sin saltar la seguridad por filas.
SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
  :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec

-- Contraseña (también al repetir el script: sirve para rotarla).
SELECT format('ALTER ROLE %I PASSWORD %L', :'app_user', :'app_password') \gexec

-- 2. Base de datos: solo se puede conectar quien tiene permiso expreso.
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database()) \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_user') \gexec

-- 3. Esquema: usar sí, crear no.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"app_user";
REVOKE CREATE ON SCHEMA public FROM :"app_user";

-- 4. Datos: leer y escribir. Sin TRUNCATE, sin REFERENCES, sin TRIGGER, y sin
--    poder alterar ni borrar tablas (eso solo lo hace el dueño).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_user";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_user";

-- 5. Objetos que las migraciones creen en adelante (los crea el rol actual).
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_user";

-- 6. La aplicación no administra las versiones del esquema.
SELECT format('REVOKE ALL ON TABLE public.alembic_version FROM %I', :'app_user')
WHERE to_regclass('public.alembic_version') IS NOT NULL \gexec

-- 7. Opcional: bitácoras de solo escritura.
\if :{?inmutables}
REVOKE UPDATE, DELETE ON TABLE public.event_log FROM :"app_user";
REVOKE UPDATE, DELETE ON TABLE public.access_events FROM :"app_user";
\echo 'Bitácoras event_log y access_events: solo SELECT e INSERT para la aplicación.'
\endif

-- 8. Verificación: si algo no quedó como se espera, se aborta y no se confirma.
SELECT bool_and(ok) AS todo_ok
FROM (VALUES
  (has_database_privilege(:'app_user', current_database(), 'CONNECT')),
  (NOT has_database_privilege(:'app_user', current_database(), 'CREATE')),
  (has_schema_privilege(:'app_user', 'public', 'USAGE')),
  (NOT has_schema_privilege(:'app_user', 'public', 'CREATE')),
  (coalesce(has_table_privilege(:'app_user', to_regclass('public.verificaciones'), 'SELECT'), false)),
  (coalesce(has_table_privilege(:'app_user', to_regclass('public.verificaciones'), 'INSERT'), false)),
  (coalesce(has_table_privilege(:'app_user', to_regclass('public.verificaciones'), 'UPDATE'), false)),
  (NOT coalesce(has_table_privilege(:'app_user', to_regclass('public.verificaciones'), 'TRUNCATE'), true)),
  (NOT coalesce(has_table_privilege(:'app_user', to_regclass('public.alembic_version'), 'SELECT'), false)),
  (NOT (SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls
          FROM pg_roles WHERE rolname = :'app_user'))
) AS v(ok) \gset

\if :todo_ok
  COMMIT;
  \echo 'OK: rol' :app_user 'creado o actualizado con privilegios mínimos.'
  \echo 'Siguiente paso: usarlo en DATABASE_URL (APP_DB_USER y APP_DB_PASSWORD en .env.prod).'
\else
  ROLLBACK;
  \echo 'ERROR: la verificación de privilegios falló; no se aplicó ningún cambio.'
  \echo 'Si es una base nueva, corre antes las migraciones (alembic upgrade head).'
  SELECT 1/0;
\endif
