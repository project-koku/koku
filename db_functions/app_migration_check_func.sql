/*
Copyright 2020 Red Hat, Inc.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */
-- Function public.app_migration_check(leaf_migrations, _verbose)
-- Returns bool: true = run migrations; false = migrations up-to-date
-- leaf_migrations (jsonb) = leaf migration names by app from the django code
--    Ex: '{<django-app>: <latest-leaf-migration-name>}'
-- Set _verbose to true to see notices raised during execution
DROP FUNCTION IF EXISTS public.app_migration_check(jsonb, boolean);

CREATE OR REPLACE FUNCTION public.app_migration_check(leaf_migrations jsonb, _verbose boolean DEFAULT false)
RETURNS boolean AS $BODY$
DECLARE
    schema_rec record;
    app_key text;
    app_keys text[];
    latest_migrations jsonb;
    do_migrations boolean := false;
BEGIN
    SELECT array_agg(k)
      INTO app_keys
      FROM jsonb_object_keys(leaf_migrations) k;

    FOR schema_rec IN
        SELECT t.schema_name
          FROM public.api_tenant t
          JOIN pg_namespace n
            on n.nspname = t.schema_name
         ORDER
            BY case when schema_name = 'public'
                         then '0public'
                    else schema_name
               END::text
    LOOP
        IF _verbose
        THEN
            RAISE NOTICE 'Checking %', schema_rec.schema_name;
        END IF;
        EXECUTE 'SELECT jsonb_object_agg(app, migration) ' ||
                  'FROM ( ' ||
                         'SELECT app, ' ||
                                'max(name) as "migration" ' ||
                           'FROM ' || quote_ident(schema_rec.schema_name) || '.django_migrations ' ||
                          'GROUP BY app ' ||
                       ') AS x ;'
           INTO latest_migrations;

        FOREACH app_key IN ARRAY app_keys
        LOOP
            IF latest_migrations ? app_key
            THEN
                IF _verbose
                THEN
                    RAISE NOTICE '    checking %.% > %.%', app_key, leaf_migrations->>app_key, app_key, latest_migrations->>app_key;
                END IF;
                IF leaf_migrations->>app_key > latest_migrations->>app_key
                THEN
                    do_migrations = true;
                    EXIT;
                END IF;
            ELSE
                IF _verbose
                THEN
                    RAISE NOTICE '    app % missing from schema', app_key;
                END IF;
                do_migrations = true;
                EXIT;
            END IF;
        END LOOP;

        EXIT WHEN do_migrations;
    END LOOP;

    RETURN do_migrations;
END;
$BODY$ LANGUAGE PLPGSQL;
