-- Roles de aplicación de la plataforma.
-- Se ejecuta fuera de Alembic (hallazgo red-team #7): CREATE ROLE no es reversible
-- desde una migración y los privilegios deben existir antes de la primera migración.
--
-- Variables psql requeridas:
--   :app_user_password       contraseña del rol de la API (sin BYPASSRLS)
--   :maintainer_password     contraseña del rol de migraciones/seed (con BYPASSRLS)
--
-- Idempotente: se puede reaplicar en cualquier momento (ver infra/scripts/ensure-roles.sh).

\set ON_ERROR_STOP on

-- app_maintainer: propietario del esquema. Ejecuta migraciones, seed y operaciones
-- transversales (alta de organización, superadmin). BYPASSRLS deliberado.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_maintainer') THEN
    CREATE ROLE app_maintainer LOGIN BYPASSRLS;
  END IF;
END
$$;

ALTER ROLE app_maintainer WITH LOGIN BYPASSRLS PASSWORD :'maintainer_password';

-- app_user: rol de la API. Nunca puede saltarse RLS ni crear objetos.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
    CREATE ROLE app_user LOGIN NOBYPASSRLS;
  END IF;
END
$$;

ALTER ROLE app_user WITH LOGIN NOBYPASSRLS NOCREATEDB NOCREATEROLE NOSUPERUSER
  PASSWORD :'app_user_password';

-- El esquema public pertenece a app_maintainer; app_user solo lo usa.
ALTER SCHEMA public OWNER TO app_maintainer;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE :"dbname" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"dbname" TO app_user, app_maintainer;
GRANT USAGE ON SCHEMA public TO app_user;

-- Tablas ya existentes (reaplicación sobre una base viva).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;

-- Tablas futuras: toda tabla creada por app_maintainer queda accesible a app_user
-- sin grants manuales por migración (hallazgo red-team #7).
ALTER DEFAULT PRIVILEGES FOR ROLE app_maintainer IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES FOR ROLE app_maintainer IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app_user;
ALTER DEFAULT PRIVILEGES FOR ROLE app_maintainer IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO app_user;
